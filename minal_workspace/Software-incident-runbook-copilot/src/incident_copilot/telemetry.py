from __future__ import annotations

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

    def list_alert_ids(self) -> list[str]:
        return sorted({snapshot.alert_id for snapshot in self._snapshots})

    def list_services(self) -> list[str]:
        return sorted({snapshot.service for snapshot in self._snapshots})
