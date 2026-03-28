# Deployment

## Prerequisites

- **Docker** ≥ 24
- **Docker Compose** v2 (`docker compose` CLI)
- **HuggingFace TEI server** — external service pointed to by `TEI_URL`; the application does not start TEI itself

## Docker Compose Service Map

| Service | Image | Internal Port | Description |
|---|---|---|---|
| `frontend` | local Dockerfile | 3000 | Next.js frontend |
| `rag-app` | local Dockerfile | 8000 | FastAPI backend |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | PostgreSQL + pgvector extension |
| `redis` | `redis:7-alpine` | 6379 | Cache |
| `ollama` | `ollama/ollama` | 11434 | Local LLM backend |
| `loki` | `grafana/loki` | 3100 | Log aggregation |
| `prometheus` | `prom/prometheus` | 9090 | Metrics scrape |
| `grafana` | `grafana/grafana` | 3002 (host) / 3000 (container) | Dashboards (admin/admin) |

## Quick Start

```bash
# Clone and enter project
git clone <repo-url>
cd RAG_researcher

# Configure environment
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY, POSTGRES_PASSWORD, TEI_URL

# Start services
docker compose up -d

# Run migrations
docker compose exec rag-app alembic upgrade head

# Access app surfaces
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# Grafana: http://localhost:3002
```

## Environment Variables Reference

### App

| Variable | Default | Description |
|---|---|---|
| `PROJECT_NAME` | `RAG Researcher API` | Application name in OpenAPI docs |
| `VERSION` | `0.1.0` | API version string |
| `API_PREFIX` | `/api` | URL prefix for all API routes |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend API base URL (set in `frontend` container) |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | Full override URL (takes precedence over component fields) |
| `POSTGRES_USER` | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `changeme` | PostgreSQL password |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `my_rag_db` | Database name |
| `DB_POOL_SIZE` | `20` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `10` | Maximum overflow connections above pool size |

### Embeddings

| Variable | Default | Description |
|---|---|---|
| `TEI_URL` | `http://localhost:8080` | HuggingFace TEI server base URL |
| `TEI_MAX_BATCH` | `8` | Maximum texts per embedding batch |
| `TEI_MODE` | `passage` | Default mode (`passage` for docs, `query` for search) |
| `EMBEDDING_DIM` | `384` | Embedding vector dimension |

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | LLM backend: `ollama` or `kaggle` |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model name |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TEMPERATURE` | `0.2` | Sampling temperature for Ollama |
| `KAGGLE_LLM_URL` | — | Kaggle LitServe tunnel URL (required when `LLM_PROVIDER=kaggle`) |
| `KAGGLE_LLM_API_KEY` | — | Bearer token for Kaggle LitServe |
| `KAGGLE_LLM_MAX_TOKENS` | `1024` | Max tokens for Kaggle LLM |
| `KAGGLE_LLM_TEMPERATURE` | `0.2` | Sampling temperature for Kaggle LLM |
| `LLM_TIMEOUT` | `90` | LLM request timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Retry attempts on transient LLM errors |
| `CHAT_HISTORY_MAX_TURNS` | `10` | Maximum chat turn pairs passed to LLM context |

### Auth

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key — **required in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token TTL in minutes |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |

### Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max requests per minute per identity |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window size in seconds |
| `RATE_LIMIT_CLEANUP_INTERVAL` | `300` | Interval in seconds to purge expired entries |

### Redis Cache

| Variable | Default | Description |
|---|---|---|
| `REDIS_ENABLED` | `true` | Enable Redis caching |
| `REDIS_URL` | `redis://localhost:6379/0` | Full Redis URL (takes precedence if non-default) |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | — | Redis password (if auth enabled) |
| `CACHE_TTL_EMBEDDINGS` | `3600` | TTL in seconds for embedding cache entries |
| `CACHE_TTL_LLM` | `1800` | TTL in seconds for LLM response cache entries |
| `CACHE_KEY_PREFIX` | `rag_cache` | Prefix for all Redis keys |

### Observability

| Variable | Default | Description |
|---|---|---|
| `ENABLE_METRICS` | `true` | Enable Prometheus metrics at `/metrics` |
| `ENABLE_TRACING` | `true` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `rag-researcher` | Service name in traces |
| `OTEL_EXPORTER_TYPE` | `otlp` | Exporter type: `otlp` or `console` |
| `OTLP_ENDPOINT` | `http://tempo:4317` | OTLP gRPC collector endpoint |
| `OTEL_TRACE_SAMPLE_RATE` | `1.0` | Fraction of traces to sample (0.0–1.0) |
| `METRICS_SLOW_QUERY_THRESHOLD_MS` | `100` | DB query duration threshold for slow-query warnings |
| `LOKI_ENABLED` | `true` | Enable Loki log shipping |
| `LOKI_ENDPOINT` | `http://loki:3100` | Loki push endpoint |

### File Uploads

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `./uploads` | Directory for uploaded PDF files (auto-created on startup) |

## LLM Provider Switching

Set `LLM_PROVIDER` in `.env` to switch backends without code changes:

**Ollama (default)** — runs locally via Docker Compose:
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
OLLAMA_URL=http://ollama:11434   # service name in docker-compose
```

**Kaggle LitServe** — requires an active Kaggle notebook with a LitServe tunnel:
```bash
LLM_PROVIDER=kaggle
KAGGLE_LLM_URL=https://your-tunnel.localhost.run
KAGGLE_LLM_API_KEY=your-litserve-api-key
```

Both backends implement LangChain `BaseChatModel` and are interchangeable at the pipeline level.

## Database Migrations

Migrations are managed with Alembic. Four migration files exist in `backend/alembic/versions/`:

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1

# Check current revision
alembic current
```

## Dev Container

A `.devcontainer/` setup is available for VS Code. Open the project in a Dev Container to get a reproducible environment with all dependencies pre-installed.

## Upload Directory

The `UPLOAD_DIR` directory is created automatically on application startup via the `ensure_directory()` helper in `lifespan.py`. PDF files uploaded via `POST /api/sources/upload` are stored here with UUID-based filenames.
