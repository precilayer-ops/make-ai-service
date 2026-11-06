from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(default="New Conversation", description="Title of the conversation")


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="New title for the conversation")


class ConversationMessage(BaseModel):
    id: str = Field(..., description="Message unique identifier")
    role: str = Field(..., description="Role: 'user' or 'model'")
    content: str = Field(..., description="Message text content")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="Attached files metadata")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class ConversationSummary(BaseModel):
    id: str = Field(..., description="Conversation unique identifier")
    title: str = Field(..., description="Conversation title")
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")
    message_count: int = Field(default=0, description="Number of messages in the conversation")


class ConversationDetail(BaseModel):
    id: str = Field(..., description="Conversation unique identifier")
    title: str = Field(..., description="Conversation title")
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")
    messages: List[ConversationMessage] = Field(default_factory=list, description="List of messages")


class SendMessageRequest(BaseModel):
    content: str = Field(..., description="User message content")
    files: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional attached files")
    model: Optional[str] = Field(default=None, description="Optional model override")
    system_instruction: Optional[str] = Field(default=None, description="Optional custom system prompt")
