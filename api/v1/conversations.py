import asyncio
from datetime import datetime
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from config import settings
from core.db import db_manager
from core.gemini_client import gemini_manager
from schemas.chat import ChatMessage
from schemas.conversation import (
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
    CreateConversationRequest,
    RenameConversationRequest,
    SendMessageRequest,
)

logger = logging.getLogger("make_ai_service.api.conversations")

router = APIRouter(prefix="/conversations", tags=["Conversations & History"])

# In-memory fallback storage if MongoDB is not reachable during local dev
_mem_conversations: Dict[str, Dict[str, Any]] = {}
_mem_messages: Dict[str, List[Dict[str, Any]]] = {}

# Uploads directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def _get_conversations_coll():
    if db_manager.ai_db is not None:
        return db_manager.ai_db["conversations"]
    return None


async def _get_messages_coll():
    if db_manager.ai_db is not None:
        return db_manager.ai_db["messages"]
    return None


@router.get("", response_model=List[ConversationSummary], summary="List all conversations")
async def list_conversations(
    user_id: Optional[str] = Query(default="default_user", description="Current user ID")
):
    """Retrieve all conversations sorted by last updated timestamp."""
    coll = await _get_conversations_coll()
    summaries = []

    if coll is not None:
        try:
            cursor = coll.find(
                {"user_id": user_id, "is_deleted": {"$ne": True}}
            ).sort("updated_at", -1)
            msg_coll = await _get_messages_coll()
            async for doc in cursor:
                conv_id = str(doc.get("_id"))
                count = 0
                if msg_coll is not None:
                    count = await msg_coll.count_documents({"conversation_id": conv_id})
                summaries.append(
                    ConversationSummary(
                        id=conv_id,
                        title=doc.get("title", "New Conversation"),
                        created_at=doc.get("created_at", datetime.utcnow().isoformat()),
                        updated_at=doc.get("updated_at", datetime.utcnow().isoformat()),
                        message_count=count,
                    )
                )
            return summaries
        except Exception as e:
            logger.warning(f"Failed querying MongoDB, falling back to memory: {e}")

    # Fallback in-memory
    active_convs = [
        c for c in _mem_conversations.values()
        if c.get("user_id") == user_id and not c.get("is_deleted", False)
    ]
    active_convs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return [
        ConversationSummary(
            id=c["id"],
            title=c["title"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=len(_mem_messages.get(c["id"], [])),
        )
        for c in active_convs
    ]


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED, summary="Create a new conversation")
async def create_conversation(
    req: CreateConversationRequest,
    user_id: Optional[str] = Query(default="default_user", description="Current user ID")
):
    """Create a new chat conversation."""
    now = datetime.utcnow().isoformat()
    conv_id = str(uuid.uuid4())
    title = (req.title or "New Conversation").strip() or "New Conversation"

    coll = await _get_conversations_coll()
    if coll is not None:
        try:
            doc = {
                "_id": conv_id,
                "user_id": user_id,
                "title": title,
                "instance": settings.INSTANCE_NAME,
                "created_at": now,
                "updated_at": now,
                "is_deleted": False,
            }
            await coll.insert_one(doc)
            return ConversationSummary(
                id=conv_id,
                title=title,
                created_at=now,
                updated_at=now,
                message_count=0,
            )
        except Exception as e:
            logger.warning(f"Failed inserting conversation to MongoDB, using memory: {e}")

    # In-memory storage
    conv_data = {
        "id": conv_id,
        "user_id": user_id,
        "title": title,
        "instance": settings.INSTANCE_NAME,
        "created_at": now,
        "updated_at": now,
        "is_deleted": False,
    }
    _mem_conversations[conv_id] = conv_data
    _mem_messages[conv_id] = []

    return ConversationSummary(
        id=conv_id,
        title=title,
        created_at=now,
        updated_at=now,
        message_count=0,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail, summary="Get conversation messages")
async def get_conversation(conversation_id: str):
    """Retrieve full conversation history and metadata."""
    coll = await _get_conversations_coll()
    msg_coll = await _get_messages_coll()

    conv_doc = None
    messages = []

    if coll is not None:
        try:
            conv_doc = await coll.find_one({"_id": conversation_id, "is_deleted": {"$ne": True}})
            if conv_doc and msg_coll is not None:
                cursor = msg_coll.find({"conversation_id": conversation_id}).sort("created_at", 1)
                async for m in cursor:
                    messages.append(
                        ConversationMessage(
                            id=str(m.get("_id")),
                            role=m.get("role", "user"),
                            content=m.get("content", ""),
                            files=m.get("files", []),
                            created_at=m.get("created_at", ""),
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed fetching conversation from MongoDB: {e}")

    if not conv_doc:
        conv_doc = _mem_conversations.get(conversation_id)
        if not conv_doc or conv_doc.get("is_deleted"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        messages = [
            ConversationMessage(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                files=m.get("files", []),
                created_at=m["created_at"],
            )
            for m in _mem_messages.get(conversation_id, [])
        ]

    return ConversationDetail(
        id=conversation_id,
        title=conv_doc.get("title", "New Conversation"),
        created_at=conv_doc.get("created_at", ""),
        updated_at=conv_doc.get("updated_at", ""),
        messages=messages,
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary, summary="Rename a conversation")
async def rename_conversation(conversation_id: str, req: RenameConversationRequest):
    """Rename a conversation title."""
    now = datetime.utcnow().isoformat()
    new_title = req.title.strip()
    coll = await _get_conversations_coll()

    if coll is not None:
        try:
            res = await coll.find_one_and_update(
                {"_id": conversation_id, "is_deleted": {"$ne": True}},
                {"$set": {"title": new_title, "updated_at": now}},
                return_document=True,
            )
            if res:
                return ConversationSummary(
                    id=conversation_id,
                    title=new_title,
                    created_at=res.get("created_at", now),
                    updated_at=now,
                    message_count=0,
                )
        except Exception as e:
            logger.warning(f"Failed renaming in MongoDB: {e}")

    conv = _mem_conversations.get(conversation_id)
    if not conv or conv.get("is_deleted"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conv["title"] = new_title
    conv["updated_at"] = now
    return ConversationSummary(
        id=conversation_id,
        title=new_title,
        created_at=conv["created_at"],
        updated_at=now,
        message_count=len(_mem_messages.get(conversation_id, [])),
    )


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(conversation_id: str):
    """Delete (archive) a conversation."""
    now = datetime.utcnow().isoformat()
    coll = await _get_conversations_coll()

    if coll is not None:
        try:
            await coll.update_one(
                {"_id": conversation_id},
                {"$set": {"is_deleted": True, "updated_at": now}}
            )
            return {"success": True, "id": conversation_id}
        except Exception as e:
            logger.warning(f"Failed deleting in MongoDB: {e}")

    if conversation_id in _mem_conversations:
        _mem_conversations[conversation_id]["is_deleted"] = True
        return {"success": True, "id": conversation_id}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("/{conversation_id}/messages", summary="Send message & stream assistant response")
async def send_message_stream(conversation_id: str, req: SendMessageRequest):
    """
    Send a message to a conversation.
    Returns a Server-Sent Events (SSE) stream of assistant response tokens.
    Persists both user message and assistant reply upon stream completion.
    """
    now = datetime.utcnow().isoformat()
    coll = await _get_conversations_coll()
    msg_coll = await _get_messages_coll()

    # 1. Verify conversation exists
    conv = None
    if coll is not None:
        try:
            conv = await coll.find_one({"_id": conversation_id, "is_deleted": {"$ne": True}})
        except Exception as e:
            logger.warning(f"MongoDB read error: {e}")
    if not conv:
        conv = _mem_conversations.get(conversation_id)
    if not conv or conv.get("is_deleted"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 2. Save User Message
    user_msg_id = str(uuid.uuid4())
    user_msg_doc = {
        "_id": user_msg_id,
        "id": user_msg_id,
        "conversation_id": conversation_id,
        "role": "user",
        "content": req.content,
        "files": req.files or [],
        "created_at": now,
    }

    if msg_coll is not None:
        try:
            await msg_coll.insert_one(user_msg_doc)
        except Exception as e:
            logger.warning(f"Error saving user message to MongoDB: {e}")

    if conversation_id not in _mem_messages:
        _mem_messages[conversation_id] = []
    _mem_messages[conversation_id].append(user_msg_doc)

    # 3. Fetch past history for context
    history_messages: List[ChatMessage] = []
    if msg_coll is not None:
        try:
            cursor = msg_coll.find({"conversation_id": conversation_id}).sort("created_at", 1)
            async for m in cursor:
                history_messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))
        except Exception:
            for m in _mem_messages.get(conversation_id, []):
                history_messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))
    else:
        for m in _mem_messages.get(conversation_id, []):
            history_messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))

    # Auto-rename if conversation title is still default
    if conv.get("title") == "New Conversation":
        new_title = req.content.strip().split("\n")[0][:36]
        if len(req.content.strip().split("\n")[0]) > 36:
            new_title += "..."
        conv["title"] = new_title
        if coll is not None:
            try:
                await coll.update_one({"_id": conversation_id}, {"$set": {"title": new_title}})
            except Exception:
                pass

    # 4. Stream generator that saves assistant response at completion
    async def sse_event_stream():
        full_assistant_reply = []
        try:
            async for sse_chunk in gemini_manager.generate_chat_stream(
                messages=history_messages,
                system_instruction=req.system_instruction or "You are a helpful, expert manufacturing and quoting assistant for CNC machining, 3D printing, sheet metal, and supply chain operations. Be professional, structured, and concise.",
                model=req.model,
            ):
                # Parse data to capture text
                if sse_chunk.startswith("data: "):
                    payload = json.loads(sse_chunk[6:].strip())
                    if payload.get("text"):
                        full_assistant_reply.append(payload["text"])
                yield sse_chunk

            # Stream finished — persist assistant response
            complete_text = "".join(full_assistant_reply).strip()
            assistant_now = datetime.utcnow().isoformat()
            assistant_msg_id = str(uuid.uuid4())
            assistant_doc = {
                "_id": assistant_msg_id,
                "id": assistant_msg_id,
                "conversation_id": conversation_id,
                "role": "model",
                "content": complete_text,
                "files": [],
                "created_at": assistant_now,
            }

            if msg_coll is not None:
                try:
                    await msg_coll.insert_one(assistant_doc)
                    if coll is not None:
                        await coll.update_one(
                            {"_id": conversation_id},
                            {"$set": {"updated_at": assistant_now}}
                        )
                except Exception as e:
                    logger.warning(f"Failed saving assistant reply to MongoDB: {e}")

            _mem_messages[conversation_id].append(assistant_doc)
            if conversation_id in _mem_conversations:
                _mem_conversations[conversation_id]["updated_at"] = assistant_now

        except Exception as e:
            logger.error(f"Error during message streaming: {e}")
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(sse_event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/upload", summary="Upload a file/drawing/step for AI context")
async def upload_file(file: UploadFile = File(...)):
    """Upload a blueprint (PDF/image) or 3D CAD (.step) file to include in AI conversation."""
    try:
        file_ext = os.path.splitext(file.filename)[1].lower()
        safe_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
        dest_path = os.path.join(UPLOAD_DIR, safe_name)

        file_bytes = await file.read()
        with open(dest_path, "wb") as f:
            f.write(file_bytes)

        file_url = f"/uploads/{safe_name}"
        return {
            "success": True,
            "filename": safe_name,
            "original_name": file.filename,
            "size": len(file_bytes),
            "content_type": file.content_type or "application/octet-stream",
            "url": file_url,
        }
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )
