from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_chat_model: str
    openai_embedding_model: str
    pinecone_api_key: str | None
    pinecone_index_name: str
    pinecone_namespace: str
    bm25_encoder_path: Path
    corpus_path: Path

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            pinecone_api_key=os.getenv("PINECONE_API_KEY"),
            pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "incident-runbook-copilot"),
            pinecone_namespace=os.getenv("PINECONE_NAMESPACE", "incident-copilot"),
            bm25_encoder_path=PROJECT_ROOT / "artifacts" / "bm25_encoder.json",
            corpus_path=PROJECT_ROOT / "corpus",
        )

    def require_openai(self) -> str:
        if not self.openai_api_key:
            raise ValueError("Set OPENAI_API_KEY in the incident project .env file.")
        return self.openai_api_key

    def require_pinecone(self) -> str:
        if not self.pinecone_api_key:
            raise ValueError("Set PINECONE_API_KEY in the incident project .env file.")
        return self.pinecone_api_key
