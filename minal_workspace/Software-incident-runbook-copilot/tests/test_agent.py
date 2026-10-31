from __future__ import annotations

from pathlib import Path

from incident_copilot.agent import IncidentAgent
from incident_copilot.conversation import build_incident_context
from incident_copilot.corpus import load_telemetry_snapshots
from incident_copilot.models import (
    Citation,
    EvidenceChunk,
    RetrievedEvidence,
    TelemetrySnapshot,
)
from incident_copilot.telemetry import ReadOnlyTelemetryTools


class FakeRetriever:
    def __init__(self, evidence: list[RetrievedEvidence]) -> None:
        self.evidence = evidence
        self.calls = []

    def search(self, query: str, top_k: int = 20, service: str | None = None,
               environment: str | None = None, include_superseded: bool = False):
        self.calls.append({"query": query, "service": service, "environment": environment,
                           "include_superseded": include_superseded})
        return self.evidence


class FakeResponder:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls = 0
        self.last_incident = None
        self.last_evidence = None
        self.last_snapshot = None
        self.last_mode = None
        self.last_current_question = None

    def generate(self, incident: str, evidence: list[RetrievedEvidence],
                 snapshot: TelemetrySnapshot | None, mode: str = "incident",
                 current_question: str | None = None) -> dict[str, object]:
        self.calls += 1
        self.last_incident = incident
        self.last_evidence = evidence
        self.last_snapshot = snapshot
        self.last_mode = mode
        self.last_current_question = current_question
        return self.result


class FakeScopeClassifier:
    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.messages = []

    def classify_message(self, message: str) -> str:
        self.messages.append(message)
        return self.intent


def make_evidence() -> RetrievedEvidence:
    chunk = EvidenceChunk(
        chunk_id="RB-PAY-014:3:0", doc_id="RB-PAY-014",
        source_path="runbooks/RB-PAY-014.md", section_path="Triage",
        service="checkout-worker", environment="production", version="3", status="active",
        owner="payments-platform", last_reviewed="2026-10-20", source_type="runbook",
        content_hash="abc", chunk_index=0, content="Check consumer errors and recent deployments.",
    )
    return RetrievedEvidence(chunk=chunk, score=0.92)


def test_agent_asks_for_context_before_retrieval() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)

    result = agent.triage("production is unhealthy")

    assert result.needs_clarification
    assert result.clarifying_questions
    assert retriever.calls == []
    assert responder.calls == 0


def test_unrelated_question_gets_scope_message_without_search() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    scope = FakeScopeClassifier("out_of_scope")
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=scope)

    result = agent.triage("Why is it so hot today?")

    assert scope.messages == ["Why is it so hot today?"]
    assert "outside Incident Copilot's scope" in result.summary.text
    assert result.clarifying_questions == []
    assert retriever.calls == []
    assert responder.calls == 0


def test_configuration_key_follow_up_is_not_treated_as_out_of_scope() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({"answer_status": "not_found", "missing_detail": "",
                               "summary": {"text": "", "citations": []}, "evidence_quotes": []})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=FakeScopeClassifier("out_of_scope"))

    result = agent.triage("How do I add this required configuration key?")

    assert responder.last_mode == "lookup"
    assert len(retriever.calls) == 1
    assert "contact the project admins" in result.summary.text


def test_scope_check_uses_only_latest_user_message() -> None:
    retriever = FakeRetriever([make_evidence()])
    scope = FakeScopeClassifier("out_of_scope")
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), FakeResponder({}),
                          scope_classifier=scope)
    messages = [
        {"role": "user", "content": "PAY-QUEUE-LAG is rising."},
        {"role": "assistant", "response": {"clarifying_questions": []}},
        {"role": "user", "content": "Tell me a joke"},
    ]

    result = agent.triage(build_incident_context(messages))

    assert scope.messages == ["Tell me a joke"]
    assert "outside Incident Copilot's scope" in result.summary.text
    assert retriever.calls == []


def test_in_scope_question_continues_to_retrieval() -> None:
    retriever = FakeRetriever([make_evidence()])
    scope = FakeScopeClassifier("incident")
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), FakeResponder({}),
                          scope_classifier=scope)

    agent.triage("PAY-QUEUE-LAG is rising for checkout-worker")

    assert scope.messages == ["PAY-QUEUE-LAG is rising for checkout-worker"]
    assert len(retriever.calls) == 1


def test_alert_threshold_lookup_uses_direct_cited_answer_without_triage_questions() -> None:
    original = make_evidence()
    evidence = RetrievedEvidence(chunk=EvidenceChunk(**{
        **original.chunk.__dict__,
        "chunk_id": "ARCH-ALERT-003:1:0",
        "doc_id": "ARCH-ALERT-003",
        "section_path": "CHECKOUT-5XX",
        "content": "CHECKOUT-5XX fires above 3% for 5 minutes.",
    }), score=0.9)
    citation = evidence.chunk.citation
    retriever = FakeRetriever([evidence])
    responder = FakeResponder({
        "answer_status": "answered", "missing_detail": "",
        "summary": {"text": "CHECKOUT-5XX fires above 3% for 5 minutes.",
                    "citations": [citation]},
        "evidence_quotes": [{"citation": citation,
                             "quote": "CHECKOUT-5XX fires above 3% for 5 minutes."}],
    })
    scope = FakeScopeClassifier("lookup")
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=scope)

    result = agent.triage("What is the CHECKOUT-5XX threshold and duration?")

    assert responder.last_mode == "lookup"
    assert result.summary.text == "CHECKOUT-5XX fires above 3% for 5 minutes."
    assert result.summary.citations[0].reference == citation
    assert result.clarifying_questions == []
    assert not result.needs_clarification


def test_snapshot_trigger_question_uses_recorded_threshold_without_model_paraphrase() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder,
                          scope_classifier=FakeScopeClassifier("incident"))

    result = agent.triage("What threshold and duration triggered PAY-PROVIDER-TIMEOUT in SNAP-PROV-001?")

    assert "28%" in result.summary.text
    assert "10%" in result.summary.text
    assert "five minutes" in result.summary.text
    assert result.summary.citations[0].reference == "SNAP-PROV-001#Alert snapshot"
    assert retriever.calls == []
    assert responder.calls == 0
    assert not result.needs_clarification


def test_lookup_can_search_without_an_alert_or_service() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({"answer_status": "not_found", "missing_detail": "",
                               "summary": {"text": "", "citations": []}})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=FakeScopeClassifier("lookup"))

    result = agent.triage("Who owns Kafka brokers?")

    assert len(retriever.calls) == 1
    assert responder.last_mode == "lookup"
    assert "not provided in the sources I can access" in result.summary.text
    assert "contact the project admins" in result.summary.text
    assert result.clarifying_questions == []


def test_follow_up_lookup_prioritizes_the_latest_user_question() -> None:
    original = make_evidence()
    evidence = RetrievedEvidence(chunk=EvidenceChunk(**{
        **original.chunk.__dict__,
        "chunk_id": "RB-K8S-003:3:0",
        "doc_id": "RB-K8S-003",
        "section_path": "Recovery decision",
        "content": "Use the approved configuration workflow.",
    }), score=0.9)
    retriever = FakeRetriever([evidence])
    responder = FakeResponder({
        "answer_status": "partial",
        "missing_detail": "The exact key name and edit steps are not documented.",
        "summary": {
            "text": "Use the approved configuration workflow.",
            "citations": [evidence.chunk.citation],
        },
        "evidence_quotes": [{"citation": evidence.chunk.citation,
                             "quote": "Use the approved configuration workflow."}],
    })
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=FakeScopeClassifier("lookup"))
    messages = [
        {"role": "user", "content": "What does SNAP-K8S-001 indicate about the CrashLoop cause?"},
        {"role": "assistant", "response": {"clarifying_questions": []}},
        {"role": "user", "content": "how do I add this required configuration key"},
    ]

    result = agent.triage(build_incident_context(messages))

    assert responder.last_current_question == "how do I add this required configuration key"
    assert retriever.calls[0]["query"].startswith(
        "Current question: how do I add this required configuration key"
    )
    assert "couldn't find a complete answer" in result.summary.text
    assert "exact key name and edit steps" in result.summary.text
    assert "contact the project admins" in result.summary.text
    assert "Use the approved configuration workflow" in result.summary.text
    assert result.summary.citations[0].reference == evidence.chunk.citation


def test_prevention_follow_up_uses_direct_answer_instead_of_root_cause_format() -> None:
    original = make_evidence()
    prevention_chunk = EvidenceChunk(**{
        **original.chunk.__dict__,
        "chunk_id": "RB-K8S-003:3:0",
        "doc_id": "RB-K8S-003",
        "section_path": "Prevention",
        "content": "Validate referenced keys before deployment.",
    })
    evidence = RetrievedEvidence(chunk=prevention_chunk, score=0.9)
    responder = FakeResponder({
        "answer_status": "answered", "missing_detail": "",
        "summary": {"text": "Validate referenced keys before deployment.",
                    "citations": [prevention_chunk.citation]},
        "evidence_quotes": [{"citation": prevention_chunk.citation,
                             "quote": "Validate referenced keys before deployment."}],
    })
    agent = IncidentAgent(FakeRetriever([evidence]), ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=FakeScopeClassifier("lookup"))
    messages = [
        {"role": "user", "content": "What caused SNAP-K8S-001?"},
        {"role": "assistant", "response": {"clarifying_questions": []}},
        {"role": "user", "content": "How do we avoid this in the future?"},
    ]

    result = agent.triage(build_incident_context(messages))

    assert responder.last_mode == "lookup"
    assert responder.last_current_question == "How do we avoid this in the future?"
    assert result.summary.text == "Validate referenced keys before deployment."
    assert "Likely root cause:" not in result.summary.text
    assert result.clarifying_questions == []


def test_lookup_rejects_a_citation_without_a_quote_from_that_source() -> None:
    evidence = make_evidence()
    responder = FakeResponder({
        "answer_status": "answered", "missing_detail": "",
        "summary": {"text": "Increase the pool limit immediately.",
                    "citations": [evidence.chunk.citation]},
        "evidence_quotes": [{"citation": evidence.chunk.citation,
                             "quote": "Increase the pool limit immediately."}],
    })
    agent = IncidentAgent(FakeRetriever([evidence]), ReadOnlyTelemetryTools([]), responder,
                          scope_classifier=FakeScopeClassifier("lookup"))

    result = agent.triage("Should I increase the pool limit?")

    assert result.summary.text == (
        "That information is not provided in the sources I can access. "
        "Please contact the project admins."
    )
    assert result.summary.citations == []


def test_follow_up_answer_supplies_missing_service_and_environment() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)
    messages = [
        {"role": "user", "content": "Consumer lag is rising."},
        {"role": "assistant", "response": {"clarifying_questions": ["Which service is affected?"]}},
        {"role": "user", "content": "checkout-worker in production"},
    ]

    agent.triage(build_incident_context(messages))

    assert retriever.calls[0]["service"] == "checkout-worker"
    assert retriever.calls[0]["environment"] == "production"
    assert "Consumer lag is rising" in responder.last_incident


def test_runtime_platform_reply_gets_a_component_question_instead_of_repeating_service() -> None:
    retriever = FakeRetriever([make_evidence()])
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), FakeResponder({}))
    messages = [
        {"role": "user", "content": "The platform is unhealthy."},
        {"role": "assistant", "response": {"clarifying_questions": ["Which service or alert is affected?"]}},
        {"role": "user", "content": "Runtime Platform is affected"},
    ]

    result = agent.triage(build_incident_context(messages))

    assert "Runtime Platform is affected" in result.summary.text
    assert "Which Runtime Platform component or alert" in result.clarifying_questions[0]
    assert retriever.calls == []


def test_runtime_platform_component_follow_up_proceeds_to_retrieval() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)
    messages = [
        {"role": "user", "content": "Runtime Platform is affected"},
        {"role": "assistant", "response": {"clarifying_questions": [
            "Which Runtime Platform component or alert is affected (for example, Kafka brokers, Redis, or Kubernetes)?"
        ]}},
        {"role": "user", "content": "Kafka brokers are timing out in production"},
    ]

    agent.triage(build_incident_context(messages))

    assert retriever.calls[0]["service"] is None
    assert retriever.calls[0]["environment"] == "production"
    assert "Affected platform component: Kafka brokers" in responder.last_incident


def test_follow_up_correction_takes_precedence_over_initial_service() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), FakeResponder({}))
    messages = [
        {"role": "user", "content": "checkout-worker in production has errors"},
        {"role": "assistant", "response": {"clarifying_questions": []}},
        {"role": "user", "content": "Actually, checkout-api is the affected service."},
    ]

    agent.triage(build_incident_context(messages))

    assert retriever.calls[0]["service"] == "checkout-api"


def test_agent_uses_snapshot_filters_and_only_allows_retrieved_citations() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({
        "summary": {"text": "Consumer errors rose after the release.",
                "citations": ["RB-PAY-014#Triage"]},
        "observations": [
            {"text": "Unsupported claim.", "citations": ["MADE-UP#Section"]},
                {"text": "Alert snapshot exists.", "citations": ["SNAP-PAY-001#Alert snapshot"]},
        ],
        "likely_causes": [
            {"text": "A release caused consumer errors.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "missing_evidence": [],
        "recommended_checks": [],
        "recovery_options": [
            {"text": "Ask the service owner to approve rollback.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "escalation": {"text": "", "citations": []},
        "clarifying_questions": [],
        "needs_clarification": False,
    })
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)

    result = agent.triage("SNAP-PAY-001 consumer errors", environment="production")

    assert retriever.calls[0]["service"] == "checkout-worker"
    assert retriever.calls[0]["environment"] == "production"
    assert result.summary.citations == [Citation(
        "RB-PAY-014", "Triage", "runbooks/RB-PAY-014.md"
    )]
    assert "Likely root cause:" in result.summary.text
    assert "Possible fix:" in result.summary.text
    assert len(result.observations) == 1
    assert result.observations[0].citations[0].doc_id == "SNAP-PAY-001"


def test_alert_name_alone_does_not_attach_an_old_fixture() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)

    agent.triage("PAY-QUEUE-LAG is firing now for checkout-worker in production")

    assert responder.last_snapshot is None


def test_alert_metadata_selects_matching_fixture() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)

    agent.triage(
        "Alert ID: PAY-QUEUE-LAG\nService: checkout-worker\n"
        "Fired at: 2026-10-18T14:22:00Z\nRegion: ca-central-1"
    )

    assert responder.last_snapshot.snapshot_id == "SNAP-PAY-001"
    assert "splunk_searches" in responder.last_snapshot.payload


def test_pasted_alert_json_selects_matching_fixture() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    responder = FakeResponder({})
    agent = IncidentAgent(FakeRetriever([make_evidence()]), ReadOnlyTelemetryTools(snapshots), responder)

    agent.triage(
        '{"alert_id":"PAY-QUEUE-LAG","service":"checkout-worker",'
        '"region":"ca-central-1","fired_at":"2026-10-18T14:22:00Z"}'
    )

    assert responder.last_snapshot.snapshot_id == "SNAP-PAY-001"


def test_fixture_with_known_data_gaps_asks_before_naming_a_cause_or_fix() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({
        "likely_causes": [
            {"text": "A cache invalidation caused the miss surge.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "recovery_options": [
            {"text": "Change cache TTL settings.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "clarifying_questions": ["Were cache keys invalidated?"],
    })
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)

    result = agent.triage("SNAP-CACHE-001")

    assert "Likely root cause: not established" in result.summary.text
    assert "Possible fix: not established" in result.summary.text
    assert result.clarifying_questions == ["Were cache keys invalidated?"]


def test_summary_prefers_current_snapshot_evidence_to_historical_cause() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    responder = FakeResponder({
        "likely_causes": [
            {"text": "A past release caused this alert type.", "citations": ["RB-PAY-014#Triage"]},
            {"text": "Current startup errors reduced active consumers.",
             "citations": ["SNAP-PAY-001#Alert snapshot"]},
        ],
        "recovery_options": [
            {"text": "Request an approved rollback.", "citations": ["RB-PAY-014#Triage"]},
        ],
    })
    agent = IncidentAgent(FakeRetriever([make_evidence()]), ReadOnlyTelemetryTools(snapshots), responder)

    result = agent.triage("SNAP-PAY-001")

    assert "Current startup errors" in result.summary.text
    assert "A past release" not in result.summary.text
    assert result.summary.citations[0].reference == "SNAP-PAY-001#Alert snapshot"


def test_agent_only_includes_superseded_docs_for_explicit_query() -> None:
    retriever = FakeRetriever([make_evidence()])
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), FakeResponder({}))

    agent.triage("PAY-QUEUE-LAG what did the archived runbook say?")

    assert retriever.calls[0]["include_superseded"] is True


def test_agent_uses_service_environment_and_time_window_from_context() -> None:
    snapshots = load_telemetry_snapshots(Path(__file__).parents[1] / "corpus")
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools(snapshots), responder)

    agent.triage(
        "Checkout-worker consumer errors in production",
        time_window="2026-10-23 10:00–10:30 UTC",
    )

    assert retriever.calls[0]["service"] == "checkout-worker"
    assert retriever.calls[0]["environment"] == "production"
    assert "Incident time window: 2026-10-23 10:00–10:30 UTC" in responder.last_incident


def test_agent_uses_fields_in_pasted_json() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)

    agent.triage('{"service":"checkout-worker","environment":"production","symptom":"consumer errors"}')

    assert retriever.calls[0]["service"] == "checkout-worker"
    assert retriever.calls[0]["environment"] == "production"
    assert responder.calls == 1


def test_no_guidance_does_not_reask_known_context() -> None:
    retriever = FakeRetriever([])
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), FakeResponder({}))

    result = agent.triage("service: checkout-worker\nenvironment: production\nconsumer errors")

    assert retriever.calls[0]["service"] == "checkout-worker"
    assert retriever.calls[0]["environment"] == "production"
    assert "not provided in the sources I can access" in result.summary.text
    assert result.clarifying_questions == []


def test_missing_recovery_option_prompts_for_more_evidence() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({
        "likely_causes": [
            {"text": "A release may have caused errors.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "recovery_options": [],
        "clarifying_questions": ["Did the errors begin immediately after the release?"],
        "needs_clarification": True,
    })
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)

    result = agent.triage("PAY-QUEUE-LAG consumer errors", service="checkout-worker")

    assert "Likely root cause:" in result.summary.text
    assert "Possible fix: not established" in result.summary.text
    assert result.needs_clarification
    assert result.clarifying_questions == ["Did the errors begin immediately after the release?"]


def test_no_cause_does_not_present_escalation_as_a_fix() -> None:
    retriever = FakeRetriever([make_evidence()])
    responder = FakeResponder({
        "likely_causes": [],
        "recovery_options": [
            {"text": "Escalate to the on-call team.", "citations": ["RB-PAY-014#Triage"]},
        ],
        "clarifying_questions": ["What changed before the lag rose?"],
    })
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)

    result = agent.triage("PAY-QUEUE-LAG rising lag", service="checkout-worker")

    assert result.recovery_options == []
    assert "Possible fix: not established" in result.summary.text
    assert result.clarifying_questions == ["What changed before the lag rose?"]


def test_new_incident_does_not_use_a_past_postmortem_as_current_evidence() -> None:
    runbook = make_evidence()
    old_incident = RetrievedEvidence(
        chunk=EvidenceChunk(**{
            **runbook.chunk.__dict__,
            "chunk_id": "PM-2026-101:1:0",
            "doc_id": "PM-2026-101",
            "source_type": "postmortem",
        }),
        score=0.95,
    )
    retriever = FakeRetriever([old_incident, runbook])
    responder = FakeResponder({})
    agent = IncidentAgent(retriever, ReadOnlyTelemetryTools([]), responder)

    agent.triage("checkout-worker in production has consumer lag with no deployment data",
                 service="checkout-worker")

    assert [item.chunk.doc_id for item in responder.last_evidence] == ["RB-PAY-014"]
