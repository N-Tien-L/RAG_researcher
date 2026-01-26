"""Query-time RAG pipeline."""

from typing import List

from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.rag.retrieval import retrieve_chunks
from app.core.config import get_env


class RagPipeline:
    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self.embedder = HuggingFaceTEIEmbedder(
            base_url=get_env("TEI_URL", "http://localhost:8080"),
            max_batch_size=int(get_env("TEI_MAX_BATCH", "8")),
            mode="query",
        )

    def retrieve(self, query: str, collection_name: str) -> List[str]:
        query_embedding = self.embedder.embed_query(query)
        return retrieve_chunks(
            embedding=query_embedding,
            collection_name=collection_name,
            top_k=self.top_k,
        )
