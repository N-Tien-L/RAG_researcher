# Architecture

## System Overview

RAG Researcher is composed of the following major components:

| Component | Role |
|---|---|
| **FastAPI app** | Async HTTP API, middleware chain, lifespan management |
| **Application Services** | Orchestration layer that composes lower-level services into use-case workflows |
| **RAG Pipeline** | LangChain LCEL chain for query embedding → vector retrieval → LLM generation |
| **Ingestion Pipeline** | Extraction → chunking → embedding → pgvector insert with hash deduplication |
| **pgvector (PostgreSQL)** | Persistent vector store and relational data (users, chats, sources, chunks) |
| **Redis** | TTL-based cache for embeddings and LLM responses |
| **HuggingFace TEI** | Self-hosted text embeddings inference server |
| **Ollama / Kaggle LitServe** | Interchangeable LLM backends, selected by `LLM_PROVIDER` env var |
| **Observability Stack** | Prometheus + Tempo (OTLP) + Loki + Grafana for metrics, traces, and logs |

## Component Diagram

```mermaid
graph TD
    Client["Client (HTTP)"]
    FastAPI["FastAPI (main.py)"]
    Middleware["Middleware Stack<br/>(Observability · RateLimit · RequestContext)"]
    Routes["Routes (api/routes/)"]
    AppSvc["Application Services<br/>(applications/)"]
    SvcLayer["Service Layer<br/>(services/)"]
    RAG["RAG Pipeline<br/>(rag/pipeline.py)"]
    Ingest["Ingestion Pipeline<br/>(ingestion/ + applications/)"]
    TEI["HuggingFace TEI<br/>(external)"]
    PGVector["pgvector<br/>(PostgreSQL)"]
    Redis["Redis Cache"]
    LLM["LLM Backend<br/>(Ollama or Kaggle)"]
    Prom["Prometheus"]
    Tempo["Tempo (OTLP)"]
    Loki["Loki"]
    Grafana["Grafana"]

    Client --> FastAPI
    FastAPI --> Middleware
    Middleware --> Routes
    Routes --> AppSvc
    Routes --> SvcLayer
    AppSvc --> RAG
    AppSvc --> Ingest
    AppSvc --> SvcLayer
    RAG --> TEI
    RAG --> PGVector
    RAG --> Redis
    RAG --> LLM
    Ingest --> TEI
    Ingest --> PGVector
    SvcLayer --> PGVector
    FastAPI --> Prom
    FastAPI --> Tempo
    FastAPI --> Loki
    Prom --> Grafana
    Tempo --> Grafana
    Loki --> Grafana
```

## Ingestion Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as API Route
    participant AppSvc as IngestionApplicationService
    participant Loader as Loaders (PDF/YouTube)
    participant Chunker as Chunking
    participant TEI as HuggingFace TEI
    participant PG as pgvector

    Client->>API: POST /api/sources/{id}/process
    API->>AppSvc: process_source(source_id, source, source_type)
    AppSvc->>PG: get_existing_file_hash(source_id)
    alt Hash matches (unchanged)
        AppSvc-->>API: {status: "skipped"}
    else New or modified source
        AppSvc->>Loader: extract_from_pdf / extract_from_youtube
        Loader-->>AppSvc: extraction dict (text, page_texts/segments, metadata)
        AppSvc->>Chunker: chunk_pdf_extraction / chunk_youtube_extraction
        Chunker-->>AppSvc: list[{id, text, metadata}]
        AppSvc->>TEI: embed_documents(texts)
        TEI-->>AppSvc: list[list[float]]
        AppSvc->>PG: insert_chunks(chunks, embeddings, source_id, file_hash)
        PG-->>AppSvc: inserted count
        AppSvc-->>API: {status: "ingested", chunks_added: N}
    end
    API-->>Client: SourceProcessResponse
```

## RAG Query Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as API Route
    participant AppSvc as RAGApplicationService
    participant Pipeline as RAGPipeline
    participant Redis
    participant TEI as HuggingFace TEI
    participant PG as pgvector
    participant LLM as LLM Backend

    Client->>API: POST /api/rag/query
    API->>AppSvc: query(question, collection_name, source_id)
    AppSvc->>Pipeline: query(db, question, collection_name, where, chat_history)
    Pipeline->>Redis: get(embedding:query:{hash})
    alt Cache hit
        Redis-->>Pipeline: cached embedding
    else Cache miss
        Pipeline->>TEI: embed_query(question)
        TEI-->>Pipeline: query_embedding
        Pipeline->>Redis: set(embedding:query:{hash}, ttl=3600)
    end
    Pipeline->>PG: query_chunks(embedding, collection_name, top_k, where)
    PG-->>Pipeline: list[{chunk_id, text, score, metadata}]
    Pipeline->>Redis: get(llm:{model}:{hash})
    alt LLM cache hit
        Redis-->>Pipeline: cached answer
    else LLM cache miss
        Pipeline->>LLM: ainvoke(QA_CONVERSATIONAL_PROMPT_V1)
        LLM-->>Pipeline: answer string
        Pipeline->>Redis: set(llm:{model}:{hash}, ttl=1800)
    end
    Pipeline-->>AppSvc: {answer, sources}
    AppSvc-->>API: {answer, sources}
    API-->>Client: RAGQueryResponse
```

## Technology Choices

| Component | Technology | Reason |
|---|---|---|
| API framework | FastAPI | Async-native, auto OpenAPI docs |
| LLM orchestration | LangChain LCEL | Composable async chains |
| Vector store | pgvector (PostgreSQL) | No extra infra, SQL joins |
| Embeddings | HuggingFace TEI | Self-hosted, batched |
| LLM | Ollama / Kaggle LitServe | Switchable via `LLM_PROVIDER` |
| Cache | Redis | Embedding + LLM response TTL |
| Observability | Prometheus + Tempo + Loki + Grafana | Full metrics/traces/logs |
| ORM | SQLAlchemy (async) + asyncpg | Native async with pgvector support |
| Settings | pydantic-settings | Env var validation with `.env` |
