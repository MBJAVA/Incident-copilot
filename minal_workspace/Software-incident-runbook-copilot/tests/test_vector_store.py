from __future__ import annotations

from types import SimpleNamespace

from pytest import approx
from pinecone.exceptions import NotFoundException

from incident_copilot.models import EvidenceChunk
from incident_copilot.vector_store import PineconeHybridStore


class FakeEmbedder:
    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        return [[0.2, 0.4] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.2, 0.4]


class FakeSparseEncoder:
    def encode_documents(self, texts: list[str]):
        return [{"indices": [3, 9], "values": [2.0, 1.0]} for _ in texts]

    def encode_queries(self, text: str):
        return {"indices": [3, 9], "values": [1.5, 0.5]}


class FakeIndex:
    def __init__(self) -> None:
        self.deleted = []
        self.upserted = []
        self.query_args = None

    def delete(self, **kwargs):
        self.deleted.append(kwargs)

    def upsert(self, **kwargs):
        self.upserted.append(kwargs)

    def query(self, **kwargs):
        self.query_args = kwargs
        metadata = {
            "doc_id": "RB-PAY-014",
            "source_path": "runbooks/RB-PAY-014-kafka-consumer-lag.md",
            "section_path": "Kafka consumer lag / Triage",
            "service": "checkout-worker",
            "environment": "production",
            "version": "3",
            "status": "active",
            "owner": "payments-platform",
            "last_reviewed": "2026-10-20",
            "source_type": "runbook",
            "content_hash": "abc",
            "chunk_index": 0,
            "content": "Check consumer errors and deployment history.",
        }
        match = SimpleNamespace(id="RB-PAY-014:3:0", score=0.88, metadata=metadata)
        return SimpleNamespace(matches=[match])


class EmptyNamespaceIndex(FakeIndex):
    def delete(self, **kwargs):
        self.deleted.append(kwargs)
        raise NotFoundException(status=404, reason="Namespace not found")


def make_chunk() -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id="RB-PAY-014:3:0",
        doc_id="RB-PAY-014",
        source_path="runbooks/RB-PAY-014-kafka-consumer-lag.md",
        section_path="Kafka consumer lag / Triage",
        service="checkout-worker",
        environment="production",
        version="3",
        status="active",
        owner="payments-platform",
        last_reviewed="2026-10-20",
        source_type="runbook",
        content_hash="abc",
        chunk_index=0,
        content="Check consumer errors and deployment history.",
    )


def test_upsert_uses_dense_and_sparse_vectors_and_replaces_document() -> None:
    index = FakeIndex()
    store = PineconeHybridStore(index, FakeEmbedder(), FakeSparseEncoder(), alpha=0.65)

    count = store.upsert_chunks([make_chunk()])

    assert count == 1
    assert index.deleted[0]["filter"] == {"doc_id": {"$in": ["RB-PAY-014"]}}
    vector = index.upserted[0]["vectors"][0]
    assert vector["values"] == [0.13, 0.26]
    assert vector["sparse_values"] == {"indices": [3, 9], "values": [0.7, 0.35]}
    assert vector["metadata"]["section_path"] == "Kafka consumer lag / Triage"


def test_first_upsert_handles_missing_namespace() -> None:
    index = EmptyNamespaceIndex()
    store = PineconeHybridStore(index, FakeEmbedder(), FakeSparseEncoder())

    assert store.upsert_chunks([make_chunk()]) == 1
    assert len(index.upserted) == 1


def test_search_combines_dense_sparse_and_metadata_filters() -> None:
    index = FakeIndex()
    store = PineconeHybridStore(index, FakeEmbedder(), FakeSparseEncoder(), alpha=0.65)

    results = store.search("consumer lag after deploy", service="checkout-worker",
                           environment="production", top_k=7)

    assert len(results) == 1
    assert results[0].chunk.citation == "RB-PAY-014#Kafka consumer lag / Triage"
    assert results[0].score == 0.88
    assert index.query_args["sparse_vector"]["indices"] == [3, 9]
    assert index.query_args["sparse_vector"]["values"] == approx([0.525, 0.175])
    assert index.query_args["filter"] == {"$and": [
        {"service": {"$in": ["checkout-worker", "platform"]}},
        {"environment": {"$eq": "production"}},
        {"status": {"$ne": "superseded"}},
    ]}
    assert index.query_args["top_k"] == 7
