# RAG_researcher

## Structure

- app/main.py - Streamlit entrypoint for ingestion demo
- app/rag/ - Chunking and pipeline stubs
- app/ingestion/ - PDF/YouTube extraction helpers
- app/core/ - Config and logging utilities
- app/utils/ - Shared helpers (text, files, time)
- tests/ - Unit/integration tests

## Quickstart

1. Install deps: `pip install -e .`
2. Run the API: `uvicorn app.main:app --reload`
3. Optionally set `SECRET_KEY` and `ACCESS_TOKEN_EXPIRE_MINUTES` in `.env` to configure JWTs.

### API authentication

- Register a user via `POST /api/users`.
- Log in with `POST /api/auth/login` (email + password) to receive an access token.
- Authorize subsequent requests with header `Authorization: Bearer <token>`; check the active user with `GET /api/auth/me`.

### Rate Limiting

The API implements sliding window rate limiting to protect against abuse. Configure via environment variables:

```bash
# Rate Limiting Configuration
RATE_LIMIT_ENABLED=true                    # Enable/disable rate limiting (default: true)
RATE_LIMIT_PER_MINUTE=60                   # Maximum requests per minute per user (default: 60)
RATE_LIMIT_WINDOW_SECONDS=60               # Time window in seconds (default: 60)
RATE_LIMIT_CLEANUP_INTERVAL=300            # Cleanup interval for old entries in seconds (default: 300)
```

**Rate limit behavior:**
- Authenticated requests are limited per user (extracted from JWT token)
- Unauthenticated requests are limited per IP address
- When exceeded, API returns HTTP 429 with `Retry-After` header
- All responses include rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

**Recommended values:**
- **Development**: `RATE_LIMIT_PER_MINUTE=300` (higher limit for testing)
- **Production**: `RATE_LIMIT_PER_MINUTE=60` (balanced protection)
- **Strict**: `RATE_LIMIT_PER_MINUTE=30` (high-security environments)
