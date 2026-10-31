from __future__ import annotations

from incident_copilot.agent import IncidentAgent
from incident_copilot.config import Settings
from incident_copilot.corpus import load_telemetry_snapshots
from incident_copilot.embeddings import OpenAIEmbedder
from incident_copilot.responder import GroundedResponder
from incident_copilot.telemetry import ReadOnlyTelemetryTools
from incident_copilot.vector_store import PineconeHybridStore


def build_agent(settings: Settings | None = None) -> IncidentAgent:
    settings = settings or Settings.from_environment()
    embedder = OpenAIEmbedder(
        api_key=settings.require_openai(),
        model=settings.openai_embedding_model,
    )
    retriever = PineconeHybridStore.connect(
        api_key=settings.require_pinecone(),
        index_name=settings.pinecone_index_name,
        embedder=embedder,
        sparse_encoder_path=settings.bm25_encoder_path,
        namespace=settings.pinecone_namespace,
    )
    responder = GroundedResponder(
        api_key=settings.require_openai(),
        model=settings.openai_chat_model,
    )
    snapshots = load_telemetry_snapshots(settings.corpus_path)
    return IncidentAgent(
        retriever, ReadOnlyTelemetryTools(snapshots), responder,
        scope_classifier=responder,
    )
