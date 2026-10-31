from __future__ import annotations

from langchain_openai import OpenAIEmbeddings


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.client = OpenAIEmbeddings(api_key=api_key, model=model)
        self.model = model

    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            vectors.extend(self.client.embed_documents(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed_query(text)
