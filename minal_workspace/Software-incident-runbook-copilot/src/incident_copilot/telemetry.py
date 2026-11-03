from __future__ import annotations

import difflib
import re

from incident_copilot.corpus import find_snapshot
from incident_copilot.models import TelemetrySnapshot


class ReadOnlyTelemetryTools:
    """Read-only fixture tools for local evaluation; never mutate production state."""

    def __init__(self, snapshots: list[TelemetrySnapshot]) -> None:
        self._snapshots = snapshots

    def get_snapshot_payload(self, snapshot_id: str) -> dict[str, object] | None:
        snapshot = self.get_snapshot(snapshot_id)
        return snapshot.payload if snapshot is not None else None

    def get_snapshot(self, snapshot_id: str) -> TelemetrySnapshot | None:
        return find_snapshot(self._snapshots, snapshot_id)

    def find_incident(self, alert_id: str, service: str, region: str,
                      fired_at: str) -> TelemetrySnapshot | None:
        for snapshot in self._snapshots:
            if (snapshot.alert_id.casefold() == alert_id.casefold()
                    and snapshot.service.casefold() == service.casefold()
                    and snapshot.region.casefold() == region.casefold()
                    and snapshot.fired_at == fired_at):
                return snapshot
        return None

    def find_exact_description(self, description: str) -> TelemetrySnapshot | None:
        """Resolve a full fixture description at the start of a user report."""
        normalized = " ".join(description.split()).casefold().lstrip(" \"'")
        matches = [
            snapshot for snapshot in self._snapshots
            if _starts_with_description(
                normalized, str(snapshot.payload.get("description", ""))
            )
        ]
        return matches[0] if len(matches) == 1 else None

    def find_similar_description(self, description: str, service: str | None = None,
                                 environment: str | None = None,
                                 region: str | None = None,
                                 threshold: float = 0.90) -> TelemetrySnapshot | None:
        """Resolve a unique near-match with service, environment, and region guards."""
        normalized = _normalize_description(description)
        candidates = []
        for snapshot in self._snapshots:
            if service and snapshot.service.casefold() != service.casefold():
                continue
            if environment and snapshot.environment.casefold() != environment.casefold():
                continue
            if region and snapshot.region.casefold() != region.casefold():
                continue
            fixture = _normalize_description(str(snapshot.payload.get("description", "")))
            score = difflib.SequenceMatcher(None, normalized, fixture).ratio()
            if score >= threshold:
                candidates.append((score, snapshot))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return None
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.03:
            return None
        return candidates[0][1]

    def find_metric_match(self, report: str, service: str | None = None,
                          environment: str | None = None,
                          region: str | None = None) -> TelemetrySnapshot | None:
        """Resolve a fixture from identity plus a metric value and matching signal words."""
        report_tokens = set(_normalize_description(report).split())
        candidates = []
        for snapshot in self._snapshots:
            if service and snapshot.service.casefold() != service.casefold():
                continue
            if environment and snapshot.environment.casefold() != environment.casefold():
                continue
            if region and snapshot.region.casefold() != region.casefold():
                continue
            description_tokens = set(_normalize_description(
                str(snapshot.payload.get("description", ""))
            ).split())
            if len(report_tokens & description_tokens) < 3:
                continue
            metric_values = snapshot.payload.get("metrics", {})
            if not isinstance(metric_values, dict):
                continue
            mentioned = False
            for value in metric_values.values():
                if value is None or isinstance(value, bool):
                    continue
                value_text = str(value).casefold()
                if re.search(rf"(?<![\w.]){re.escape(value_text)}%?(?![\w.])",
                             _normalize_description(report)):
                    mentioned = True
                    break
            if mentioned:
                candidates.append(snapshot)
        return candidates[0] if len(candidates) == 1 else None

    def find_signal_match(self, report: str, service: str | None = None,
                          environment: str | None = None,
                          region: str | None = None) -> TelemetrySnapshot | None:
        """Resolve one fixture from identity and several matching alert-description terms."""
        report_tokens = set(_normalize_description(report).split())
        candidates = []
        for snapshot in self._snapshots:
            if service and snapshot.service.casefold() != service.casefold():
                continue
            if environment and snapshot.environment.casefold() != environment.casefold():
                continue
            if region and snapshot.region.casefold() != region.casefold():
                continue
            fixture_tokens = set(_normalize_description(
                str(snapshot.payload.get("description", ""))
            ).split())
            overlap = len(report_tokens & fixture_tokens)
            distinctive_terms = {
                "startup", "readiness", "repeatedly", "failed", "misses", "surged",
                "lookups", "slowed", "timeouts", "lag",
            }
            distinctive_overlap = len(report_tokens & fixture_tokens & distinctive_terms)
            cache_signal = (
                snapshot.alert_id == "CACHE-MISS-SURGE"
                and overlap >= 5
                and {"misses", "missed", "miss"} & report_tokens
                and {"issue", "cause", "root"} & report_tokens
            )
            if ((overlap >= 6 and overlap / max(len(fixture_tokens), 1) >= 0.60
                 and distinctive_overlap >= 2) or cache_signal):
                candidates.append((overlap, snapshot))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return None
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            return None
        return candidates[0][1]

    def list_alert_ids(self) -> list[str]:
        return sorted({snapshot.alert_id for snapshot in self._snapshots})

    def list_services(self) -> list[str]:
        return sorted({snapshot.service for snapshot in self._snapshots})


def _starts_with_description(report: str, description: str) -> bool:
    phrase = " ".join(description.split()).casefold().rstrip(" .!?")
    if not phrase or not report.startswith(phrase):
        return False
    # The full saved wording may be followed by a question or punctuation.
    return not report[len(phrase):] or bool(re.match(r"[\s,.;:!?\"']", report[len(phrase):]))


def _normalize_description(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", " ", text.casefold()).strip()
