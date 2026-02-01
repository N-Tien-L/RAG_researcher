from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.applications.rag_service import RagService
from app.core.config import settings
from app.db.sessions import init_engine
from app.vectorstore.chroma import init_chroma

@asynccontextmanager
async def lifespan(app: FastAPI):
    # -------------------------
    # Startup
    # -------------------------
    init_engine(settings.DATABASE_URL)
    init_chroma()

    app.state.rag_service = RagService(top_k=5)

    print("✅ Postgres connected")
    print("✅ Chroma initialized")
    print("✅ RAG service ready")

    yield

    # -------------------------
    # Shutdown
    # -------------------------
    print("🛑 Shutting down API")
