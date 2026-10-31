from __future__ import annotations

import json
from types import SimpleNamespace

from incident_copilot.responder import GroundedResponder


def test_responder_requests_structured_triage_fields() -> None:
    captured = {}
    model_result = {
        "summary": {"text": "", "citations": []},
        "observations": [],
        "likely_causes": [],
        "missing_evidence": [],
        "recommended_checks": [],
        "recovery_options": [],
        "escalation": {"text": "", "citations": []},
        "clarifying_questions": [],
        "needs_clarification": False,
    }

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=json.dumps(model_result), refusal=None),
        )])

    responder = GroundedResponder.__new__(GroundedResponder)
    responder.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    responder.model = "gpt-4o-mini"

    assert responder.generate("sample incident", [], None) == model_result
    response_format = captured["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["recommended_checks"]["type"] == "array"
    assert schema["properties"]["recovery_options"]["type"] == "array"
    assert schema["properties"]["needs_clarification"]["type"] == "boolean"


def test_intent_classifier_uses_latest_message_and_structured_enum() -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content='{"intent": "out_of_scope"}', refusal=None),
        )])

    responder = GroundedResponder.__new__(GroundedResponder)
    responder.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    responder.model = "gpt-4o-mini"

    assert responder.is_incident_related("Why is it so hot today?") is False
    assert captured["messages"][-1]["content"] == "Why is it so hot today?"
    assert captured["response_format"]["json_schema"]["schema"]["properties"]["intent"]["enum"] == [
        "incident", "lookup", "out_of_scope",
    ]
    assert "How can we avoid this same incident" in captured["messages"][0]["content"]


def test_lookup_generation_uses_direct_answer_instructions() -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content='{"answer_status": "answered", "missing_detail": "", "summary": {"text": "3% for 5 minutes", "citations": []}, "evidence_quotes": []}',
                                    refusal=None),
        )])

    responder = GroundedResponder.__new__(GroundedResponder)
    responder.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    responder.model = "gpt-4o-mini"

    responder.generate("Earlier incident context", [], None, mode="lookup",
                       current_question="How do I repair the missing reference?")

    assert "Do not convert a definition or threshold question" in captured["messages"][0]["content"]
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["answer_status"]["enum"] == ["answered", "partial", "not_found"]
    assert "evidence_quotes" in schema["required"]
    context = json.loads(captured["messages"][1]["content"])
    assert context["current_question"] == "How do I repair the missing reference?"
