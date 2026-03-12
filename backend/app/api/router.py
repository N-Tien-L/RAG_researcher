"""FastAPI main router."""

from fastapi import APIRouter

from app.api.routes import auth, chats, messages, rag, sources, users

api_router = APIRouter()

# Register all route modules
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(sources.router)
api_router.include_router(chats.router)
api_router.include_router(messages.router)
api_router.include_router(rag.router)
