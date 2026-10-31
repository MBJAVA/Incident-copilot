from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from incident_copilot.config import Settings
from incident_copilot.evaluation import (
    DEFAULT_CASE_IDS,
    answer_statements,
    answer_text,
    behavior_matches,
    incident_for_case,
    score_judgment,
    summarize_results,
)
from incident_copilot.models import RetrievedEvidence, TriageResponse
from incident_copilot.runtime import build_agent


def _grade_item(value_name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            value_name: {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["index", value_name, "reason"],
        "additionalProperties": False,
    }


def _required_grade_item() -> dict[str, Any]:
    item = _grade_item("met")
    item["properties"]["quote"] = {"type": "string"}
    item["required"].append("quote")
    return item


JUDGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "behavior_grade": {
            "type": "object",
            "properties": {"met": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["met", "reason"],
            "additionalProperties": False,
        },
        "statement_grades": {"type": "array", "items": _grade_item("supported")},
        "required_grades": {"type": "array", "items": _required_grade_item()},
        "forbidden_grades": {"type": "array", "items": _grade_item("violated")},
    },
    "required": ["behavior_grade", "statement_grades", "required_grades", "forbidden_grades"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """Audit an incident-triage answer against its source text. Return exactly one
grade for each supplied index, even when an input list is empty.

For behavior_grade, met means the response fulfills the expected behavior for the user's actual
question. For answer, it must address the question directly; generic diagnostic steps alone do not
count. For ask_for_evidence, it must request relevant missing information without guessing a cause.
For escalate, it must give the appropriate handoff or approval boundary. For abstain, it must
state that the requested information is unavailable in accessible sources and avoid guessing.

For statement_grades, supported is true only when ALL material factual or operational claims in that
statement follow from its own cited sources and the user's incident facts. A cited source that merely
mentions the same component is insufficient. A past postmortem cannot prove a current incident's
cause. Mark an unsupported causal leap, invented fix, or contradicted detail false. The citation
must support the specific statement, not just be a valid reference.

For required_grades, met is true only when the answer explicitly conveys the expected point,
including in clarifying questions. Do not infer a point from silence, a related observation, or
an unstated implication. If met is true, quote the shortest exact contiguous excerpt of the
answer that states it; otherwise return an empty quote. For forbidden_grades, violated is true only when the answer
asserts or recommends the forbidden point; a warning against it is not a violation. Do not reward
plausible-sounding text that is absent from the answer. Keep reasons short.
"""


class RecordingRetriever:
    def __init__(self, retriever: Any) -> None:
        self.retriever = retriever
        self.last_results: list[RetrievedEvidence] = []

    def search(self, *args: Any, **kwargs: Any) -> list[RetrievedEvidence]:
        self.last_results = self.retriever.search(*args, **kwargs)
        return self.last_results


def judge_answer(client: OpenAI, model: str, case: dict[str, Any], response: TriageResponse,
                 evidence: list[RetrievedEvidence], snapshot_payload: dict[str, object] | None) -> dict[str, Any]:
    statements = answer_statements(response)
    cited = {citation for statement in statements for citation in statement.citations}
    sources: dict[str, list[str]] = {}
    for item in evidence:
        if item.chunk.citation in cited:
            sources.setdefault(item.chunk.citation, []).append(item.chunk.content)
    if snapshot_payload is not None and case.get("alert_snapshot"):
        reference = f"{case['alert_snapshot']}#Alert snapshot"
        if reference in cited:
            sources[reference] = [json.dumps(snapshot_payload, ensure_ascii=False)]

    input_data = {
        "incident": incident_for_case(case),
        "expected_behavior": case["expected_behavior"],
        "answer": answer_text(response),
        "statements": [
            {"index": index, "section": item.section, "text": item.text, "citations": item.citations}
            for index, item in enumerate(statements)
        ],
        "cited_source_text": sources,
        "required_points": [
            {"index": index, "point": point}
            for index, point in enumerate(case.get("must_include", []))
        ],
        "forbidden_points": [
            {"index": index, "point": point}
            for index, point in enumerate(case.get("must_not", []))
        ],
    }
    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {
            "name": "incident_answer_evaluation", "strict": True, "schema": JUDGMENT_SCHEMA,
        }},
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ],
    )
    choice = completion.choices[0]
    if choice.finish_reason != "stop" or choice.message.refusal or not choice.message.content:
        raise ValueError("Answer judge did not return a complete evaluation")
    return json.loads(choice.message.content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score generated incident answers against labeled cases.")
    parser.add_argument("--case-ids", default=",".join(DEFAULT_CASE_IDS),
                        help="Comma-separated case IDs; default is an eight-case smoke set.")
    parser.add_argument("--all", action="store_true", help="Evaluate all labeled cases.")
    parser.add_argument("--judge-model", default=None,
                        help="OpenAI grading model; defaults to OPENAI_JUDGE_MODEL or gpt-4o.")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "answer_evaluation.json")
    args = parser.parse_args()

    all_cases = yaml.safe_load((ROOT / "evaluation" / "questions.yaml").read_text(encoding="utf-8"))["cases"]
    cases_by_id = {case["id"]: case for case in all_cases}
    selected_ids = list(cases_by_id) if args.all else [item.strip() for item in args.case_ids.split(",") if item.strip()]
    unknown = set(selected_ids) - cases_by_id.keys()
    if unknown:
        parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
    if not selected_ids:
        parser.error("Select at least one case")

    settings = Settings.from_environment()
    judge_model = args.judge_model or os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o")
    agent = build_agent(settings)
    retriever = RecordingRetriever(agent.retriever)
    agent.retriever = retriever
    judge_client = OpenAI(api_key=settings.require_openai())
    results = []

    for case_id in selected_ids:
        case = cases_by_id[case_id]
        retriever.last_results = []
        print(f"Evaluating {case_id} ({case['category']})...", flush=True)
        try:
            start = perf_counter()
            response = agent.triage(incident_for_case(case))
            latency = perf_counter() - start  # Retrieval + answer generation; excludes grading.
            snapshot = agent.telemetry.get_snapshot(case["alert_snapshot"]) if case.get("alert_snapshot") else None
            judgment = judge_answer(
                judge_client, judge_model, case, response,
                retriever.last_results, snapshot.payload if snapshot else None,
            )
            behavior_grade = judgment.get("behavior_grade")
            if not isinstance(behavior_grade, dict) or type(behavior_grade.get("met")) is not bool:
                raise ValueError("Judge returned an invalid behavior grade")
            allowed = {item.chunk.citation for item in retriever.last_results}
            if snapshot:
                allowed.add(f"{snapshot.snapshot_id}#Alert snapshot")
            scores = score_judgment(
                judgment, case, answer_statements(response), allowed, answer_text(response)
            )
            results.append({
                "id": case_id,
                "category": case["category"],
                "expected_behavior": case["expected_behavior"],
                "behavior_matched": (
                    behavior_matches(case["expected_behavior"], response)
                    and behavior_grade["met"]
                ),
                "triage_latency_seconds": round(latency, 3),
                "scores": scores,
                "judge_grades": judgment,
                "response": response.to_dict(),
            })
        except Exception as error:
            results.append({"id": case_id, "category": case["category"], "error": str(error)})
            print(f"  Failed: {error}", flush=True)

    summary = summarize_results(results)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_version": yaml.safe_load((ROOT / "evaluation" / "questions.yaml").read_text(encoding="utf-8")).get("corpus_version"),
        "answer_model": settings.openai_chat_model,
        "judge_model": judge_model,
        "latency_scope": "agent.triage only; excludes judge time and app rendering",
        "faithfulness_definition": "fraction of factual answer statements whose entire content is supported by their own citations and incident facts, as checked by an LLM judge and citation validation",
        "summary": summary,
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Report: {args.output}")
    return 1 if summary["cases_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
