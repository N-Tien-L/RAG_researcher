"""Async RAG pipeline using LangChain Expression Language (LCEL)."""

import asyncio
import time
from typing import Any

import httpx
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.llm.kaggle_client import KaggleChatModel
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
from app.observability.metrics import (
    record_cache_operation,
    record_embedding,
    record_rag_query,
)
from app.observability.tracing import add_span_attributes, add_span_event, trace_context_manager
from app.rag.prompts.qa import QA_CONVERSATIONAL_PROMPT_V1
from app.db import schemas as db_schemas
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
        
        # Initialize LLM based on configured provider
        if settings.LLM_PROVIDER == "kaggle":
            self.llm = KaggleChatModel(
                api_url=settings.KAGGLE_LLM_URL,
                api_key=settings.KAGGLE_LLM_API_KEY,
                max_tokens=settings.KAGGLE_LLM_MAX_TOKENS,
                temperature=settings.KAGGLE_LLM_TEMPERATURE,
                timeout=float(settings.LLM_TIMEOUT),
            )
        else:
            self.llm = ChatOllama(
                model=settings.OLLAMA_MODEL,
                base_url=settings.OLLAMA_URL,
                temperature=settings.OLLAMA_TEMPERATURE,
            )

    async def _retrieve_and_format(
        self, db: AsyncSession, query: str, collection_name: str, where: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Retrieve chunks and format context."""
        retrieval_start = time.perf_counter()

        with trace_context_manager(
            "rag.retrieval",
            {
                "collection_name": collection_name,
                "top_k": self.top_k,
                "query": query[:200],
            },
        ):
            # Embed query (async with internal caching)
            try:
                with trace_context_manager(
                    "rag.embed_query",
                    {"provider": "huggingface_tei", "mode": "query"},
                ):
                    embed_start = time.perf_counter()
                    query_embedding = await self.embedder.embed_query(query)
                    embed_duration = time.perf_counter() - embed_start
                    record_embedding(
                        provider="huggingface_tei",
                        mode="query",
                        duration_seconds=embed_duration,
                        batch_size=1,
                    )
            except Exception as exc:
                raise EmbeddingError(
                    message="Failed to generate query embedding",
                    provider="huggingface_tei",
                    **get_request_context_data(),
                ) from exc

            # Retrieve chunks
            try:
                with trace_context_manager(
                    "rag.vector_search",
                    {"collection_name": collection_name},
                ):
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

        retrieval_time_ms = (time.perf_counter() - retrieval_start) * 1000
        
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
            "retrieval_time_seconds": retrieval_time_ms / 1000,
        }

    @staticmethod
    def _to_langchain_messages(history: list[db_schemas.ChatMessageRead]) -> list[BaseMessage]:
        """Convert DB chat messages to LangChain message objects.

        Skips system-role messages — those are owned by the prompt template.

        Args:
            history: Ordered list of ChatMessageRead from the database.

        Returns:
            List of HumanMessage / AIMessage instances.
        """
        result: list[BaseMessage] = []
        for msg in history:
            if msg.role == db_schemas.ChatRole.user:
                result.append(HumanMessage(content=msg.content))
            elif msg.role == db_schemas.ChatRole.assistant:
                result.append(AIMessage(content=msg.content))
            # system role skipped — handled by the prompt template
        return result

    @retry(
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (asyncio.TimeoutError, ConnectionError, httpx.TimeoutException, httpx.ConnectError)
        ),
    )
    async def _generate_answer(
        self, context: str, question: str, chat_history: list[BaseMessage] | None = None
    ) -> tuple[str, float]:
        """Generate answer with retry logic, timeout, and LLM response caching.

        Args:
            context: Formatted RAG document chunks.
            question: Current user question.
            chat_history: Prior conversation turns as LangChain messages.
        """
        if chat_history is None:
            chat_history = []

        # Build a provider-agnostic cache key
        if settings.LLM_PROVIDER == "kaggle":
            _model_id = f"kaggle:{settings.KAGGLE_LLM_URL}"
            _temperature = settings.KAGGLE_LLM_TEMPERATURE
        else:
            _model_id = settings.OLLAMA_MODEL
            _temperature = settings.OLLAMA_TEMPERATURE

        history_fingerprint = str([m.content for m in chat_history])
        cache_key = (
            f"llm:{_model_id}:"
            f"{compute_cache_key(context, question, history_fingerprint, _model_id, _temperature)}"
        )

        with trace_context_manager(
            "rag.generation",
            {
                "model": _model_id,
                "temperature": _temperature,
                "context_length": len(context),
            },
        ):
            # ---- LLM cache lookup ----
            if settings.REDIS_ENABLED:
                redis_client = await get_redis_client()
                cache_start = time.perf_counter()
                cached = await redis_client.get(cache_key)
                cache_elapsed = time.perf_counter() - cache_start

                if cached is not None:
                    log_cache_operation(logger, "hit", "llm", cache_key, cache_elapsed * 1000)
                    record_cache_operation("get", "llm", cache_elapsed, True)
                    add_span_event("cache.hit", {"cache_type": "llm"})
                    return cached, 0.0

                log_cache_operation(logger, "miss", "llm", cache_key, cache_elapsed * 1000)
                record_cache_operation("get", "llm", cache_elapsed, False)
                add_span_event("cache.miss", {"cache_type": "llm"})

            # ---- LLM generation ----
            start = time.perf_counter()

            # Build LCEL chain
            chain = QA_CONVERSATIONAL_PROMPT_V1 | self.llm | StrOutputParser()

            # Invoke with timeout
            try:
                with trace_context_manager("rag.llm_invoke"):
                    response = await asyncio.wait_for(
                        chain.ainvoke({
                            "context": context, 
                            "question": question,
                            "chat_history": chat_history
                            }),
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
                    model=_model_id,
                    **get_request_context_data(),
                ) from exc
            except Exception as exc:
                raise LLMError(
                    message="Failed to generate answer from LLM",
                    model=_model_id,
                    **get_request_context_data(),
                ) from exc

            generation_time_seconds = time.perf_counter() - start

            # Log generation metrics
            log_generation(
                logger,
                query=question,
                response_length=len(response),
                tokens_used=None,
                generation_time_ms=generation_time_seconds * 1000,
            )

            answer = response.strip()

            # ---- Store in cache ----
            if settings.REDIS_ENABLED:
                await redis_client.set(cache_key, answer, ttl=settings.CACHE_TTL_LLM)

            return answer, generation_time_seconds

    async def query(
        self,
        db: AsyncSession,
        question: str,
        collection_name: str,
        where: dict[str, Any] | None = None,
        chat_history: list[BaseMessage] | None = None,
    ) -> dict[str, Any]:
        """Execute RAG query: retrieve + generate.

        Args:
            db: Async database session.
            question: User question.
            collection_name: Collection to search in.
            where: Optional metadata filters.
            chat_history: Prior conversation turns as LangChain messages.

        Returns:
            Dictionary with 'answer' and 'sources' keys.
        """
        query_start = time.perf_counter()
        with trace_context_manager(
            "rag.query",
            {
                "collection_name": collection_name,
                "question": question[:200],
            },
        ):
            # Retrieve and format context
            retrieval_result = await self._retrieve_and_format(
                db, question, collection_name, where
            )

            if not retrieval_result["chunks"]:
                logger.info("No chunks found for query", question=question[:100])
                record_rag_query(
                    collection=collection_name,
                    duration_seconds=time.perf_counter() - query_start,
                    retrieval_seconds=retrieval_result["retrieval_time_seconds"],
                    generation_seconds=0.0,
                    status="empty",
                )
                return {
                    "answer": "I don't know. No relevant information was found.",
                    "sources": [],
                }

            # Generate answer
            answer, generation_time_seconds = await self._generate_answer(
                retrieval_result["context"],
                question,
                chat_history=chat_history or []
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

            total_duration = time.perf_counter() - query_start
            record_rag_query(
                collection=collection_name,
                duration_seconds=total_duration,
                retrieval_seconds=retrieval_result["retrieval_time_seconds"],
                generation_seconds=generation_time_seconds,
                status="success",
            )
            add_span_attributes(
                num_sources=len(sources),
                answer_length=len(answer),
            )

            return {
                "answer": answer,
                "sources": sources,
            }