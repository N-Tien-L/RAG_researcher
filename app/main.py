from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.lifespan import lifespan
from app.api.router import api_router
from app.services.exceptions import AuthenticationError, ResourceConflict, ResourceNotFound

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
    
    # -------------------------
    # Health check
    # -------------------------
    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}
    
    return app

app = create_app()

