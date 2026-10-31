from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from incident_copilot.config import Settings
from incident_copilot.corpus import load_documents
from incident_copilot.documents import chunk_document
from incident_copilot.embeddings import OpenAIEmbedder
from incident_copilot.vector_store import PineconeHybridStore


def main() -> None:
    settings = Settings.from_environment()
    api_key = settings.require_openai()
    pinecone_key = settings.require_pinecone()
    documents = load_documents(settings.corpus_path)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    if not chunks:
        raise SystemExit("No Markdown chunks were produced from the corpus.")

    sparse_encoder = PineconeHybridStore.fit_sparse_encoder(chunks, settings.bm25_encoder_path)
    embedder = OpenAIEmbedder(api_key, settings.openai_embedding_model)
    from pinecone import Pinecone

    index = Pinecone(api_key=pinecone_key).Index(settings.pinecone_index_name)
    store = PineconeHybridStore(index, embedder, sparse_encoder, namespace=settings.pinecone_namespace)
    count = store.upsert_chunks(chunks)
    print(f"Indexed {count} chunks from {len(documents)} source documents.")
    print(f"BM25 encoder saved to {settings.bm25_encoder_path}")


if __name__ == "__main__":
    main()
