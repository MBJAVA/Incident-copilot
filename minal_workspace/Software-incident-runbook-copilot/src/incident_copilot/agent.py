from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Protocol

from incident_copilot.models import (
    Citation,
    CitedStatement,
    RetrievedEvidence,
    TelemetrySnapshot,
    TriageResponse,
)
from incident_copilot.telemetry import ReadOnlyTelemetryTools


class Retriever(Protocol):
    def search(self, query: str, top_k: int = 20, service: str | None = None,
               environment: str | None = None,
               include_superseded: bool = False) -> list[RetrievedEvidence]: ...


class Responder(Protocol):
    def generate(self, incident: str, evidence: list[RetrievedEvidence],
                 snapshot: TelemetrySnapshot | None, mode: str = "incident",
                 current_question: str | None = None) -> dict[str, object]: ...


class ScopeClassifier(Protocol):
    def classify_message(self, message: str) -> str: ...


ALERT_ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+){1,5}\b")
SNAPSHOT_ID_PATTERN = re.compile(r"\bSNAP-[A-Z0-9]+-\d+\b", re.I)
OLD_DOC_QUERY_PATTERN = re.compile(r"\b(archived|superseded|previous|old runbook|old guidance)\b", re.I)
HISTORICAL_QUERY_PATTERN = re.compile(
    r"\b(postmortem|previous incident|past incident|historical|similar incident|PM-\d{4}-\d+)\b", re.I
)
ENVIRONMENT_ALIASES = {"prod": "production", "dev": "development"}
UNAVAILABLE_SOURCE_MESSAGE = (
    "That information is not provided in the sources I can access. "
    "Please contact the project admins."
)
RUNTIME_PLATFORM_PATTERN = re.compile(r"\bruntime platform\b", re.I)
PLATFORM_COMPONENT_PATTERNS = {
    "Kafka brokers": re.compile(r"\b(?:kafka|brokers?)\b", re.I),
    "Redis": re.compile(r"\bredis\b", re.I),
    "Kubernetes": re.compile(r"\b(?:kubernetes|k8s)\b", re.I),
}
CONFIGURATION_FOLLOWUP_PATTERN = re.compile(
    r"\b(?:configuration|config|secret)\s+(?:key|reference)\b", re.I
)
SNAPSHOT_ISSUE_PATTERN = re.compile(r"\b(?:issue|symptoms?|what happened)\b", re.I)
SNAPSHOT_TRIGGER_PATTERN = re.compile(
    r"\b(?:threshold|breach(?:ed)?|trigger(?:ed)?)\b|\bwhy\b.{0,80}\bfir(?:e|ed)\b", re.I
)
SNAPSHOT_DESCRIPTION_PATTERN = re.compile(r"\b(?:description|one.line)\b", re.I)
ROOT_CAUSE_OR_ACTION_PATTERN = re.compile(
    r"\b(?:root cause|fix|repair|mitigat\w*|resolv\w*|should we|next steps?)\b", re.I
)


class IncidentAgent:
    """Bounded, read-only incident triage workflow. It cannot execute operations."""

    def __init__(self, retriever: Retriever, telemetry: ReadOnlyTelemetryTools,
                 responder: Responder, top_k: int = 20,
                 scope_classifier: ScopeClassifier | None = None) -> None:
        self.retriever = retriever
        self.telemetry = telemetry
        self.responder = responder
        self.top_k = top_k
        self.scope_classifier = scope_classifier

    def triage(self, incident: str, service: str | None = None,
               environment: str | None = None,
               time_window: str | None = None) -> TriageResponse:
        cleaned_incident = incident.strip()
        if not cleaned_incident:
            return _clarification_response(["What alert or production symptom are you investigating?"])

        latest_update = cleaned_incident.split("\n\nConversation so far:", 1)[0]
        latest_update = latest_update.removeprefix("Latest user update:\n")
        intent = self.scope_classifier.classify_message(latest_update) if self.scope_classifier else "incident"
        if CONFIGURATION_FOLLOWUP_PATTERN.search(latest_update) and re.search(
            r"\b(?:how|where|what|which)\b", latest_update, re.I
        ):
            intent = "lookup"
        if intent == "out_of_scope":
            return _out_of_scope_response()

        service = service.strip().lower() if service else None
        environment = environment.strip().lower() if environment else None
        if environment:
            environment = ENVIRONMENT_ALIASES.get(environment, environment)
        alert_id = _extract_alert_id(cleaned_incident)
        details = _incident_fields(cleaned_incident)
        known_services = self.telemetry.list_services()
        service = (service or details.get("service")
                   or _mentioned_service(latest_update, known_services)
                   or _mentioned_service(cleaned_incident, known_services))
        environment = (environment or details.get("environment")
                       or _mentioned_environment(latest_update)
                       or _mentioned_environment(cleaned_incident))
        snapshot = self._get_snapshot(
            cleaned_incident, latest_update, alert_id, service,
            details.get("region"), details.get("fired_at")
        )
        if snapshot is not None:
            alert_id = alert_id or snapshot.alert_id
            service = service or snapshot.service
            environment = environment or snapshot.environment
            fact_response = _snapshot_fact_response(latest_update, snapshot)
            if fact_response is not None:
                return fact_response

        platform_component = (_mentioned_platform_component(latest_update)
                              or _mentioned_platform_component(cleaned_incident))
        if intent != "lookup" and not alert_id and not service and not platform_component:
            if RUNTIME_PLATFORM_PATTERN.search(cleaned_incident):
                return _clarification_response(
                    ["Which Runtime Platform component or alert is affected (for example, Kafka brokers, Redis, or Kubernetes)?"],
                    summary="I understand that Runtime Platform is affected. I need the component or alert to investigate.",
                )
            return _clarification_response(["Which service or alert is affected?"])

        context_parts = [cleaned_incident]
        if service:
            context_parts.append(f"Affected service: {service}")
        if platform_component:
            context_parts.append(f"Affected platform component: {platform_component}")
        if environment:
            context_parts.append(f"Environment: {environment}")
        if time_window and time_window.strip():
            context_parts.append(f"Incident time window: {time_window.strip()}")
        incident_context = "\n".join(context_parts)
        query_parts = [f"Current question: {latest_update}", incident_context]
        if snapshot is not None:
            query_parts.append(_snapshot_search_text(snapshot))
        query = "\n".join(query_parts)
        evidence = self.retriever.search(
            query=query,
            top_k=self.top_k,
            service=service,
            environment=environment,
            include_superseded=bool(OLD_DOC_QUERY_PATTERN.search(cleaned_incident)),
        )
        if snapshot is None and not HISTORICAL_QUERY_PATTERN.search(cleaned_incident):
            evidence = [item for item in evidence if item.chunk.source_type != "postmortem"]
        if not evidence:
            return _no_guidance_response()

        model_result = self.responder.generate(
            incident_context, evidence, snapshot, mode=intent, current_question=latest_update
        )
        if intent == "incident" and snapshot is not None and snapshot.payload.get("data_gaps"):
            model_result = {
                **model_result,
                "likely_causes": [],
                "recovery_options": [],
                "needs_clarification": True,
            }
        allowed_citations = _allowed_citations(evidence, snapshot)
        response = _response_from_model(
            model_result, allowed_citations, mode=intent,
            source_texts=_source_texts(evidence, snapshot),
        )
        if intent == "incident" and snapshot is not None and snapshot.alert_id == "CACHE-MISS-SURGE":
            conditional_paths = _cache_recovery_paths(evidence)
            if conditional_paths and not response.likely_causes:
                response = replace(response, recovery_options=conditional_paths)
        return response

    def _get_snapshot(self, incident: str, latest_update: str,
                      alert_id: str | None, service: str | None,
                      region: str | None, fired_at: str | None) -> TelemetrySnapshot | None:
        snapshot_id = SNAPSHOT_ID_PATTERN.search(incident)
        if snapshot_id:
            return self.telemetry.get_snapshot(snapshot_id.group(0))
        if alert_id and service and region and fired_at:
            return self.telemetry.find_incident(alert_id, service, region, fired_at)
        # A verbatim fixture description is an explicit reference in this prototype.
        # Paraphrases must not inherit historical telemetry from a similar alert.
        snapshot = self.telemetry.find_exact_description(latest_update)
        if snapshot is not None:
            return snapshot
        if "Initial incident report:\n" in incident:
            initial_report = incident.split("Initial incident report:\n", 1)[1].split("\n\n", 1)[0]
            return self.telemetry.find_exact_description(initial_report)
        return None


def _snapshot_fact_response(question: str, snapshot: TelemetrySnapshot) -> TriageResponse | None:
    if ROOT_CAUSE_OR_ACTION_PATTERN.search(question):
        return None
    payload = snapshot.payload
    parts = []
    if SNAPSHOT_DESCRIPTION_PATTERN.search(question) and payload.get("description"):
        parts.append(str(payload["description"]))
    if SNAPSHOT_ISSUE_PATTERN.search(question) and payload.get("issue_summary"):
        parts.append(f"Issue: {payload['issue_summary']}")
    if SNAPSHOT_TRIGGER_PATTERN.search(question) and payload.get("trigger_summary"):
        parts.append(f"Alert trigger: {payload['trigger_summary']}")
    if not parts:
        return None
    citation = Citation(
        doc_id=snapshot.snapshot_id,
        section_path="Alert snapshot",
        source_path=snapshot.source_path,
    )
    return TriageResponse(
        summary=CitedStatement("\n\n".join(parts), [citation]),
        observations=[],
        likely_causes=[],
        missing_evidence=[],
        recommended_checks=[],
        recovery_options=[],
        escalation=CitedStatement("", []),
        clarifying_questions=[],
        needs_clarification=False,
    )


def _extract_alert_id(text: str) -> str | None:
    for candidate in ALERT_ID_PATTERN.findall(text):
        if candidate.startswith(("PAY-", "DB-", "CHECKOUT-", "K8S-", "CACHE-")):
            return candidate
    return None


def _incident_fields(text: str) -> dict[str, str]:
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    fields: dict[str, str] = {}
    if isinstance(payload, dict):
        for key in ("service", "environment", "region", "fired_at"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                fields[key] = value.strip().lower()
    labels = {"service": "service", "environment": "environment",
              "region": "region", "fired_at": "fired_at|fired at"}
    for key, label in labels.items():
        if key not in fields:
            match = re.search(
                rf"(?im)^\s*[\"']?(?:{label})[\"']?\s*[:=]\s*[\"']?([^\s,\"']+)", text
            )
            if match:
                fields[key] = match.group(1).lower()
    if "region" not in fields:
        region = re.search(r"\b[a-z]{2}(?:-[a-z0-9]+)+-\d\b", text, re.I)
        if region:
            fields["region"] = region.group(0).lower()
    if "fired_at" not in fields:
        timestamp = re.search(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b", text, re.I)
        if timestamp:
            fields["fired_at"] = timestamp.group(0).upper()
    if "environment" in fields:
        fields["environment"] = ENVIRONMENT_ALIASES.get(fields["environment"], fields["environment"])
    if "fired_at" in fields:
        fields["fired_at"] = fields["fired_at"].upper()
    return fields


def _mentioned_service(text: str, known_services: list[str]) -> str | None:
    found = [name for name in known_services
             if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.I)]
    return found[0] if len(found) == 1 else None


def _mentioned_environment(text: str) -> str | None:
    matches = {match.lower() for match in re.findall(
        r"\b(?:production|staging|development|prod|dev)\b", text, re.I
    )}
    normalized = {ENVIRONMENT_ALIASES.get(match, match) for match in matches}
    return next(iter(normalized)) if len(normalized) == 1 else None


def _mentioned_platform_component(text: str) -> str | None:
    matches = [name for name, pattern in PLATFORM_COMPONENT_PATTERNS.items() if pattern.search(text)]
    return matches[0] if len(matches) == 1 else None


def _snapshot_search_text(snapshot: TelemetrySnapshot) -> str:
    return f"Alert snapshot {snapshot.alert_id}: {snapshot.payload}"


def _allowed_citations(evidence: list[RetrievedEvidence],
                       snapshot: TelemetrySnapshot | None) -> dict[str, Citation]:
    citations = {
        item.chunk.citation: Citation(
            doc_id=item.chunk.doc_id,
            section_path=item.chunk.section_path,
            source_path=item.chunk.source_path,
        )
        for item in evidence
    }
    if snapshot is not None:
        citation = Citation(
            doc_id=snapshot.snapshot_id,
            section_path="Alert snapshot",
            source_path=snapshot.source_path,
        )
        citations[citation.reference] = citation
    return citations


def _source_texts(evidence: list[RetrievedEvidence],
                  snapshot: TelemetrySnapshot | None) -> dict[str, list[str]]:
    texts: dict[str, list[str]] = {}
    for item in evidence:
        texts.setdefault(item.chunk.citation, []).append(item.chunk.content)
    if snapshot is not None:
        texts[f"{snapshot.snapshot_id}#Alert snapshot"] = [
            json.dumps(snapshot.payload, ensure_ascii=False)
        ]
    return texts


def _cache_recovery_paths(evidence: list[RetrievedEvidence]) -> list[CitedStatement]:
    """Quote the active cache runbook's conditional paths without choosing one."""
    paths: list[CitedStatement] = []
    seen: set[str] = set()
    for section in ("Recovery decision", "Verification"):
        for item in evidence:
            chunk = item.chunk
            if (chunk.doc_id != "RB-CACHE-005" or chunk.status != "active"
                    or chunk.section_path != section):
                continue
            body = re.sub(r"^#{1,6}\s+[^\n]*\n", "", chunk.content).strip()
            citation = Citation(chunk.doc_id, chunk.section_path, chunk.source_path)
            for paragraph in re.split(r"\n\s*\n", body):
                paragraph = paragraph.strip()
                if paragraph in seen:
                    continue
                if section == "Recovery decision" and paragraph.startswith("If "):
                    paths.append(CitedStatement(paragraph, [citation]))
                    seen.add(paragraph)
                elif section == "Verification" and paragraph.startswith("Confirm "):
                    paths.append(CitedStatement("After mitigation: " + paragraph, [citation]))
                    seen.add(paragraph)
    return paths


def _has_verified_lookup_quotes(result: dict[str, object], summary: CitedStatement,
                                source_texts: dict[str, list[str]]) -> bool:
    quotes = result.get("evidence_quotes")
    if not isinstance(quotes, list) or not summary.citations:
        return False
    for citation in summary.citations:
        if not any(
            isinstance(item, dict)
            and item.get("citation") == citation.reference
            and isinstance(item.get("quote"), str)
            and len(item["quote"].strip()) >= 8
            and any(item["quote"] in text for text in source_texts.get(citation.reference, []))
            for item in quotes
        ):
            return False
    return True


def _response_from_model(result: dict[str, object],
                         allowed: dict[str, Citation], mode: str = "incident",
                         source_texts: dict[str, list[str]] | None = None) -> TriageResponse:
    if mode == "lookup":
        status = result.get("answer_status")
        summary = _parse_statement(result.get("summary"), allowed)
        raw_summary = result.get("summary")
        raw_references = raw_summary.get("citations") if isinstance(raw_summary, dict) else None
        if not isinstance(raw_references, list) or any(
            not isinstance(reference, str) or reference not in allowed
            for reference in raw_references
        ):
            summary = CitedStatement("", [])
        if summary.text and not _has_verified_lookup_quotes(result, summary, source_texts or {}):
            summary = CitedStatement("", [])
        if status == "partial":
            missing_detail = str(result.get("missing_detail", "")).strip()
            text = "I couldn't find a complete answer in the sources I can access."
            text += f" {missing_detail}" if missing_detail else ""
            text += " Please contact the project admins."
            if summary.text:
                text += f" Available guidance: {summary.text}"
            summary = CitedStatement(text, summary.citations)
        elif status != "answered" or not summary.text:
            summary = CitedStatement(UNAVAILABLE_SOURCE_MESSAGE, [])
        return TriageResponse(
            summary=summary,
            observations=[],
            likely_causes=[],
            missing_evidence=[],
            recommended_checks=[],
            recovery_options=[],
            escalation=CitedStatement("", []),
            clarifying_questions=[],
            needs_clarification=False,
        )
    observations = _parse_statements(result.get("observations"), allowed)
    likely_causes = _parse_statements(result.get("likely_causes"), allowed)
    checks = _parse_statements(result.get("recommended_checks"), allowed)
    recovery_options = _parse_statements(result.get("recovery_options"), allowed)
    if not likely_causes:
        recovery_options = []
    escalation = _parse_statement(result.get("escalation"), allowed)
    missing = _string_list(result.get("missing_evidence"))
    questions = _string_list(result.get("clarifying_questions"))
    needs_clarification = bool(result.get("needs_clarification")) or bool(questions)
    if not likely_causes or not recovery_options:
        needs_clarification = True
        if not questions:
            questions = [
                "What additional incident evidence can confirm the cause and a safe recovery path?"
            ]
    snapshot_references = {reference for reference in allowed if reference.startswith("SNAP-")}
    summary = _cause_and_fix_summary(likely_causes, recovery_options, snapshot_references)
    if needs_clarification and not questions:
        questions = ["What additional service or incident evidence can you provide?"]
    return TriageResponse(
        summary=summary,
        observations=observations,
        likely_causes=likely_causes,
        missing_evidence=missing,
        recommended_checks=checks,
        recovery_options=recovery_options,
        escalation=escalation,
        clarifying_questions=questions,
        needs_clarification=needs_clarification,
    )


def _cause_and_fix_summary(causes: list[CitedStatement],
                           recovery_options: list[CitedStatement],
                           snapshot_references: set[str]) -> CitedStatement:
    parts = []
    citations = []
    seen = set()
    current_cause = next(
        (cause for cause in causes
         if any(citation.reference in snapshot_references for citation in cause.citations)),
        causes[0] if causes else None,
    )
    summary_items = (("Likely root cause", current_cause),
                     ("Possible fix", recovery_options[0] if recovery_options else None))
    for label, statement in summary_items:
        if statement is not None:
            parts.append(f"{label}: {statement.text}")
            for citation in statement.citations:
                if citation.reference not in seen:
                    citations.append(citation)
                    seen.add(citation.reference)
        else:
            parts.append(f"{label}: not established from the available evidence.")
    return CitedStatement("\n\n".join(parts), citations)


def _parse_statements(value: object, allowed: dict[str, Citation]) -> list[CitedStatement]:
    if not isinstance(value, list):
        return []
    return [statement for item in value
            if (statement := _parse_statement(item, allowed)).text]


def _parse_statement(value: object, allowed: dict[str, Citation]) -> CitedStatement:
    if not isinstance(value, dict):
        return CitedStatement("", [])
    text = str(value.get("text", "")).strip()
    references = value.get("citations", [])
    if not isinstance(references, list):
        references = []
    citations = []
    seen = set()
    for reference in references:
        if isinstance(reference, str) and reference in allowed and reference not in seen:
            citations.append(allowed[reference])
            seen.add(reference)
    if text and not citations:
        return CitedStatement("", [])
    return CitedStatement(text, citations)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clarification_response(questions: list[str], *, summary: str | None = None) -> TriageResponse:
    return TriageResponse(
        summary=CitedStatement(summary or "I need a little more incident context before triaging.", []),
        observations=[],
        likely_causes=[],
        missing_evidence=[],
        recommended_checks=[],
        recovery_options=[],
        escalation=CitedStatement("", []),
        clarifying_questions=questions,
        needs_clarification=True,
    )


def _no_guidance_response() -> TriageResponse:
    return TriageResponse(
        summary=CitedStatement(UNAVAILABLE_SOURCE_MESSAGE, []),
        observations=[],
        likely_causes=[],
        missing_evidence=[],
        recommended_checks=[],
        recovery_options=[],
        escalation=CitedStatement("", []),
        clarifying_questions=[],
        needs_clarification=False,
    )


def _out_of_scope_response() -> TriageResponse:
    return TriageResponse(
        summary=CitedStatement(
            "That question is outside Incident Copilot's scope. I can help investigate software alerts and incidents using runbooks and available telemetry.",
            [],
        ),
        observations=[],
        likely_causes=[],
        missing_evidence=[],
        recommended_checks=[],
        recovery_options=[],
        escalation=CitedStatement("", []),
        clarifying_questions=[],
        needs_clarification=False,
    )
