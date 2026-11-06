import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, List, Optional, Tuple, Union

from config import settings
from schemas.chat import ChatMessage, ChatResponse

logger = logging.getLogger("make_ai_service.gemini")


class GeminiManager:
    def __init__(self):
        self._client = None

    def is_configured(self) -> bool:
        """Check if a valid Gemini API key is configured."""
        key = settings.GEMINI_API_KEY
        if not key or not key.strip():
            return False
        if key.startswith("your_") or key.startswith("your-") or "placeholder" in key.lower():
            return False
        return True

    @property
    def client(self):
        """Lazy initialization of Google GenAI Client with active event loop binding."""
        import asyncio
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is None or getattr(self, "_loop", None) != current_loop:
            if self.is_configured():
                try:
                    from google import genai
                    self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
                    self._loop = current_loop
                    logger.info("Initialized Google GenAI client with active event loop.")
                except ImportError:
                    logger.error("google-genai package not installed. Run: pip install google-genai")
                    return None
                except Exception as e:
                    logger.error(f"Failed to initialize Gemini client: {e}")
                    return None
        return self._client

    def prepare_contents(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None
    ) -> Tuple[Union[List[Any], str], str]:
        """
        Format prompt and/or message history for Gemini.
        Returns:
            (contents_for_gemini, last_query_text)
        """
        from google.genai import types

        formatted_contents = []
        last_query = ""

        # If multi-turn message history is provided
        if messages and len(messages) > 0:
            for msg in messages:
                # Map role: assistant -> model, model -> model, user -> user
                role = "model" if msg.role in ("assistant", "model") else "user"
                content_obj = types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)]
                )
                formatted_contents.append(content_obj)
                if role == "user":
                    last_query = msg.content

        # If a single prompt is passed in addition or as standalone
        if prompt and prompt.strip():
            last_query = prompt.strip()
            if not messages:
                return last_query, last_query
            else:
                formatted_contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=last_query)]
                    )
                )

        if not formatted_contents and not prompt:
            raise ValueError("Either 'prompt' or 'messages' must be provided.")

        return formatted_contents, last_query

    async def generate_chat(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7
    ) -> ChatResponse:
        """
        Generate a complete non-streaming chat response.
        """
        from google.genai import types

        target_model = model or settings.GEMINI_FLASH_MODEL
        contents, query = self.prepare_contents(prompt=prompt, messages=messages)
        start_time = time.perf_counter()

        # If API key is not yet configured, provide helpful dev simulation
        if not self.is_configured():
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            dev_text = (
                f"[Dev Mode: GEMINI_API_KEY is not configured in .env]\n\n"
                f"The request/response microservice architecture is working properly.\n"
                f"• Instance: {settings.INSTANCE_NAME}\n"
                f"• Target Model: {target_model}\n"
                f"• Query Received: \"{query}\"\n\n"
                f"To connect to live Google Gemini inference, configure GEMINI_API_KEY in your .env file."
            )
            return ChatResponse(
                text=dev_text,
                model=target_model,
                finish_reason="STOP_DEV_SIMULATED",
                latency_ms=latency_ms,
                instance=settings.INSTANCE_NAME
            )

        cli = self.client
        if not cli:
            raise RuntimeError("Gemini client could not be initialized.")

        config = types.GenerateContentConfig(
            temperature=temperature if temperature is not None else 0.7,
            system_instruction=system_instruction
        )

        try:
            response = await cli.aio.models.generate_content(
                model=target_model,
                contents=contents,
                config=config
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            finish_reason = "STOP"
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = str(response.candidates[0].finish_reason)

            return ChatResponse(
                text=response.text or "",
                model=target_model,
                finish_reason=finish_reason,
                latency_ms=latency_ms,
                instance=settings.INSTANCE_NAME
            )
        except Exception as e:
            logger.error(f"Gemini generate_chat error: {e}")
            raise

    async def generate_chat_stream(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming chat tokens formatted as Server-Sent Events (SSE).
        Format: data: {"text": "...", "done": false}\n\n
        End format: data: {"text": "", "done": true}\n\n
        """
        from google.genai import types

        target_model = model or settings.GEMINI_FLASH_MODEL
        contents, query = self.prepare_contents(prompt=prompt, messages=messages)

        # If API key is not yet configured, yield a realistic SSE dev stream
        if not self.is_configured():
            mock_tokens = [
                f"[Dev Mode: Server-Sent Events (SSE) Stream Active]\n\n",
                f"Connected to Make AI Service ({settings.INSTANCE_NAME}).\n",
                f"Echoing input: \"{query}\"\n\n",
                "• SSE streaming transport: OK\n",
                "• Async generator pipeline: OK\n",
                "• Status: Waiting for GEMINI_API_KEY in .env to stream live Gemini tokens."
            ]
            for token in mock_tokens:
                chunk_data = {"text": token, "done": False}
                yield f"data: {json.dumps(chunk_data)}\n\n"
                await asyncio.sleep(0.08)

            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
            return

        cli = self.client
        if not cli:
            err_data = {"error": "Gemini client failed to initialize", "done": True}
            yield f"data: {json.dumps(err_data)}\n\n"
            return

        config = types.GenerateContentConfig(
            temperature=temperature if temperature is not None else 0.7,
            system_instruction=system_instruction
        )

        try:
            response_stream = await cli.aio.models.generate_content_stream(
                model=target_model,
                contents=contents,
                config=config
            )

            async for chunk in response_stream:
                if chunk.text:
                    chunk_data = {"text": chunk.text, "done": False}
                    yield f"data: {json.dumps(chunk_data)}\n\n"

            # Final completion signal
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"

        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            err_data = {"error": str(e), "done": True}
            yield f"data: {json.dumps(err_data)}\n\n"


gemini_manager = GeminiManager()
