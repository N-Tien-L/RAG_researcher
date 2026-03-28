"""E2E journey: create chat session → send RAG-powered message → verify response.

Exercises ChatApplicationService → RAGApplicationService → RAGPipeline with
real pgvector retrieval and mocked embedder + LLM answer generation.
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatSessionSource, Source, User
from tests.e2e.conftest import E2E_ANSWER

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
        1.5 Link seeded source to chat.
        2. POST /api/messages/send with use_rag=True.
        3. ChatApplicationService → RAGApplicationService → RAGPipeline runs.
        4. Real pgvector retrieval picks up the seeded chunk.
        5. Mocked _generate_answer returns E2E_ANSWER.
        6. Both user message and assistant message objects are returned.
        """
        _, seeded_source = seeded_chunks

        # 1. Create chat
        chat_resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "E2E RAG Chat"},
        )
        assert chat_resp.status_code == 201, chat_resp.text
        chat_id = chat_resp.json()["id"]

        # 1.5 Link source used by retrieval
        link_resp = await authenticated_client.post(
            f"/api/chats/{chat_id}/sources/{seeded_source.id}"
        )
        assert link_resp.status_code == 200, link_resp.text

        # 2. Send message
        msg_resp = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": chat_id,
                "content": "What is RAG?",
                "use_rag": True,
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
            },
        )
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # New tests: link source, chat history, send without RAG
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_link_source_to_chat_journey(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        test_db_session: AsyncSession,
    ) -> None:
        """POST /chats/{chat_id}/sources/{source_id} creates a ChatSessionSource row.

        Steps
        -----
        1. Create a chat session via API.
        2. Seed a source directly in DB.
        3. Link the source to the chat via the API.
        4. Verify the ChatSessionSource row exists in the DB.
        """
        # 1. Create chat
        chat_resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "Chat with Source"},
        )
        assert chat_resp.status_code == 201, chat_resp.text
        chat_id = chat_resp.json()["id"]

        # 2. Seed a source
        source = Source(
            user_id=test_user.id,
            type="pdf",
            title="Linkable Source",
            status="ready",
            source_uri="file://e2e/link_test.pdf",
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        # 3. Link source to chat
        link_resp = await authenticated_client.post(
            f"/api/chats/{chat_id}/sources/{source.id}"
        )
        assert link_resp.status_code == 200, link_resp.text
        data = link_resp.json()
        assert data["chat_session_id"] == chat_id
        assert data["source_id"] == str(source.id)

        # 4. Verify DB row
        result = await test_db_session.execute(
            select(ChatSessionSource).where(
                ChatSessionSource.chat_session_id == _uuid.UUID(chat_id),
                ChatSessionSource.source_id == source.id,
            )
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_get_chat_history_after_message(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        seeded_chunks: tuple,
    ) -> None:
        """GET /messages/{chat_id}/history returns user + assistant messages in order.

        Steps
        -----
        1. Create a chat session.
        1.5 Link seeded source to chat.
        2. Send a RAG message (mocked answer via autouse fixtures).
        3. GET /messages/{chat_id}/history.
        4. Assert two messages are returned: user first, assistant second.
        """
        _, seeded_source = seeded_chunks

        # 1. Create chat
        chat_resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "History Test Chat"},
        )
        assert chat_resp.status_code == 201, chat_resp.text
        chat_id = chat_resp.json()["id"]

        # 1.5 Link source used by retrieval
        link_resp = await authenticated_client.post(
            f"/api/chats/{chat_id}/sources/{seeded_source.id}"
        )
        assert link_resp.status_code == 200, link_resp.text

        # 2. Send a message
        msg_resp = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": chat_id,
                "content": "What is retrieval augmented generation?",
                "use_rag": True,
            },
        )
        assert msg_resp.status_code == 200, msg_resp.text

        # 3. Retrieve history
        history_resp = await authenticated_client.get(
            f"/api/messages/{chat_id}/history"
        )
        assert history_resp.status_code == 200, history_resp.text
        messages = history_resp.json()

        # 4. Assert both messages with correct roles
        assert len(messages) == 2
        roles = [m["role"] for m in messages]
        assert roles[0] == "user"
        assert roles[1] == "assistant"
        assert messages[0]["content"] == "What is retrieval augmented generation?"
        assert messages[1]["content"] == E2E_ANSWER
        assert messages[0]["chat_id"] == chat_id
        assert messages[1]["chat_id"] == chat_id

    @pytest.mark.asyncio
    async def test_send_message_without_rag_stores_only_user_message(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """When use_rag=False, only the user message is persisted in the DB.

        The route returns a placeholder assistant_message equal to user_msg but
        does NOT write a second row, so GET /history returns exactly 1 message.
        """
        # Create chat
        chat_resp = await authenticated_client.post(
            "/api/chats/",
            json={"user_id": str(test_user.id), "title": "No-RAG Chat"},
        )
        assert chat_resp.status_code == 201, chat_resp.text
        chat_id = chat_resp.json()["id"]

        # Send message without RAG
        send_resp = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": chat_id,
                "content": "Just a plain user message.",
                "use_rag": False,
            },
        )
        assert send_resp.status_code == 200, send_resp.text
        data = send_resp.json()
        assert data["user_message"]["role"] == "user"
        assert data["user_message"]["content"] == "Just a plain user message."

        # History should contain exactly one message
        history_resp = await authenticated_client.get(
            f"/api/messages/{chat_id}/history"
        )
        assert history_resp.status_code == 200, history_resp.text
        messages = history_resp.json()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Just a plain user message."
