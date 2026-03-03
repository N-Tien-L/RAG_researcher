"""E2E journey: create chat session → send RAG-powered message → verify response.

Exercises ChatApplicationService → RAGApplicationService → RAGPipeline with
real pgvector retrieval and mocked embedder + LLM answer generation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.models import User
from tests.e2e.conftest import E2E_ANSWER, E2E_COLLECTION

pytestmark = pytest.mark.e2e


class TestChatJourney:
    """Chat with RAG end-to-end journey tests."""

    @pytest.mark.asyncio
    async def test_create_chat_session(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Creating a chat session returns correct user_id and title."""
        resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "E2E Chat Session"},
        )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data
        assert data["user_id"] == str(test_user.id)
        assert data["title"] == "E2E Chat Session"

    @pytest.mark.asyncio
    async def test_send_rag_message_returns_user_and_assistant_messages(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        seeded_chunks: tuple,
    ) -> None:
        """Full journey: create chat → send message → verify both user + assistant rows.

        Steps
        -----
        1. Create chat session for test user.
        2. POST /api/messages/send with use_rag=True.
        3. ChatApplicationService → RAGApplicationService → RAGPipeline runs.
        4. Real pgvector retrieval picks up the seeded chunk.
        5. Mocked _generate_answer returns E2E_ANSWER.
        6. Both user message and assistant message objects are returned.
        """
        # 1. Create chat
        chat_resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "E2E RAG Chat"},
        )
        assert chat_resp.status_code == 201, chat_resp.text
        chat_id = chat_resp.json()["id"]

        # 2. Send message
        msg_resp = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": chat_id,
                "content": "What is RAG?",
                "use_rag": True,
                "collection_name": E2E_COLLECTION,
            },
        )

        assert msg_resp.status_code == 200, msg_resp.text
        data = msg_resp.json()

        # User message assertions
        user_msg = data["user_message"]
        assert user_msg["content"] == "What is RAG?"
        assert user_msg["role"] == "user"
        assert user_msg["chat_id"] == chat_id

        # Assistant message assertions
        assistant_msg = data["assistant_message"]
        assert assistant_msg["content"] == E2E_ANSWER
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["chat_id"] == chat_id

    @pytest.mark.asyncio
    async def test_list_chat_sessions_returns_created_chat(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """After creating a session, GET /api/chats/ returns it in the list."""
        # Create a chat
        title = "Listable E2E Chat"
        await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": title},
        )

        # List all chats
        list_resp = await authenticated_client.get("/api/chats/")
        assert list_resp.status_code == 200, list_resp.text
        chats = list_resp.json()

        titles = [c["title"] for c in chats]
        assert title in titles

    @pytest.mark.asyncio
    async def test_send_message_without_auth_is_rejected(
        self,
        client: AsyncClient,
    ) -> None:
        """Unauthenticated message send returns 401."""
        resp = await client.post(
            "/api/messages/send",
            json={
                "chat_id": "00000000-0000-0000-0000-000000000000",
                "content": "Sneaky message",
                "use_rag": False,
                "collection_name": E2E_COLLECTION,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_send_message_to_nonexistent_chat_returns_404(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Sending a message to an unknown chat_id returns 404."""
        resp = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": "00000000-0000-0000-0000-000000000001",
                "content": "Hello?",
                "use_rag": False,
                "collection_name": E2E_COLLECTION,
            },
        )
        assert resp.status_code == 404
