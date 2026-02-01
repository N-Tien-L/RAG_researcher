# FastAPI app entry

from fastapi import APIRouter

from app.api.routes import auth, chats, messages, rag, sources, users


api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
# api_router.include_router(chats.router)
# api_router.include_router(messages.router)
# api_router.include_router(rag.router)
# api_router.include_router(sources.router)
