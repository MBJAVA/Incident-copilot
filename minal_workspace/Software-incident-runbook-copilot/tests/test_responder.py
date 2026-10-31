from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from incident_copilot.responder import GroundedResponder


class FakeStructuredClient:
    def __init__(self, result: dict[str, object], *, refusal: str | None = None) -> None:
        self.result = result
        self.refusal = refusal
        self.schema = None
        self.options = None
        self.messages = None

    def with_structured_output(self, schema, **options):
        self.schema = schema
        self.options = options
        return self

    def invoke(self, messages):
        self.messages = messages
        return {
            "raw": SimpleNamespace(
                response_metadata={"finish_reason": "stop"},
                additional_kwargs={"refusal": self.refusal} if self.refusal else {},
            ),
            "parsed": self.result,
            "parsing_error": None,
        }


def test_responder_requests_structured_triage_fields() -> None:
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
    client = FakeStructuredClient(model_result)
    responder = GroundedResponder.__new__(GroundedResponder)
    responder.client = client
    responder.model = "gpt-4o-mini"

    assert responder.generate("sample incident", [], None) == model_result
    assert client.schema["title"] == "incident_triage_response"
    assert client.options == {"method": "json_schema", "strict": True, "include_raw": True}
    schema = client.schema
    assert schema["properties"]["recommended_checks"]["type"] == "array"
    assert schema["properties"]["recovery_options"]["type"] == "array"
    assert schema["properties"]["needs_clarification"]["type"] == "boolean"


def test_intent_classifier_uses_latest_message_and_structured_enum() -> None:
    client = FakeStructuredClient({"intent": "out_of_scope"})
    responder = GroundedResponder.__new__(GroundedResponder)
    responder.classifier = client
    responder.model = "gpt-4o-mini"

    assert responder.is_incident_related("Why is it so hot today?") is False
    assert client.messages[-1].content == "Why is it so hot today?"
    assert client.schema["properties"]["intent"]["enum"] == [
        "incident", "lookup", "out_of_scope",
    ]
    assert "How can we avoid this same incident" in client.messages[0].content


def test_lookup_generation_uses_direct_answer_instructions() -> None:
    client = FakeStructuredClient({
        "answer_status": "answered", "missing_detail": "",
        "summary": {"text": "3% for 5 minutes", "citations": []}, "evidence_quotes": [],
    })
    responder = GroundedResponder.__new__(GroundedResponder)
    responder.client = client
    responder.model = "gpt-4o-mini"

    responder.generate("Earlier incident context", [], None, mode="lookup",
                       current_question="How do I repair the missing reference?")

    assert "Do not convert a definition or threshold question" in client.messages[0].content
    assert client.schema["properties"]["answer_status"]["enum"] == [
        "answered", "partial", "not_found",
    ]
    assert "evidence_quotes" in client.schema["required"]
    context = json.loads(client.messages[1].content)
    assert context["current_question"] == "How do I repair the missing reference?"


def test_structured_model_refusal_is_rejected() -> None:
    responder = GroundedResponder.__new__(GroundedResponder)
    responder.classifier = FakeStructuredClient({"intent": "lookup"}, refusal="declined")

    with pytest.raises(ValueError, match="declined"):
        responder.classify_message("What is the alert threshold?")
