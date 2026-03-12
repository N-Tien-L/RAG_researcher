"""Custom LangChain chat model for the Kaggle-hosted LitServe endpoint."""

from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, model_validator

from app.core.logging import get_logger

logger = get_logger(__name__)


def _to_api_message(message: BaseMessage) -> dict[str, str]:
    """Convert a LangChain message to the LitServe API role/content dict.

    Args:
        message: A LangChain BaseMessage instance.

    Returns:
        A dict with ``role`` and ``content`` keys.

    Raises:
        ValueError: If the message type is not supported.
    """
    if isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    else:
        raise ValueError(f"Unsupported message type: {type(message)}")
    return {"role": role, "content": str(message.content)}


class KaggleChatModel(BaseChatModel):
    """LangChain-compatible chat model backed by the Kaggle LitServe endpoint.

    The endpoint must implement the contract::

        POST /predict
        Authorization: Bearer <api_key>
        Body: {"messages": [...], "max_tokens": int, "temperature": float}
        Response: {"response": "<generated text>"}

    Args:
        api_url: Base URL of the Kaggle tunnel (e.g. ``https://abc123.localhost.run``).
        api_key: Bearer token set as ``LITSERVE_API_KEY`` on Kaggle.
        max_tokens: Maximum tokens to generate per request.
        temperature: Sampling temperature forwarded to the model.
        timeout: HTTP request timeout in seconds.
    """

    api_url: str = Field(..., description="Base URL of the Kaggle LitServe endpoint.")
    api_key: str | None = Field(default=None, description="Bearer token for authentication.")
    max_tokens: int = Field(default=1024, description="Maximum tokens to generate.")
    temperature: float = Field(default=0.2, description="Sampling temperature.")
    timeout: float = Field(default=90.0, description="HTTP request timeout in seconds.")

    @model_validator(mode="after")
    def _validate_url(self) -> "KaggleChatModel":
        """Ensure api_url is set when using the Kaggle provider."""
        if not self.api_url:
            raise ValueError(
                "KAGGLE_LLM_URL must be set when LLM_PROVIDER='kaggle'. "
                "Update it in your .env file after starting the Kaggle tunnel."
            )
        return self

    @property
    def _llm_type(self) -> str:
        return "kaggle_litserve"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous generation — not supported; use async path only."""
        raise NotImplementedError(
            "KaggleChatModel only supports async invocation. Use ainvoke() / agenerate()."
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Send messages to the Kaggle LitServe endpoint and return the response.

        Args:
            messages: Conversation messages to send.
            stop: Unused (LitServe endpoint does not support stop sequences).
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            ChatResult containing a single AIMessage generation.

        Raises:
            httpx.HTTPStatusError: On non-2xx HTTP responses (e.g. 401 Unauthorized).
            httpx.TimeoutException: When the request exceeds ``timeout`` seconds.
        """
        payload = {
            "messages": [_to_api_message(m) for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url.rstrip('/')}/predict",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        text: str = response.json()["response"]
        logger.debug(
            "kaggle_llm_response_received",
            response_length=len(text),
            status_code=response.status_code,
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
