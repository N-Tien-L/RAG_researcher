from typing import List, Optional
import requests


class HuggingFaceTEIEmbedder:
    """Client for Hugging Face text-embeddings-inference server."""

    def __init__(
        self,
        base_url: str,
        max_batch_size: int = 8,
        timeout: int = 30,
        mode: str = "passage",
    ):
        # mode="passage" → documents / chunks you store
        # mode="query" → user questions / search queries
        self.base_url = base_url.rstrip("/")
        self.max_batch_size = max_batch_size
        self.timeout = timeout
        self.mode = mode

    def _embed_batch(self, batch: List[str], mode: Optional[str] = None) -> List[List[float]]:
        current_mode = (mode or self.mode).strip()
        prefixed = [f"{current_mode}: {text}" for text in batch]

        resp = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": prefixed},
            timeout=self.timeout,
        )
        resp.raise_for_status()

        return [item["embedding"] for item in resp.json()["data"]]

    def _embed(self, texts: List[str], mode: Optional[str] = None) -> List[List[float]]:
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            embeddings.extend(self._embed_batch(batch, mode=mode))

        return embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts, mode=self.mode)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text], mode="query")[0]