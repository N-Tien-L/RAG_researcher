"""Groq-backed chat title generation helpers."""

from __future__ import annotations

import re

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_MULTISPACE_PATTERN = re.compile(r"\s+")
_WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")


def fallback_chat_title(message: str, word_limit: int = 6) -> str:
    """Build a deterministic fallback title from the first message.

    Args:
        message: Raw first user message.
        word_limit: Maximum number of words to keep.

    Returns:
        A short title derived from the message.
    """
    normalized = _MULTISPACE_PATTERN.sub(" ", message).strip()
    words = _WORD_PATTERN.findall(normalized)
    if not words:
        return "New chat"
    return " ".join(words[:word_limit])


async def generate_chat_title(message: str, context: str | None = None) -> str:
    """Generate a 5-6 word chat title using Groq's chat completions API.

    Args:
        message: First user message content.
        context: Optional assistant response to improve title quality.

    Returns:
        Generated short title.

    Raises:
        RuntimeError: If Groq is not configured or the response is invalid.
        httpx.HTTPError: If the HTTP request fails.
    """
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")

    # Use a concise, deterministic prompt per requirements: 3-5 words, return only title
    if context:
        user_prompt = (
            f"Summarize this chat interaction into a 5-6 word title. Return ONLY the title string. "
            f"User asked: {message}. Assistant answered: {context[:300]}"
        )
    else:
        user_prompt = (
            "Summarize this chat interaction into a 5-6 word title. Return ONLY the title string. "
            f"Conversation: {message}"
        )

    payload = {
        "model": settings.GROQ_TITLE_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                        "Summarize this chat interaction into a 5-6 word title. Return ONLY the title string."
                    ),
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": settings.GROQ_TITLE_TEMPERATURE,
        "max_tokens": settings.GROQ_TITLE_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=settings.GROQ_TITLE_TIMEOUT) as client:
        response = await client.post(
            f"{settings.GROQ_API_URL.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

    data = response.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not content:
        raise RuntimeError("Groq returned an empty chat title")

    title = _MULTISPACE_PATTERN.sub(" ", content.replace('"', "")).strip()
    logger.debug(
        "groq_chat_title_generated",
        model=settings.GROQ_TITLE_MODEL,
        title=title,
        title_length=len(title),
    )
    return title