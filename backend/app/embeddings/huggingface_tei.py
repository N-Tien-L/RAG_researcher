"""HuggingFace Text-Embeddings-Inference (TEI) client with Redis caching.

Provides :class:`HuggingFaceTEIEmbedder`, a LangChain-compatible embedder that
forwards texts to a self-hosted TEI server (``/v1/embeddings``) with
automatic per-item Redis caching and batching.

Embedding cache keys:

* **Document embeddings**: ``embedding:doc:{sha256(text + mode)}``
  (TTL: ``settings.CACHE_TTL_EMBEDDINGS``, default 3600 s).
* **Query embeddings**: ``embedding:query:{sha256(text + "query")}``
  (same TTL).
"""
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
    """Async-capable client for HuggingFace Text-Embeddings-Inference (TEI).

    Batches texts into groups of ``max_batch_size`` before calling the TEI
    ``/v1/embeddings`` endpoint.  Each text is prefixed with the embedding
    mode (``"passage: "`` or ``"query: "``) as required by asymmetric
    retrieval models (e.g. E5, BGE).

    When ``settings.REDIS_ENABLED`` is ``True``, results are cached in Redis
    using SHA-256 content-addressed keys so that re-embedding unchanged
    texts is avoided.
    """

    def __init__(
        self,
        base_url: str,
        max_batch_size: int = 8,
        timeout: int = 30,
        mode: str = "passage",
    ):
        """Initialise the TEI embedder.

        Args:
            base_url: Base URL of the TEI server
                (e.g. ``"http://localhost:8080"``).  Trailing slashes are
                stripped automatically.
            max_batch_size: Maximum number of texts per HTTP request
                (default 8).  Increase for throughput, decrease to avoid
                OOM on the TEI server.
            timeout: HTTP request timeout in seconds (default 30).
            mode: Default embedding mode: ``"passage"`` for documents
                stored in the vector store, ``"query"`` for user questions.
        """
        self.base_url = base_url.rstrip("/")
        self.max_batch_size = max_batch_size
        self.timeout = timeout
        self.mode = mode

    def _embed_batch(self, batch: List[str], mode: Optional[str] = None) -> List[List[float]]:
        """Embed a single batch of texts synchronously via the TEI HTTP API.

        Prefixes each text with the active mode (``"passage: "`` or
        ``"query: "``) before sending.  Validates that the returned
        embedding dimension matches ``settings.EMBEDDING_DIM``.

        Args:
            batch: Texts to embed (length <= ``max_batch_size``).
            mode: Override the instance-level mode for this batch.

        Returns:
            list[list[float]]: One embedding vector per input text.

        Raises:
            EmbeddingError: If the HTTP request fails or the returned
                dimension does not match ``settings.EMBEDDING_DIM``.
        """
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
        """Embed an arbitrary number of texts by splitting into batches.

        Iterates over *texts* in windows of ``max_batch_size`` and calls
        :meth:`_embed_batch` for each window.

        Args:
            texts: Texts to embed (any length).
            mode: Embedding mode override passed through to each batch.

        Returns:
            list[list[float]]: One embedding vector per input text, in
            the original order.
        """
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            embeddings.extend(self._embed_batch(batch, mode=mode))

        return embeddings

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents with per-document Redis caching.

        Checks the Redis cache for each text individually.  Only texts with
        a cache miss are forwarded to the TEI server as a batch.  Results
        are stored back to Redis with TTL ``settings.CACHE_TTL_EMBEDDINGS``
        and returned in the original input order.

        Falls back to a direct TEI call (no caching) when
        ``settings.REDIS_ENABLED`` is ``False``.

        Args:
            texts: Document texts to embed (typically chunk content).

        Returns:
            list[list[float]]: One embedding vector per input text.
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
        """Embed a single query string with Redis caching.

        Always uses mode ``"query"`` regardless of the instance-level
        ``mode`` setting, so that asymmetric retrieval models score queries
        correctly against passage embeddings.

        Cache key: ``embedding:query:{sha256(text + "query")}``.

        Args:
            text: The user's search or question text.

        Returns:
            list[float]: Embedding vector for *text*.
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