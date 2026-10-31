from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from incident_copilot.documents import parse_markdown_document
from incident_copilot.models import SourceDocument, TelemetrySnapshot


class CorpusError(ValueError):
    pass


def load_documents(corpus_root: Path) -> list[SourceDocument]:
    documents = [
        parse_markdown_document(path, corpus_root)
        for path in sorted(corpus_root.rglob("*.md"))
        if path.name != "README.md"
    ]
    _validate_unique_doc_ids(documents)
    return documents


def load_telemetry_snapshots(corpus_root: Path) -> list[TelemetrySnapshot]:
    snapshots: list[TelemetrySnapshot] = []
    for path in sorted((corpus_root / "telemetry").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "snapshot_id", "alert_id", "service", "environment", "region",
            "fired_at", "captured_at", "severity",
        }
        missing = required - payload.keys()
        if missing:
            raise CorpusError(f"{path} is missing fields: {', '.join(sorted(missing))}")
        snapshots.append(TelemetrySnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            source_path=path.relative_to(corpus_root).as_posix(),
            alert_id=str(payload["alert_id"]),
            service=str(payload["service"]),
            environment=str(payload["environment"]),
            region=str(payload["region"]),
            fired_at=str(payload["fired_at"]),
            captured_at=str(payload["captured_at"]),
            severity=str(payload["severity"]),
            payload=payload,
        ))
    return snapshots


def find_snapshot(snapshots: Iterable[TelemetrySnapshot], snapshot_id: str) -> TelemetrySnapshot | None:
    key = snapshot_id.casefold()
    return next((snapshot for snapshot in snapshots if snapshot.snapshot_id.casefold() == key), None)


def _validate_unique_doc_ids(documents: list[SourceDocument]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for document in documents:
        if document.doc_id in seen:
            duplicates.add(document.doc_id)
        seen.add(document.doc_id)
    if duplicates:
        raise CorpusError(f"Duplicate document IDs: {', '.join(sorted(duplicates))}")
