from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from incident_copilot.models import CitedStatement, TriageResponse


FAITHFULNESS_TARGET = 0.90
LATENCY_P95_TARGET_SECONDS = 15.0
DEFAULT_CASE_IDS = ("Q02", "Q03", "Q13", "Q17", "Q18", "Q20", "Q26", "Q27")


@dataclass(frozen=True)
class AnswerStatement:
    section: str
    text: str
    citations: list[str]


def incident_for_case(case: dict[str, Any]) -> str:
    incident = str(case["query"])
    if case.get("alert_snapshot"):
        incident += f"\nSnapshot ID: {case['alert_snapshot']}"
    return incident


def answer_statements(response: TriageResponse) -> list[AnswerStatement]:
    sections: list[tuple[str, list[CitedStatement]]] = [
        ("summary", [response.summary]),
        ("observations", response.observations),
        ("likely_causes", response.likely_causes),
        ("recommended_checks", response.recommended_checks),
        ("recovery_options", response.recovery_options),
        ("escalation", [response.escalation]),
    ]
    statements = []
    for section, items in sections:
        for item in items:
            if item.text.strip() and not _is_clarification_scaffold(item):
                statements.append(AnswerStatement(
                    section=section,
                    text=item.text,
                    citations=[citation.reference for citation in item.citations],
                ))
    return statements


def _is_clarification_scaffold(statement: CitedStatement) -> bool:
    text = statement.text.strip()
    return not statement.citations and (
        text == "I need a little more incident context before triaging."
        or text.startswith("I understand that Runtime Platform is affected.")
        or text == (
            "That information is not provided in the sources I can access. "
            "Please contact the project admins."
        )
        or text == (
            "Likely root cause: not established from the available evidence.\n\n"
            "Possible fix: not established from the available evidence."
        )
    )


def answer_text(response: TriageResponse) -> str:
    # The visible answer includes clarification scaffolding even though it does
    # not contain factual claims to grade for faithfulness.
    parts = [response.summary.text]
    for group in (response.observations, response.likely_causes,
                  response.recommended_checks, response.recovery_options):
        parts.extend(statement.text for statement in group)
    if response.escalation.text:
        parts.append(response.escalation.text)
    parts.extend(response.missing_evidence)
    parts.extend(response.clarifying_questions)
    return "\n".join(part for part in parts if part.strip())


def behavior_matches(expected: str, response: TriageResponse) -> bool:
    if expected == "abstain":
        return (
            "not provided in the sources I can access" in response.summary.text
            or "couldn't find a complete answer in the sources I can access" in response.summary.text
        ) and not response.clarifying_questions
    if expected == "ask_for_evidence":
        return response.needs_clarification and bool(response.clarifying_questions)
    if expected == "escalate":
        return bool(response.escalation.text.strip())
    if expected == "answer":
        return bool(answer_statements(response))
    raise ValueError(f"Unknown expected behavior: {expected}")


def score_judgment(
    judgment: dict[str, Any], case: dict[str, Any], statements: list[AnswerStatement],
    allowed_sources: set[str], answer_body: str,
) -> dict[str, Any]:
    statement_grades = _indexed_grades(judgment, "statement_grades", len(statements), "supported")
    required_grades = judgment.get("required_grades")
    required = _indexed_grades(judgment, "required_grades", len(case.get("must_include", [])), "met")
    forbidden = _indexed_grades(judgment, "forbidden_grades", len(case.get("must_not", [])), "violated")
    required_audit = []
    for grade in sorted(required_grades, key=lambda item: item["index"]):
        quote = grade.get("quote")
        if not isinstance(quote, str):
            raise ValueError("Judge returned an invalid required quote")
        index = grade["index"]
        met = required[index] and bool(quote.strip()) and quote in answer_body
        required_audit.append({
            "point": case["must_include"][index], "met": met, "quote": quote,
        })

    audited = []
    for index, statement in enumerate(statements):
        invalid = sorted(set(statement.citations) - allowed_sources)
        # A factual answer needs a source for its claims. The judge also checks that
        # the cited text actually supports the whole statement.
        supported = bool(statement.citations) and not invalid and statement_grades[index]
        audited.append({
            "section": statement.section,
            "text": statement.text,
            "citations": statement.citations,
            "invalid_citations": invalid,
            "supported": supported,
        })

    cited_sources = {citation for statement in statements for citation in statement.citations}
    expected_sources = set(case.get("expected_sources", []))
    return {
        "statements": audited,
        "supported_statements": sum(item["supported"] for item in audited),
        "statement_count": len(audited),
        "cited_statements": sum(bool(item["citations"]) for item in audited),
        "valid_citations": sum(
            citation in allowed_sources for item in audited for citation in item["citations"]
        ),
        "citation_count": sum(len(item["citations"]) for item in audited),
        "required_audit": required_audit,
        "required_met": sum(item["met"] for item in required_audit),
        "required_count": len(required),
        "forbidden_avoided": len(forbidden) - sum(forbidden),
        "forbidden_count": len(forbidden),
        "expected_sources_cited": len(expected_sources & cited_sources),
        "expected_source_count": len(expected_sources),
    }


def _indexed_grades(judgment: dict[str, Any], key: str, expected_count: int,
                    value_key: str) -> list[bool]:
    grades = judgment.get(key)
    if not isinstance(grades, list) or len(grades) != expected_count:
        raise ValueError(f"Judge returned the wrong number of {key}")
    by_index: dict[int, bool] = {}
    for grade in grades:
        if not isinstance(grade, dict) or type(grade.get("index")) is not int \
                or type(grade.get(value_key)) is not bool:
            raise ValueError(f"Judge returned an invalid {key} item")
        index = grade["index"]
        if index in by_index or index < 0 or index >= expected_count:
            raise ValueError(f"Judge returned a duplicate or out-of-range {key} index")
        by_index[index] = grade[value_key]
    return [by_index[index] for index in range(expected_count)]


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [result for result in results if "scores" in result]
    all_cases_scored = len(successful) == len(results)
    def total(field: str) -> int:
        return sum(result["scores"][field] for result in successful)

    statement_count = total("statement_count")
    required_count = total("required_count")
    forbidden_count = total("forbidden_count")
    expected_source_count = total("expected_source_count")
    citation_count = total("citation_count")
    latencies = sorted(result["triage_latency_seconds"] for result in successful)
    p95 = latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None
    faithfulness = total("supported_statements") / statement_count if statement_count else None
    return {
        "cases_scored": len(successful),
        "cases_failed": len(results) - len(successful),
        "faithfulness": faithfulness,
        "faithfulness_target": FAITHFULNESS_TARGET,
        "faithfulness_target_met": (
            faithfulness >= FAITHFULNESS_TARGET and all_cases_scored
            if faithfulness is not None else None
        ),
        "p95_triage_latency_seconds": p95,
        "latency_target_seconds": LATENCY_P95_TARGET_SECONDS,
        "latency_target_met": (
            p95 <= LATENCY_P95_TARGET_SECONDS and all_cases_scored if p95 is not None else None
        ),
        "behavior_accuracy": (
            sum(result["behavior_matched"] for result in successful) / len(successful)
            if successful else None
        ),
        "required_point_coverage": total("required_met") / required_count if required_count else None,
        "citation_validity": total("valid_citations") / citation_count if citation_count else None,
        "factual_statement_citation_coverage": (
            total("cited_statements") / statement_count if statement_count else None
        ),
        "forbidden_claim_avoidance": (
            total("forbidden_avoided") / forbidden_count if forbidden_count else None
        ),
        "expected_source_citation_recall": (
            total("expected_sources_cited") / expected_source_count if expected_source_count else None
        ),
        "supported_statements": total("supported_statements"),
        "statement_count": statement_count,
    }
