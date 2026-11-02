from __future__ import annotations

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
