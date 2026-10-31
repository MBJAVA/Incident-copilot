from pathlib import Path

from incident_copilot.corpus import find_snapshot, load_documents, load_telemetry_snapshots
from incident_copilot.telemetry import ReadOnlyTelemetryTools


CORPUS = Path(__file__).parents[1] / "corpus"


def test_corpus_loader_keeps_telemetry_out_of_document_corpus() -> None:
    documents = load_documents(CORPUS)
    snapshots = load_telemetry_snapshots(CORPUS)

    assert len(documents) == 18
    assert len(snapshots) == 6
    assert all(document.source_type != "telemetry" for document in documents)
    assert all(snapshot.snapshot_id.startswith("SNAP-") for snapshot in snapshots)


def test_read_only_telemetry_tool_finds_selected_fixture_without_mutations() -> None:
    snapshots = load_telemetry_snapshots(CORPUS)
    tools = ReadOnlyTelemetryTools(snapshots)

    result = tools.get_snapshot_payload("snap-pay-001")

    assert result is not None
    assert result["snapshot_id"] == "SNAP-PAY-001"
    assert result["fired_at"] == "2026-10-18T14:22:00Z"
    assert result["splunk_searches"][0]["events"]
    assert tools.list_alert_ids() == sorted(snapshot.alert_id for snapshot in snapshots)


def test_find_snapshot_is_case_insensitive() -> None:
    snapshots = load_telemetry_snapshots(CORPUS)

    assert find_snapshot(snapshots, "snap-chk-001").alert_id == "CHECKOUT-5XX"
    assert find_snapshot(snapshots, "UNKNOWN-SNAPSHOT") is None


def test_fixture_lookup_requires_exact_incident_context() -> None:
    tools = ReadOnlyTelemetryTools(load_telemetry_snapshots(CORPUS))

    assert tools.find_incident(
        "PAY-QUEUE-LAG", "checkout-worker", "ca-central-1", "2026-10-18T14:22:00Z"
    ).snapshot_id == "SNAP-PAY-001"
    assert tools.find_incident(
        "PAY-QUEUE-LAG", "checkout-worker", "ca-central-1", "2026-10-25T14:22:00Z"
    ) is None
