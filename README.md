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