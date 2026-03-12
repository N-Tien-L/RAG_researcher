# Contributing

## Local Dev Setup (without Docker)

```bash
# Clone and enter the backend
git clone <repo-url>
cd RAG_researcher/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Configure environment
cp ../.env.example ../.env
# Edit .env — set SECRET_KEY, DATABASE_URL, TEI_URL at minimum
```

You will still need PostgreSQL with the pgvector extension and Redis running. The easiest way is to start only those services via Docker Compose:

```bash
docker compose up postgres redis -d
```

Then apply migrations:

```bash
alembic upgrade head
```

## Running Tests

```bash
# From the backend/ directory
pytest

# With coverage
pytest --cov=app --cov-report=html

# Run a specific test file
pytest tests/test_chunking.py -v
```

### Test Structure

| Directory | Coverage |
|---|---|
| `tests/api/` | Route-level HTTP tests (FastAPI `TestClient`) |
| `tests/applications/` | Application service integration tests |
| `tests/services/` | Service layer unit tests |
| `tests/rag/` | RAG pipeline and chunking tests |
| `tests/cache/` | Redis cache tests |
| `tests/middleware/` | Rate limiting and observability middleware tests |
| `tests/core/` | Config and logging tests |
| `tests/utils/` | Utility function tests |
| `tests/e2e/` | End-to-end scenarios |

## Code Conventions

### Logging

Use `structlog` with the module-level logger:

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

# Bind structured key-value pairs
logger.info("ingestion_started", source_id=source_id, source_type=source_type)
logger.warning("cache_miss", cache_key=cache_key)
logger.error("embedding_failed", error=str(exc), provider="tei")
```

### Async Patterns

- Use `AsyncSession` from `app.db.sessions.get_db()` for all database operations
- Use `asyncio.wait_for()` for LLM calls with explicit timeout: `asyncio.wait_for(coro, timeout=settings.LLM_TIMEOUT)`
- Use `asyncio.to_thread()` for synchronous HTTP calls (e.g., TEI requests in `HuggingFaceTEIEmbedder`)

### Exception Hierarchy

Always raise domain-specific subclasses. The hierarchy is:

```
Exception
├── ServiceError          → ResourceNotFound, ResourceConflict
├── AuthenticationError   → invalid credentials / token
├── RateLimitExceeded     → sliding window exceeded
└── BaseApplicationError  → IngestionError, EmbeddingError, VectorStoreError, LLMError
```

```python
# Correct — raise domain error
raise ResourceNotFound(f"Source {source_id} not found")

# Correct — wrap lower-level errors
raise IngestionError(
    message="Failed to extract content",
    stage="extraction",
    source_id=source_id,
    **get_request_context_data(),
) from exc
```

## Adding New Routes

1. Create a router file in `backend/app/api/routes/my_resource.py`:

```python
"""My resource endpoints."""

from fastapi import APIRouter, Depends
from app.api import deps

router = APIRouter(prefix="/my-resource", tags=["my-resource"])

@router.get("/")
async def list_my_resource(
    current_user = Depends(deps.current_user),
):
    """List resources for current user."""
    ...
```

2. Add dependencies via `backend/app/api/deps.py`:

```python
def my_service(db: Annotated[AsyncSession, Depends(db_session)]) -> MyService:
    """Dependency to inject MyService."""
    return MyService(db)
```

3. Register the router in `backend/app/api/router.py`:

```python
from app.api.routes.my_resource import router as my_resource_router
api_router.include_router(my_resource_router)
```

## Adding New Services

Follow the pattern in `backend/app/services/`:

```python
"""Business logic for my resource."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.exceptions import ResourceNotFound, ResourceConflict

class MyResourceService:
    """Service layer for my resource operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_resource(self, resource_id: UUID) -> MyResourceRead:
        """Get resource by ID.

        Args:
            resource_id: Resource UUID.

        Returns:
            Resource data.

        Raises:
            ResourceNotFound: If the resource does not exist.
        """
        resource = await self.db.get(MyResource, resource_id)
        if not resource:
            raise ResourceNotFound(f"Resource {resource_id} not found")
        return MyResourceRead.model_validate(resource)
```

- Constructor must accept `db: AsyncSession`
- Raise `ResourceNotFound` for missing records
- Raise `ResourceConflict` for uniqueness violations
- Never expose SQLAlchemy models outside the service — always return Pydantic schemas
