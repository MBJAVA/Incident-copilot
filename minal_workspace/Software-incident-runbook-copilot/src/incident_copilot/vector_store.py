from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
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
        documents = self.as_retriever(
            top_k=top_k, service=service, environment=environment,
            include_superseded=include_superseded,
        ).invoke(query)
        return [
            RetrievedEvidence(
                chunk=_chunk_from_document(document),
                score=float(document.metadata.get("score", 0.0)),
            )
            for document in documents
        ]

    def as_retriever(self, top_k: int = 20, service: str | None = None,
                     environment: str | None = None,
                     include_superseded: bool = False) -> LangChainHybridRetriever:
        if top_k < 1:
            raise ValueError("top_k must be positive")
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
        return LangChainHybridRetriever(
            index=self.index, embedder=self.embedder, sparse_encoder=self.sparse_encoder,
            namespace=self.namespace, alpha=self.alpha, top_k=top_k,
            metadata_filter=metadata_filter,
        )


class LangChainHybridRetriever(BaseRetriever):
    """LangChain retriever over the project's existing hybrid Pinecone records."""

    index: Any
    embedder: Any
    sparse_encoder: Any
    namespace: str
    alpha: float
    top_k: int
    metadata_filter: Optional[dict[str, Any]] = None

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        sparse_query = self.sparse_encoder.encode_queries(query)
        response = self.index.query(
            vector=[self.alpha * value for value in self.embedder.embed_query(query)],
            sparse_vector={
                "indices": sparse_query["indices"],
                "values": [(1.0 - self.alpha) * value for value in sparse_query["values"]],
            },
            top_k=self.top_k,
            include_metadata=True,
            namespace=self.namespace,
            filter=self.metadata_filter,
        )
        documents = []
        for match in response.matches:
            if not match.metadata:
                continue
            metadata = dict(match.metadata)
            content = str(metadata.pop("content"))
            metadata["score"] = float(match.score or 0.0)
            documents.append(Document(id=str(match.id), page_content=content, metadata=metadata))
        return documents


def make_embedder(api_key: str, model: str = "text-embedding-3-small") -> OpenAIEmbedder:
    return OpenAIEmbedder(api_key=api_key, model=model)


def _chunk_from_document(document: Document) -> EvidenceChunk:
    metadata = document.metadata
    return EvidenceChunk(
        chunk_id=str(document.id),
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
        content=document.page_content,
    )
