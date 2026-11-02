from __future__ import annotations

import pytest

from incident_copilot.evaluation import (
    AnswerStatement,
    answer_statements,
    answer_text,
    behavior_matches,
    incident_for_case,
    score_judgment,
    summarize_results,
)
from incident_copilot.models import Citation, CitedStatement, TriageResponse


def response_with(statement: CitedStatement) -> TriageResponse:
    return TriageResponse(
        summary=statement,
        observations=[], likely_causes=[], missing_evidence=[], recommended_checks=[],
        recovery_options=[], escalation=CitedStatement("", []),
        clarifying_questions=[], needs_clarification=False,
    )


def test_evaluation_attaches_only_the_requested_snapshot() -> None:
    assert incident_for_case({"query": "PAY-QUEUE-LAG is rising", "alert_snapshot": "SNAP-PAY-001"}) == (
        "PAY-QUEUE-LAG is rising\nSnapshot ID: SNAP-PAY-001"
    )


def test_visible_abstention_text_is_available_to_the_answer_judge() -> None:
    response = response_with(CitedStatement(
        "Likely root cause: not established from the available evidence.\n\n"
        "Possible fix: not established from the available evidence.", []
    ))

    assert answer_statements(response) == []
    assert "Likely root cause: not established" in answer_text(response)


def test_partial_abstention_without_guidance_is_not_a_factual_statement() -> None:
    response = response_with(CitedStatement(
        "I couldn't find a complete answer in the sources I can access. "
        "The exact production command is not documented. Please contact the project admins.", []
    ))

    assert answer_statements(response) == []
    assert behavior_matches("abstain", response)
    assert "exact production command" in answer_text(response)


def test_statement_grading_requires_a_valid_supporting_citation() -> None:
    citation = Citation("RB-PAY-014", "Triage", "runbooks/RB-PAY-014.md")
    statements = answer_statements(response_with(CitedStatement("Restart the broker.", [citation])))
    case = {"must_include": ["broker restart"], "must_not": ["purge messages"],
            "expected_sources": [citation.reference]}
    judgment = {
        "statement_grades": [{"index": 0, "supported": False}],
        "required_grades": [{"index": 0, "met": True, "quote": "Restart the broker."}],
        "forbidden_grades": [{"index": 0, "violated": False}],
    }

    scores = score_judgment(judgment, case, statements, {citation.reference}, "Restart the broker.")

    assert scores["supported_statements"] == 0
    assert scores["valid_citations"] == 1
    assert scores["citation_count"] == 1
    assert scores["required_met"] == 1
    assert scores["forbidden_avoided"] == 1
    assert scores["expected_sources_cited"] == 1

    judgment["statement_grades"][0]["supported"] = True
    assert score_judgment(judgment, case, statements, set(), "Restart the broker.")["supported_statements"] == 0
    assert score_judgment(judgment, case, [AnswerStatement("summary", "Restart the broker.", [])],
                          {citation.reference}, "Restart the broker.")["supported_statements"] == 0
    judgment["required_grades"][0]["quote"] = "a phrase absent from the answer"
    assert score_judgment(judgment, case, statements, {citation.reference},
                          "Restart the broker.")["required_met"] == 0


def test_judge_must_grade_every_index_once() -> None:
    case = {"must_include": ["one"], "must_not": [], "expected_sources": []}
    judgment = {"statement_grades": [], "required_grades": [], "forbidden_grades": []}

    with pytest.raises(ValueError, match="wrong number"):
        score_judgment(judgment, case, [], set(), "")


def test_behavior_and_aggregate_targets_use_triage_time_only() -> None:
    citation = Citation("RB-PAY-014", "Triage", "runbooks/RB-PAY-014.md")
    assert behavior_matches("answer", response_with(CitedStatement("Check errors.", [citation])))
    assert not behavior_matches("ask_for_evidence", response_with(CitedStatement("Check errors.", [citation])))
    assert behavior_matches("abstain", response_with(CitedStatement(
        "That information is not provided in the sources I can access. Please contact the project admins.", []
    )))
    summary = summarize_results([
        {"behavior_matched": True, "triage_latency_seconds": 7.0, "scores": {
            "supported_statements": 1, "statement_count": 1,
            "cited_statements": 1, "valid_citations": 1, "citation_count": 1,
            "required_met": 1, "required_count": 1,
            "forbidden_avoided": 1, "forbidden_count": 1,
            "expected_sources_cited": 1, "expected_source_count": 1,
        }},
        {"behavior_matched": False, "triage_latency_seconds": 16.0, "scores": {
            "supported_statements": 0, "statement_count": 1,
            "cited_statements": 0, "valid_citations": 0, "citation_count": 0,
            "required_met": 0, "required_count": 1,
            "forbidden_avoided": 0, "forbidden_count": 1,
            "expected_sources_cited": 0, "expected_source_count": 1,
        }},
    ])

    assert summary["faithfulness"] == 0.5
    assert summary["faithfulness_target_met"] is False
    assert summary["p95_triage_latency_seconds"] == 16.0
    assert summary["latency_target_met"] is False
    assert summary["behavior_accuracy"] == 0.5
    assert summary["citation_validity"] == 1.0
    assert summary["factual_statement_citation_coverage"] == 0.5
