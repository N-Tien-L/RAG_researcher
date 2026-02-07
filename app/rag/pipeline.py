"""Async RAG pipeline using LangChain Expression Language (LCEL)."""

import asyncio
from typing import Any

from langchain_community.chat_models import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.cache.redis_cache import compute_cache_key, get_redis_client
from app.core.config import settings
from app.core.logging import get_logger, log_cache_operation, log_generation, log_retrieval
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.rag.prompts.qa import QA_PROMPT_V1
from app.rag.retrieval import retrieve_chunks
from app.services.exceptions import (
    EmbeddingError,
    LLMError,
    VectorStoreError,
    get_request_context_data,
)

logger = get_logger(__name__)


class RAGPipeline:
    """Async RAG pipeline using LCEL for retrieval + generation."""

    def __init__(self, top_k: int = 5) -> None:
        """Initialize RAG pipeline.
        
        Args:
            top_k: Number of chunks to retrieve.
        """
        self.top_k = top_k
        
        # Initialize embedder
        self.embedder = HuggingFaceTEIEmbedder(
            base_url=settings.TEI_URL,
            max_batch_size=settings.TEI_MAX_BATCH,
            mode="query",
        )
        
        # Initialize LLM
        self.llm = ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_URL,
            temperature=settings.OLLAMA_TEMPERATURE,
        )

    async def _retrieve_and_format(
        self, db: AsyncSession, query: str, collection_name: str, where: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Retrieve chunks and format context."""
        import time
        start = time.time()
        
        # Embed query (async with internal caching)
        try:
            query_embedding = await self.embedder.embed_query(query)
        except Exception as exc:
            raise EmbeddingError(
                message="Failed to generate query embedding",
                provider="huggingface_tei",
                **get_request_context_data(),
            ) from exc
        
        # Retrieve chunks
        try:
            chunks = await retrieve_chunks(
                db=db,
                embedding=query_embedding,
                collection_name=collection_name,
                top_k=self.top_k,
                where=where,
            )
        except Exception as exc:
            raise VectorStoreError(
                message="Failed to retrieve chunks from vector store",
                operation="query",
                **get_request_context_data(),
            ) from exc
        
        retrieval_time_ms = (time.time() - start) * 1000
        
        # Log retrieval metrics
        top_score = chunks[0]["score"] if chunks else None
        log_retrieval(
            logger,
            query=query,
            num_chunks=len(chunks),
            top_score=top_score,
            retrieval_time_ms=retrieval_time_ms,
        )
        
        # Format context
        context = "\n\n".join(
            f"[{idx + 1}] {chunk['text']}"
            for idx, chunk in enumerate(chunks)
        )
        
        return {
            "context": context,
            "chunks": chunks,
        }

    @retry(
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError)),
    )
    async def _generate_answer(
        self, context: str, question: str
    ) -> str:
        """Generate answer with retry logic, timeout, and LLM response caching."""
        import time

        # ---- LLM cache lookup ----
        cache_key = f"llm:{settings.OLLAMA_MODEL}:{compute_cache_key(context, question, settings.OLLAMA_MODEL, settings.OLLAMA_TEMPERATURE)}"

        if settings.REDIS_ENABLED:
            redis_client = await get_redis_client()
            cache_start = time.time()
            cached = await redis_client.get(cache_key)
            cache_elapsed = (time.time() - cache_start) * 1000

            if cached is not None:
                log_cache_operation(logger, "hit", "llm", cache_key, cache_elapsed)
                return cached

            log_cache_operation(logger, "miss", "llm", cache_key, cache_elapsed)

        # ---- LLM generation ----
        start = time.time()

        # Build LCEL chain
        chain = (
            RunnableParallel(
                context=RunnablePassthrough(),
                question=RunnablePassthrough(),
            )
            | QA_PROMPT_V1
            | self.llm
            | StrOutputParser()
        )

        # Invoke with timeout
        try:
            response = await asyncio.wait_for(
                chain.ainvoke({"context": context, "question": question}),
                timeout=settings.LLM_TIMEOUT,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                "LLM call timed out",
                timeout=settings.LLM_TIMEOUT,
                question=question[:100],
            )
            raise LLMError(
                message=f"LLM response timed out after {settings.LLM_TIMEOUT}s",
                model=settings.OLLAMA_MODEL,
                **get_request_context_data(),
            ) from exc
        except Exception as exc:
            raise LLMError(
                message="Failed to generate answer from LLM",
                model=settings.OLLAMA_MODEL,
                **get_request_context_data(),
            ) from exc

        generation_time_ms = (time.time() - start) * 1000

        # Log generation metrics
        log_generation(
            logger,
            query=question,
            response_length=len(response),
            tokens_used=None,  # Ollama doesn't provide token count easily
            generation_time_ms=generation_time_ms,
        )

        answer = response.strip()

        # ---- Store in cache ----
        if settings.REDIS_ENABLED:
            await redis_client.set(cache_key, answer, ttl=settings.CACHE_TTL_LLM)

        return answer

    async def query(
        self,
        db: AsyncSession,
        question: str,
        collection_name: str,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute RAG query: retrieve + generate.
        
        Args:
            db: Async database session.
            question: User question.
            collection_name: Collection to search in.
            where: Optional metadata filters.
            
        Returns:
            Dictionary with 'answer' and 'sources' keys.
        """
        # Retrieve and format context
        retrieval_result = await self._retrieve_and_format(
            db, question, collection_name, where
        )
        
        if not retrieval_result["chunks"]:
            logger.info("No chunks found for query", question=question[:100])
            return {
                "answer": "I don't know. No relevant information was found.",
                "sources": [],
            }
        
        # Generate answer
        answer = await self._generate_answer(
            retrieval_result["context"],
            question,
        )
        
        # Format sources
        sources = [
            {
                "chunk_id": chunk["id"],
                "score": chunk["score"],
                "metadata": chunk.get("metadata", {}),
            }
            for chunk in retrieval_result["chunks"]
        ]
        
        return {
            "answer": answer,
            "sources": sources,
        }
