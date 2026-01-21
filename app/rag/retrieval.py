"""Retrieval layer placeholder for future vector store integrations."""

from typing import List


class Retriever:
    """Stub retriever to be implemented with a vector store client."""

    def __init__(self) -> None:
        self.ready = False

    def search(self, query: str, k: int = 5) -> List[str]:
        if not self.ready:
            raise RuntimeError("Retriever not configured with a vector store")
        return []
