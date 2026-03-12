import asyncio
import json
import time
from typing import List, Optional

from app.cache.redis_cache import compute_cache_key, get_redis_client
from app.core.config import settings
from app.core.logging import get_logger, log_cache_operation
from app.services.exceptions import EmbeddingError, get_request_context_data
import requests

logger = get_logger(__name__)


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

        try:
            resp = requests.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": prefixed},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EmbeddingError(
                message=f"TEI API request failed: {str(exc)}",
                provider="huggingface_tei",
                **get_request_context_data(),
            ) from exc

        embeddings = [item["embedding"] for item in resp.json()["data"]]
        if embeddings and len(embeddings[0]) != settings.EMBEDDING_DIM:
            raise EmbeddingError(
                message=(
                    "Embedding dimension mismatch: "
                    f"expected {settings.EMBEDDING_DIM}, got {len(embeddings[0])}"
                ),
                provider="huggingface_tei",
                **get_request_context_data(),
            )
        return embeddings

    def _embed(self, texts: List[str], mode: Optional[str] = None) -> List[List[float]]:
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            embeddings.extend(self._embed_batch(batch, mode=mode))

        return embeddings

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed documents with per-document caching.

        Cached embeddings are looked up individually; only uncached texts
        are sent to the TEI server.  Results are returned in the original
        order.

        Args:
            texts: List of document texts to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not settings.REDIS_ENABLED:
            return await asyncio.to_thread(self._embed, texts, self.mode)

        redis_client = await get_redis_client()
        results: List[List[float] | None] = [None] * len(texts)
        uncached_indices: List[int] = []

        # Check cache for each document
        for idx, text in enumerate(texts):
            cache_key = f"embedding:doc:{compute_cache_key(text, self.mode)}"
            start = time.time()
            cached = await redis_client.get(cache_key)
            elapsed = (time.time() - start) * 1000

            if cached is not None:
                results[idx] = json.loads(cached)
                log_cache_operation(logger, "hit", "embedding", cache_key, elapsed)
            else:
                log_cache_operation(logger, "miss", "embedding", cache_key, elapsed)
                uncached_indices.append(idx)

        # Batch-embed only uncached documents
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            new_embeddings = await asyncio.to_thread(
                self._embed, uncached_texts, self.mode
            )

            for local_idx, global_idx in enumerate(uncached_indices):
                embedding = new_embeddings[local_idx]
                results[global_idx] = embedding
                # Store in cache
                cache_key = f"embedding:doc:{compute_cache_key(texts[global_idx], self.mode)}"
                await redis_client.set(
                    cache_key,
                    json.dumps(embedding),
                    ttl=settings.CACHE_TTL_EMBEDDINGS,
                )

        return results  # type: ignore[return-value]

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query with caching.

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector.
        """
        cache_key = f"embedding:query:{compute_cache_key(text, 'query')}"

        if settings.REDIS_ENABLED:
            redis_client = await get_redis_client()
            start = time.time()
            cached = await redis_client.get(cache_key)
            elapsed = (time.time() - start) * 1000

            if cached is not None:
                log_cache_operation(logger, "hit", "embedding", cache_key, elapsed)
                return json.loads(cached)

            log_cache_operation(logger, "miss", "embedding", cache_key, elapsed)

        # Cache miss or caching disabled – call TEI
        result = await asyncio.to_thread(self._embed, [text], "query")
        embedding = result[0]

        if settings.REDIS_ENABLED:
            await redis_client.set(
                cache_key,
                json.dumps(embedding),
                ttl=settings.CACHE_TTL_EMBEDDINGS,
            )

        return embedding