from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pinecone import Pinecone
from pinecone.exceptions import NotFoundException
from pinecone_text.sparse import BM25Encoder

from incident_copilot.embeddings import OpenAIEmbedder
from incident_copilot.models import EvidenceChunk, RetrievedEvidence


class Embedder(Protocol):
    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class PineconeHybridStore:
    def __init__(self, index: Any, embedder: Embedder, sparse_encoder: BM25Encoder,
                 namespace: str = "incident-copilot", alpha: float = 0.65) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be between 0 and 1")
        self.index = index
        self.embedder = embedder
        self.sparse_encoder = sparse_encoder
        self.namespace = namespace
        self.alpha = alpha

    @classmethod
    def connect(cls, api_key: str, index_name: str, embedder: Embedder,
                sparse_encoder_path: Path, namespace: str, alpha: float = 0.65) -> PineconeHybridStore:
        if not sparse_encoder_path.exists():
            raise FileNotFoundError(
                f"BM25 encoder not found at {sparse_encoder_path}; run python scripts/index_corpus.py first."
            )
        sparse_encoder = BM25Encoder().load(str(sparse_encoder_path))
        index = Pinecone(api_key=api_key).Index(index_name)
        return cls(index, embedder, sparse_encoder, namespace=namespace, alpha=alpha)

    @staticmethod
    def fit_sparse_encoder(chunks: list[EvidenceChunk], path: Path) -> BM25Encoder:
        encoder = BM25Encoder().fit([chunk.content for chunk in chunks])
        path.parent.mkdir(parents=True, exist_ok=True)
        encoder.dump(str(path))
        return encoder

    def upsert_chunks(self, chunks: list[EvidenceChunk], batch_size: int = 64) -> int:
        if not chunks:
            return 0
        doc_ids = sorted({chunk.doc_id for chunk in chunks})
        try:
            self.index.delete(
                filter={"doc_id": {"$in": doc_ids}},
                namespace=self.namespace,
            )
        except NotFoundException as error:
            # Pinecone has no namespace to delete from before the first upsert.
            if "Namespace not found" not in str(error):
                raise
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            dense_vectors = self.embedder.embed_documents([chunk.content for chunk in batch])
            sparse_vectors = self.sparse_encoder.encode_documents([chunk.content for chunk in batch])
            vectors = []
            for chunk, dense, sparse in zip(batch, dense_vectors, sparse_vectors):
                scaled_dense = [self.alpha * value for value in dense]
                scaled_sparse = {
                    "indices": sparse["indices"],
                    "values": [(1.0 - self.alpha) * value for value in sparse["values"]],
                }
                vectors.append({
                    "id": chunk.chunk_id,
                    "values": scaled_dense,
                    "sparse_values": scaled_sparse,
                    "metadata": chunk.to_metadata(),
                })
            self.index.upsert(vectors=vectors, namespace=self.namespace)
        return len(chunks)

    def search(self, query: str, top_k: int = 20, service: str | None = None,
               environment: str | None = None, include_superseded: bool = False) -> list[RetrievedEvidence]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        sparse_query = self.sparse_encoder.encode_queries(query)
        filters: list[dict[str, Any]] = []
        if service:
            filters.append({"service": {"$in": [service, "platform"]}})
        if environment:
            filters.append({"environment": {"$eq": environment}})
        if not include_superseded:
            filters.append({"status": {"$ne": "superseded"}})
        metadata_filter: dict[str, Any] | None = None
        if len(filters) == 1:
            metadata_filter = filters[0]
        elif filters:
            metadata_filter = {"$and": filters}

        response = self.index.query(
            vector=[self.alpha * value for value in self.embedder.embed_query(query)],
            sparse_vector={
                "indices": sparse_query["indices"],
                "values": [(1.0 - self.alpha) * value for value in sparse_query["values"]],
            },
            top_k=top_k,
            include_metadata=True,
            namespace=self.namespace,
            filter=metadata_filter,
        )
        return [
            RetrievedEvidence(
                chunk=_chunk_from_match(match),
                score=float(match.score or 0.0),
            )
            for match in response.matches
            if match.metadata
        ]


def make_embedder(api_key: str, model: str = "text-embedding-3-small") -> OpenAIEmbedder:
    return OpenAIEmbedder(api_key=api_key, model=model)


def _chunk_from_match(match: Any) -> EvidenceChunk:
    metadata = dict(match.metadata or {})
    return EvidenceChunk(
        chunk_id=str(match.id),
        doc_id=str(metadata["doc_id"]),
        source_path=str(metadata["source_path"]),
        section_path=str(metadata["section_path"]),
        service=str(metadata["service"]),
        environment=str(metadata["environment"]),
        version=str(metadata["version"]),
        status=str(metadata["status"]),
        owner=str(metadata["owner"]),
        last_reviewed=str(metadata["last_reviewed"]),
        source_type=str(metadata["source_type"]),
        content_hash=str(metadata["content_hash"]),
        chunk_index=int(metadata["chunk_index"]),
        content=str(metadata["content"]),
    )
