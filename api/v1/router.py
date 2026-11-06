from fastapi import APIRouter
from api.v1.chat import router as chat_router
from api.v1.conversations import router as conversations_router

api_v1_router = APIRouter(prefix="/api/v1/ai")

# Mount chat and streaming router
api_v1_router.include_router(chat_router)

# Mount conversation history & upload router
api_v1_router.include_router(conversations_router)
