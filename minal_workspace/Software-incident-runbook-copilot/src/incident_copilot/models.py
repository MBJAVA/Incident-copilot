from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


REQUIRED_DOCUMENT_FIELDS = {
    "doc_id",
    "service",
    "environment",
    "version",
    "status",
    "owner",
    "last_reviewed",
    "source_type",
}


@dataclass(frozen=True)
class SourceDocument:
    doc_id: str
    source_path: str
    service: str
    environment: str
    version: str
    status: str
    owner: str
    last_reviewed: str
    source_type: str
    title: str
    content: str
    content_hash: str

    @classmethod
    def from_parts(
        cls,
        source_path: str,
        metadata: dict[str, Any],
        title: str,
        content: str,
        content_hash: str,
    ) -> SourceDocument:
        missing = REQUIRED_DOCUMENT_FIELDS - metadata.keys()
        if missing:
            raise ValueError(f"{source_path} is missing metadata: {', '.join(sorted(missing))}")

        return cls(
            doc_id=str(metadata["doc_id"]),
            source_path=source_path,
            service=str(metadata["service"]),
            environment=str(metadata["environment"]),
            version=str(metadata["version"]),
            status=str(metadata["status"]),
            owner=str(metadata["owner"]),
            last_reviewed=str(metadata["last_reviewed"]),
            source_type=str(metadata["source_type"]),
            title=title,
            content=content,
            content_hash=content_hash,
        )


@dataclass(frozen=True)
class Section:
    path: str
    content: str


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    doc_id: str
    source_path: str
    section_path: str
    service: str
    environment: str
    version: str
    status: str
    owner: str
    last_reviewed: str
    source_type: str
    content_hash: str
    chunk_index: int
    content: str

    @property
    def citation(self) -> str:
        return f"{self.doc_id}#{self.section_path}"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "section_path": self.section_path,
            "service": self.service,
            "environment": self.environment,
            "version": self.version,
            "status": self.status,
            "owner": self.owner,
            "last_reviewed": self.last_reviewed,
            "source_type": self.source_type,
            "content_hash": self.content_hash,
            "chunk_index": self.chunk_index,
            "content": self.content,
        }


@dataclass(frozen=True)
class TelemetrySnapshot:
    snapshot_id: str
    source_path: str
    alert_id: str
    service: str
    environment: str
    region: str
    fired_at: str
    captured_at: str
    severity: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Citation:
    doc_id: str
    section_path: str
    source_path: str

    @property
    def reference(self) -> str:
        return f"{self.doc_id}#{self.section_path}"


@dataclass(frozen=True)
class RetrievedEvidence:
    chunk: EvidenceChunk
    score: float


@dataclass(frozen=True)
class CitedStatement:
    text: str
    citations: list[Citation]


@dataclass(frozen=True)
class TriageResponse:
    summary: CitedStatement
    observations: list[CitedStatement]
    likely_causes: list[CitedStatement]
    missing_evidence: list[str]
    recommended_checks: list[CitedStatement]
    recovery_options: list[CitedStatement]
    escalation: CitedStatement
    clarifying_questions: list[str]
    needs_clarification: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
