from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "model", "assistant", "system"] = Field(
        default="user",
        description="Role of the message author. Note: 'assistant' is mapped to 'model' for Gemini."
    )
    content: str = Field(..., description="Text content of the message.")


class ChatRequest(BaseModel):
    prompt: Optional[str] = Field(
        default=None,
        description="Single prompt message (convenience for simple one-off questions)."
    )
    messages: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Multi-turn conversation history."
    )
    system_instruction: Optional[str] = Field(
        default=None,
        description="Custom system prompt to guide the AI's behavior and persona."
    )
    model: Optional[str] = Field(
        default=None,
        description="Gemini model override (defaults to gemini-2.5-flash)."
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for creativity vs precision."
    )


class ChatResponse(BaseModel):
    text: str = Field(..., description="The complete generated text response.")
    model: str = Field(..., description="The Gemini model used for generation.")
    finish_reason: Optional[str] = Field(default=None, description="Reason the generation finished.")
    latency_ms: float = Field(..., description="Round-trip request latency in milliseconds.")
    instance: str = Field(..., description="Current running instance (PIPL or NDCS).")


class StreamChunk(BaseModel):
    text: str = Field(..., description="Incremental word-by-word text chunk.")
    done: bool = Field(default=False, description="True when generation is complete.")
    error: Optional[str] = Field(default=None, description="Error message if generation failed.")
