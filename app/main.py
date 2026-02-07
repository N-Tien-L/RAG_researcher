from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from app.api.deps import current_user
from app.cache.invalidation import (
    get_cache_stats,
    invalidate_all_embeddings,
    invalidate_all_llm,
)
from app.core.config import settings
from app.core.lifespan import lifespan
from app.api.router import api_router
from app.db import schemas
from app.middleware.request_context import RequestContextMiddleware
from app.services.exceptions import (
    AuthenticationError,
    BaseApplicationError,
    EmbeddingError,
    IngestionError,
    LLMError,
    RateLimitExceeded,
    ResourceConflict,
    ResourceNotFound,
    VectorStoreError,
)
from app.middleware.rate_limit import RateLimitMiddleware

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan
    )

    # -------------------------
    # Middleware
    # -------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware
    app.add_middleware(RateLimitMiddleware, settings=settings)

    # Request context middleware
    app.add_middleware(RequestContextMiddleware)

    # -------------------------
    # Routes
    # -------------------------
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # -------------------------
    # Exception Handlers
    # -------------------------
    @app.exception_handler(ResourceNotFound)
    async def not_found_handler(request: Request, exc: ResourceNotFound):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)}
        )

    @app.exception_handler(ResourceConflict)
    async def conflict_handler(request: Request, exc: ResourceConflict):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)}
        )

    @app.exception_handler(AuthenticationError)
    async def auth_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc)}
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        import time
        reset_time = int(time.time() + settings.RATE_LIMIT_WINDOW_SECONDS)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc)},
            headers={
                "Retry-After": str(exc.retry_after),
                "X-RateLimit-Limit": str(exc.limit),
                "X-RateLimit-Remaining": str(exc.remaining),
                "X-RateLimit-Reset": str(reset_time),
            }
        )

    def get_request_context(request: Request) -> dict:
        """Extract request context for error responses."""
        contextvars = structlog.contextvars.get_contextvars()
        request_id = getattr(request.state, "request_id", None) or contextvars.get("request_id")
        user_id = contextvars.get("user_id")
        return {
            "request_id": request_id,
            "user_id": user_id,
            "path": request.url.path,
            "method": request.method,
        }

    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(request: Request, exc: IngestionError):
        context = get_request_context(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": exc.error_code,
                "message": "Failed to process source",
                "detail": exc.message,
                "context": context,
                "details": exc.details,
            },
            headers={"X-Request-ID": context.get("request_id", "")},
        )

    @app.exception_handler(EmbeddingError)
    async def embedding_error_handler(request: Request, exc: EmbeddingError):
        context = get_request_context(request)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": exc.error_code,
                "message": "Embedding service unavailable",
                "detail": exc.message,
                "context": context,
                "details": exc.details,
            },
            headers={"X-Request-ID": context.get("request_id", "")},
        )

    @app.exception_handler(VectorStoreError)
    async def vectorstore_error_handler(request: Request, exc: VectorStoreError):
        context = get_request_context(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": exc.error_code,
                "message": "Database operation failed",
                "detail": exc.message,
                "context": context,
                "details": exc.details,
            },
            headers={"X-Request-ID": context.get("request_id", "")},
        )

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError):
        context = get_request_context(request)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": exc.error_code,
                "message": "LLM service unavailable",
                "detail": exc.message,
                "context": context,
                "details": exc.details,
            },
            headers={"X-Request-ID": context.get("request_id", "")},
        )

    @app.exception_handler(BaseApplicationError)
    async def base_error_handler(request: Request, exc: BaseApplicationError):
        """Catch-all for any BaseApplicationError subclasses not handled above."""
        context = get_request_context(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": exc.error_code,
                "message": "An error occurred",
                "detail": exc.message,
                "context": context,
                "details": exc.details,
            },
            headers={"X-Request-ID": context.get("request_id", "")},
        )
    
    # -------------------------
    # Health check
    # -------------------------
    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    # -------------------------
    # Cache management
    # -------------------------
    @app.get("/cache/stats", tags=["system"])
    async def cache_stats(
        _user: Annotated[schemas.UserRead, Depends(current_user)],
    ):
        """Return Redis cache statistics (requires authentication)."""
        stats = await get_cache_stats()
        return stats

    @app.post("/cache/clear", tags=["system"])
    async def cache_clear(
        _user: Annotated[schemas.UserRead, Depends(current_user)],
        cache_type: str = Query(
            "all",
            description="Type of cache to clear: embeddings, llm, or all",
        ),
    ):
        """Clear cached data by type."""
        if cache_type == "embeddings":
            deleted = await invalidate_all_embeddings()
        elif cache_type == "llm":
            deleted = await invalidate_all_llm()
        elif cache_type == "all":
            emb = await invalidate_all_embeddings()
            llm = await invalidate_all_llm()
            deleted = emb + llm
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": f"Invalid cache_type '{cache_type}'. Use: embeddings, llm, all"},
            )
        return {"message": "Cache cleared", "keys_deleted": deleted}

    return app

app = create_app()

