from __future__ import annotations

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from incident_copilot.config import Settings
from incident_copilot.embeddings import OpenAIEmbedder
from incident_copilot.vector_store import PineconeHybridStore


def main() -> None:
    settings = Settings.from_environment()
    store = PineconeHybridStore.connect(
        api_key=settings.require_pinecone(),
        index_name=settings.pinecone_index_name,
        embedder=OpenAIEmbedder(settings.require_openai(), settings.openai_embedding_model),
        sparse_encoder_path=settings.bm25_encoder_path,
        namespace=settings.pinecone_namespace,
    )
    cases = yaml.safe_load((ROOT / "evaluation" / "questions.yaml").read_text(encoding="utf-8"))["cases"]
    cases = [case for case in cases if any(not source.startswith("SNAP-")
                                           for source in case.get("expected_sources", []))]

    hits_at_k = 0
    reciprocal_ranks = []
    citation_hits = 0
    citation_total = 0
    for case in cases:
        query = case["query"]
        service = None
        environment = None
        incident = case.get("alert_snapshot")
        if incident:
            telemetry = next((path for path in (ROOT / "corpus" / "telemetry").glob("*.json")
                              if incident in path.read_text(encoding="utf-8")), None)
            if telemetry is not None:
                import json
                snapshot = json.loads(telemetry.read_text(encoding="utf-8"))
                service = snapshot.get("service")
                environment = snapshot.get("environment")
                query += "\n" + json.dumps(snapshot, sort_keys=True)

        expected = {source for source in case.get("expected_sources", []) if not source.startswith("SNAP-")}
        old_query = any(term in query.casefold() for term in ("archived", "superseded", "old runbook", "old guidance"))
        results = store.search(query, top_k=20, service=service,
                               environment=environment, include_superseded=old_query)
        retrieved = [item.chunk.citation for item in results]
        citation_hits += len(expected.intersection(retrieved))
        citation_total += len(expected)
        if expected.intersection(retrieved):
            hits_at_k += 1
            reciprocal_ranks.append(1 / (min(retrieved.index(item) for item in expected.intersection(retrieved)) + 1))
        else:
            reciprocal_ranks.append(0.0)

    denominator = max(citation_total, 1)
    print(f"Queries evaluated: {len(cases)}")
    print(f"Expected source-section recall@20: {citation_hits / denominator:.3f}")
    print(f"Query hit rate@20: {hits_at_k / max(len(cases), 1):.3f}")
    print(f"MRR@20: {sum(reciprocal_ranks) / max(len(cases), 1):.3f}")


if __name__ == "__main__":
    main()
