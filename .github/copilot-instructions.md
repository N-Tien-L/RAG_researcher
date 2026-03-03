# Role and Context
You are an expert Python Backend & AI Engineer. You are working on "RAG_researcher", a monolithic FastAPI application that integrates RAG (Retrieval-Augmented Generation) flows using LangChain and PostgreSQL (with pgvector).

# Tech Stack & Frameworks
- **Language**: Python 3.12 (Strict type hinting required).
- **Web Framework**: FastAPI.
- **ORM**: SQLAlchemy (Use 2.0 style - Async preferred where applicable).
- **Migrations**: Alembic.
- **RAG Orchestration**: LangChain (Use LCEL - LangChain Expression Language).
- **Vector DB**: PostgreSQL with `pgvector` extension (primary store; `chromadb` is for local notebooks only, not production).
- **Caching**: Redis via `redis-py` (async). Use `RedisCacheClient` from `app/cache/redis_cache.py`.
- **Observability**: OpenTelemetry (tracing → Tempo), Prometheus (metrics), Loki (log shipping), Grafana (dashboards).
- **Data Validation**: Pydantic V2.
- **Testing**: Pytest (with async support via `pytest-asyncio`).
- **Deployment**: Docker-ready (Use environment variables for all configs).

# Project Structure (STRICT ADHERENCE REQUIRED)
```
app/
  ├── api/              # FastAPI routes and dependencies
  │   ├── deps.py       # Dependency injection providers
  │   ├── router.py     # Main API router
  │   └── routes/       # Route handlers (auth, chats, messages, rag, sources, users)
  ├── applications/     # High-level application services (orchestration layer)
  │   ├── chat_service.py
  │   ├── ingestion_service.py
  │   └── rag_service.py
  ├── cache/            # Redis caching layer
  │   ├── redis_cache.py    # RedisCacheClient singleton & compute_cache_key()
  │   └── invalidation.py   # Cache invalidation helpers
  ├── core/             # Core configuration and setup
  │   ├── config.py     # Pydantic settings
  │   ├── lifespan.py   # Application lifespan handlers
  │   └── logging.py    # Logging configuration (structlog)
  ├── db/               # Database layer
  │   ├── models.py     # SQLAlchemy models
  │   ├── schemas.py    # Pydantic schemas
  │   └── sessions.py   # Database session management
  ├── embeddings/       # Embedding generation logic
  │   └── huggingface_tei.py
  ├── ingestion/        # Data ingestion and loading
  │   └── loaders.py
  ├── middleware/       # Starlette/FastAPI middleware
  │   ├── observability.py   # OpenTelemetry trace context + Prometheus HTTP metrics
  │   ├── rate_limit.py      # Sliding-window rate limiting
  │   └── request_context.py # UUID request_id injection (X-Request-ID header)
  ├── observability/    # Metrics and tracing setup
  │   ├── metrics.py    # Prometheus counters, histograms (_REGISTRY)
  │   └── tracing.py    # configure_tracing(), get_tracer(), trace_async_function()
  ├── rag/              # RAG-specific logic (NO business logic here)
  │   ├── chunking.py   # Text chunking strategies
  │   ├── pipeline.py   # RAG pipeline implementation (LCEL chains)
  │   ├── retrieval.py  # Retrieval logic
  │   └── prompts/      # Prompt templates (versioned)
  ├── services/         # Business logic services
  │   ├── auth_service.py
  │   ├── chat_service.py
  │   ├── exceptions.py # Custom exceptions
  │   ├── source_service.py
  │   └── user_service.py
  ├── utils/            # Utility functions
  │   ├── auth.py
  │   ├── files.py
  │   ├── password.py
  │   ├── text.py
  │   └── time.py
  └── vectorstore/      # Vector store implementations
      └── pgvector_store.py
```

**Key Separation Rules**:
- `app/rag/`: Pure RAG logic (chains, retrievers, prompts). NO database calls, NO HTTP handlers.
- `app/services/`: Business logic that may use RAG components. Database interactions allowed.
- `app/applications/`: High-level orchestration between services and RAG.
- `app/api/routes/`: HTTP handlers only. Delegate to `app/applications/` or `app/services/`.
- `app/cache/`: Only Redis I/O. No business logic. Use `get_redis_client()` singleton everywhere.
- `app/observability/`: Only metric/tracer definitions and setup. No business logic.
- `app/middleware/`: Only request/response lifecycle concerns. No service calls.

# Coding Standards

## Naming Conventions
- **Variables, functions, files**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: Prefix with single underscore `_private_method`
- **Type aliases**: `PascalCase` (e.g., `UserDict = dict[str, User]`)

## Type Hinting (MANDATORY)
- Use strict type hints for all function parameters and return values.
- Use `from typing import` or `from collections.abc import` for generic types.
- For async functions, explicitly type return as `Coroutine` or the actual type.
- Example:
  ```python
  async def get_user(user_id: int) -> User | None:
      ...
  ```

## Documentation
- Use Google-style docstrings for all public functions, classes, and modules.
- Include Args, Returns, Raises sections.
- Example:
  ```python
  def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
      """Split text into chunks of specified size.
      
      Args:
          text: Input text to chunk.
          chunk_size: Maximum characters per chunk.
          
      Returns:
          List of text chunks.
          
      Raises:
          ValueError: If chunk_size is less than 1.
      """
  ```

## Error Handling
- Use `try-except` blocks in service/application layers to catch specific exceptions.
- Define custom exceptions in `app/services/exceptions.py`.
- Bubble up custom exceptions to be handled by FastAPI's global exception handlers.
- Always log errors with sufficient context using structured logging.
- Example:
  ```python
  # In service layer
  try:
      result = await some_operation()
  except SpecificError as e:
      logger.error("Operation failed", extra={"user_id": user_id, "error": str(e)})
      raise CustomServiceException(f"Failed to process: {e}") from e
  ```

# FastAPI Best Practices

## Dependency Injection
- Define all dependencies in `app/api/deps.py`.
- Use `Annotated[Type, Depends(dependency)]` for cleaner signatures.
- Example:
  ```python
  # deps.py
  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with async_session_maker() as session:
          yield session
  
  # In route
  async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
      ...
  ```

## Pydantic V2 Features
- Use `ConfigDict` instead of nested `Config` class.
- Use `model_validator`, `field_validator` decorators.
- Leverage `Field()` with `json_schema_extra` for API documentation.
- Example:
  ```python
  from pydantic import BaseModel, Field, ConfigDict, field_validator
  
  class UserCreate(BaseModel):
      model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
      
      email: str = Field(..., json_schema_extra={"example": "user@example.com"})
      
      @field_validator('email')
      @classmethod
      def validate_email(cls, v: str) -> str:
          # validation logic
          return v.lower()
  ```

## Response Models
- Always define explicit response models for routes.
- Use `response_model` parameter in route decorators.
- Use `status_code` for proper HTTP status codes.

## Async Patterns
- Always use `async def` for I/O-bound operations (DB, API calls).
- Use `asyncio.gather()` for concurrent operations.
- Avoid blocking operations in async context (use `asyncio.to_thread()` if needed).

## Middleware Stack
The following middleware is registered in order (outermost → innermost):
1. `RequestContextMiddleware` — generates a UUID `request_id`, binds it to `structlog` context vars, and returns it as the `X-Request-ID` response header.
2. `ObservabilityMiddleware` — manages the OpenTelemetry trace span and records `http_requests_total` / `http_request_duration_seconds` Prometheus metrics. Injects `X-Trace-ID` and `X-Span-ID` response headers.
3. `RateLimitMiddleware` — enforces a per-user / per-IP sliding window limit.

**Rules**:
- Never bypass the middleware stack by calling internal handlers directly.
- `request.state.request_id` is always available inside route handlers.
- Do **not** add additional `structlog.contextvars.bind_contextvars` calls for `request_id`; the middleware handles it.

# SQLAlchemy 2.0 & pgvector Best Practices

## Async Sessions
- Always use `AsyncSession` for database operations.
- Use context managers for session lifecycle.
- Example:
  ```python
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy import select
  
  async def get_user(db: AsyncSession, user_id: int) -> User | None:
      result = await db.execute(select(User).where(User.id == user_id))
      return result.scalar_one_or_none()
  ```

## Connection Pool Management
- Configure connection pool in `app/db/sessions.py`.
- Set appropriate pool size based on expected concurrent connections.
- Use `pool_pre_ping=True` for connection health checks.
- Example:
  ```python
  engine = create_async_engine(
      DATABASE_URL,
      echo=False,
      pool_size=20,
      max_overflow=10,
      pool_pre_ping=True,
      pool_recycle=3600,  # Recycle connections after 1 hour
  )
  ```

## pgvector Integration
- Use `pgvector` extension for vector operations.
- Index vector columns for performance: `CREATE INDEX ON table USING ivfflat (embedding vector_cosine_ops)`.
- Filter by metadata before vector search to reduce search space.
- Example:
  ```python
  from pgvector.sqlalchemy import Vector
  from sqlalchemy import select
  
  # Model
  class DocumentChunk(Base):
      __tablename__ = "document_chunks"
      embedding = Column(Vector(768))  # Specify dimension
  
  # Query with metadata filter
  stmt = (
      select(DocumentChunk)
      .where(DocumentChunk.source_id == source_id)
      .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
      .limit(k)
  )
  ```

# RAG & LangChain Best Practices

## LangChain Expression Language (LCEL)
- **ALWAYS use LCEL** for building chains (avoid legacy `Chain` classes).
- Leverage `|` operator for chaining components.
- Use `RunnablePassthrough`, `RunnableParallel` for complex flows.
- Example:
  ```python
  from langchain_core.runnables import RunnablePassthrough, RunnableParallel
  from langchain_core.output_parsers import StrOutputParser
  
  # Define chain using LCEL
  chain = (
      RunnableParallel(
          context=retriever | format_docs,
          question=RunnablePassthrough()
      )
      | prompt
      | llm
      | StrOutputParser()
  )
  ```

## Async LLM Calls
- Use `ainvoke()`, `astream()` for async invocation.
- Implement timeout handling with `asyncio.wait_for()`.
- Use `tenacity` for retry logic with exponential backoff.
- Example:
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
  import httpx
  
  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=2, max=10),
      retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
  )
  async def call_llm_with_retry(prompt: str) -> str:
      try:
          response = await asyncio.wait_for(
              llm.ainvoke(prompt),
              timeout=30.0  # 30 seconds timeout
          )
          return response
      except asyncio.TimeoutError:
          logger.error("LLM call timed out", extra={"prompt_length": len(prompt)})
          raise
  ```

## Context Window Management
- Track token counts for prompts and responses (use `tiktoken` or model-specific tokenizers).
- Implement truncation strategies for large contexts.
- Prioritize most relevant chunks (use re-ranking if needed).
- Example:
  ```python
  import tiktoken
  
  def truncate_to_token_limit(text: str, max_tokens: int, model: str = "gpt-3.5-turbo") -> str:
      """Truncate text to fit within token limit."""
      encoding = tiktoken.encoding_for_model(model)
      tokens = encoding.encode(text)
      if len(tokens) <= max_tokens:
          return text
      return encoding.decode(tokens[:max_tokens])
  
  # In RAG pipeline
  context_chunks = retriever.get_relevant_documents(query)
  combined_context = "\n\n".join([chunk.page_content for chunk in context_chunks])
  combined_context = truncate_to_token_limit(combined_context, max_tokens=2000)
  ```

## Prompt Management
- Store prompts in `app/rag/prompts/` with versioning.
- Use `ChatPromptTemplate` for structured prompts.
- Include prompt metadata (version, purpose, expected input/output).
- Example:
  ```python
  # app/rag/prompts/qa.py
  from langchain_core.prompts import ChatPromptTemplate
  
  QA_PROMPT_V1 = ChatPromptTemplate.from_messages([
      ("system", "You are a helpful assistant. Use the context to answer questions."),
      ("human", "Context: {context}\n\nQuestion: {question}\n\nAnswer:"),
  ])
  
  # Metadata
  QA_PROMPT_V1.metadata = {
      "version": "1.0",
      "purpose": "Basic Q&A with context",
      "required_inputs": ["context", "question"]
  }
  ```

## Chunking Strategies
- Prefer semantic chunking over fixed-size chunking.
- Use `RecursiveCharacterTextSplitter` with appropriate separators.
- Maintain metadata for chunk provenance (source, page, position).
- Implement overlap for context continuity.
- Example:
  ```python
  from langchain.text_splitter import RecursiveCharacterTextSplitter
  
  splitter = RecursiveCharacterTextSplitter(
      chunk_size=1000,
      chunk_overlap=200,
      separators=["\n\n", "\n", ". ", " ", ""],
      length_function=len,
  )
  
  chunks = splitter.split_text(document.content)
  # Attach metadata to each chunk
  chunk_docs = [
      {"content": chunk, "source_id": doc.id, "chunk_index": i}
      for i, chunk in enumerate(chunks)
  ]
  ```

## Retrieval Optimization
- Implement hybrid search (vector + keyword) when appropriate.
- Use metadata filters to reduce search space.
- Consider re-ranking retrieved chunks (e.g., cross-encoder models).
- Cache frequently accessed embeddings.

# Logging & Observability

## Structured Logging
- Obtain a logger via `get_logger(__name__)` from `app.core.logging` — never use `logging.getLogger()` directly.
- `request_id` and `user_id` are bound automatically by `RequestContextMiddleware`; do not re-bind them in route handlers.
- Use `info` for high-level operational events and `error` with full context variables for exceptions.
- Example:
  ```python
  from app.core.logging import get_logger
  
  logger = get_logger(__name__)
  
  # In RAG pipeline
  logger.info(
      "rag_query_executed",
      query=query,
      num_chunks_retrieved=len(chunks),
      response_length=len(response),
      latency_ms=latency,
  )
  
  logger.error(
      "rag_query_failed",
      query=query,
      error=str(exc),
      exc_info=True,
  )
  ```

## RAG-Specific Logging
- Log retrieval metrics (number of chunks, similarity scores).
- Log generation metrics (tokens used, latency).
- Log errors with full context (query, retrieved chunks, error type).
- Example:
  ```python
  # In app/rag/pipeline.py
  logger.info(
      "retrieval_completed",
      query=query,
      num_chunks=len(chunks),
      top_score=chunks[0].score if chunks else None,
      retrieval_time_ms=retrieval_time,
  )
  
  logger.info(
      "generation_completed",
      query=query,
      response_length=len(response),
      tokens_used=token_count,
      generation_time_ms=generation_time,
  )
  ```

## OpenTelemetry Tracing
- Call `get_tracer(__name__)` from `app.observability.tracing` **once at module level**.
- Wrap significant operations (retrieval, generation, DB writes) in a span.
- Add business-relevant attributes with `span.set_attribute()`.
- Prefer the `@trace_async_function("span_name")` decorator for entire async functions.
- Example:
  ```python
  from app.observability.tracing import get_tracer, trace_async_function, add_span_attributes
  
  tracer = get_tracer(__name__)
  
  # Context-manager style for a code block
  async def retrieve_docs(query: str) -> list[Document]:
      with tracer.start_as_current_span("rag.retrieve") as span:
          span.set_attribute("rag.query", query)
          docs = await _do_retrieval(query)
          span.set_attribute("rag.num_docs", len(docs))
          return docs
  
  # Decorator style for a whole function
  @trace_async_function("rag.generate")
  async def generate_answer(context: str, question: str) -> str:
      add_span_attributes(rag_model=settings.LLM_MODEL)
      return await llm.ainvoke(...)
  ```

## Prometheus Metrics
- Use **only** the pre-defined counters and histograms in `app/observability/metrics.py`.
- Register new application-level metrics in that same file inside `_REGISTRY`.
- Always supply all required label values when recording observations.
- Example:
  ```python
  from app.observability.metrics import (
      rag_queries_total,
      rag_query_duration_seconds,
  )
  import time
  
  start = time.perf_counter()
  try:
      result = await run_rag_pipeline(query, collection_name)
      rag_queries_total.labels(collection_name=collection_name, status="success").inc()
  except Exception:
      rag_queries_total.labels(collection_name=collection_name, status="error").inc()
      raise
  finally:
      rag_query_duration_seconds.labels(collection_name=collection_name).observe(
          time.perf_counter() - start
      )
  ```

# Caching Best Practices

## Redis Client
- Always use the module-level `get_redis_client()` from `app.cache.redis_cache` — never construct `RedisCacheClient` directly outside of `lifespan.py`.
- The client connects lazily; connection is verified in `lifespan.py` via `connect()`.
- Graceful failure is built-in: all methods return `None` / `False` / `0` when Redis is unavailable. Do **not** add extra `try-except` wrappers around cache calls.
- Example:
  ```python
  from app.cache.redis_cache import get_redis_client, compute_cache_key
  import json
  
  async def get_cached_embedding(text: str) -> list[float] | None:
      cache = await get_redis_client()
      key = compute_cache_key("embedding", text)
      raw = await cache.get(key)
      return json.loads(raw) if raw else None
  
  async def set_cached_embedding(
      text: str, embedding: list[float], ttl: int = 3600
  ) -> None:
      cache = await get_redis_client()
      key = compute_cache_key("embedding", text)
      await cache.set(key, json.dumps(embedding), ttl=ttl)
  ```

## Key Naming
- Use `compute_cache_key(*args, **kwargs)` to generate deterministic SHA-256 hash keys for complex inputs.
- Do **not** manually prepend `settings.CACHE_KEY_PREFIX`; `RedisCacheClient._make_key()` handles it.
- Adopt a consistent namespace prefix pattern in your arguments: `("namespace", primary_input)`.

## Cache Invalidation
- Use `clear_pattern(pattern)` for bulk invalidation (e.g., after a source document is re-ingested).
- Provide the pattern **without** the global prefix (it is added automatically).
- Example:
  ```python
  from app.cache.redis_cache import get_redis_client
  
  async def invalidate_source_cache(source_id: str) -> None:
      cache = await get_redis_client()
      deleted = await cache.clear_pattern(f"source:{source_id}:*")
      logger.info("cache_invalidated", source_id=source_id, keys_deleted=deleted)
  ```

## Serialization
- Redis stores strings only. Serialize/deserialize complex objects with `json.dumps` / `json.loads`.
- For binary data (e.g., raw embeddings), use `base64` encoding before storing.

# Testing Guidelines

## Test Structure
- Place tests in `tests/` directory mirroring `app/` structure.
- Use `pytest-asyncio` for async tests.
- Use fixtures for common setup (DB sessions, mock clients).

## RAG Testing
- Test retrieval independently from generation.
- Mock LLM calls in integration tests.
- Test chunking strategies with real documents.
- Example:
  ```python
  # tests/test_rag_retrieval_pipeline.py
  import pytest
  from app.rag.retrieval import retrieve_chunks
  
  @pytest.mark.asyncio
  async def test_retrieval_returns_relevant_chunks(mock_db_session):
      query = "What is RAG?"
      chunks = await retrieve_chunks(mock_db_session, query, k=5)
      
      assert len(chunks) <= 5
      assert all(chunk.content for chunk in chunks)
      assert all(chunk.score >= 0 for chunk in chunks)
  ```

# Docker & Environment

## Configuration Management
- Use `pydantic_settings.BaseSettings` in `app/core/config.py`.
- All secrets via environment variables (never hardcode).
- Provide sensible defaults for development.
- Example:
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict
  
  class Settings(BaseSettings):
      model_config = SettingsConfigDict(
          env_file=".env",
          env_file_encoding="utf-8",
          case_sensitive=False
      )
      
      # Database
      DATABASE_URL: str
      DB_POOL_SIZE: int = 20
      DB_MAX_OVERFLOW: int = 10
      
      # LLM API
      LLM_API_URL: str
      LLM_API_KEY: str | None = None
      LLM_TIMEOUT: int = 30
      
      # Embeddings
      EMBEDDING_API_URL: str
      EMBEDDING_DIM: int = 768
  ```

## Path Handling
- Use `pathlib.Path` for all file operations.
- Ensure cross-platform compatibility (Windows/Linux).
- Example:
  ```python
  from pathlib import Path
  
  BASE_DIR = Path(__file__).resolve().parent.parent
  DATA_DIR = BASE_DIR / "data"
  MODELS_DIR = BASE_DIR / "models"
  
  # Ensure directory exists
  DATA_DIR.mkdir(parents=True, exist_ok=True)
  ```

# Output Instructions

## Code Generation
- **Always include necessary imports** at the top of code snippets.
- If a change affects multiple files, list changes for each file separately.
- Provide file paths relative to project root.
- Respect the project structure strictly (see Project Structure section).

## Multi-File Changes
When adding a new feature (e.g., new endpoint), provide changes in this order:
1. **Database Model** (`app/db/models.py`)
2. **Pydantic Schema** (`app/db/schemas.py`)
3. **Service Logic** (`app/services/`)
4. **API Route** (`app/api/routes/`)
5. **Tests** (`tests/`)

## Code Style
- Prefer modular, reusable components over monolithic functions.
- Single Responsibility Principle: Each function should do one thing well.
- Avoid deep nesting (max 3 levels).
- Use early returns to reduce complexity.

## Documentation
- Include inline comments for complex logic.
- Update docstrings when modifying functions.
- Provide usage examples in docstrings for public APIs.