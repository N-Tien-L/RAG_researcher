"""Tests for chat message routes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.models import User


class TestSendMessage:
    """Test cases for POST /api/messages/send endpoint."""
    
    @pytest.mark.asyncio
    @patch("app.applications.chat_application.ChatApplicationService.send_message_with_rag")
    async def test_send_message_with_rag_success(
        self,
        mock_send: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Valid message with RAG returns user and assistant messages."""
        chat = await chat_factory(user_id=test_user.id)
        
        mock_send.return_value = {
            "user_message": {
                "id": str(uuid4()),
                "chat_id": str(chat.id),
                "role": "user",
                "content": "What is RAG?",
                "created_at": "2026-02-24T10:00:00Z",
            },
            "assistant_message": {
                "id": str(uuid4()),
                "chat_id": str(chat.id),
                "role": "assistant",
                "content": "RAG stands for Retrieval-Augmented Generation...",
                "created_at": "2026-02-24T10:00:05Z",
            },
            "sources": [
                {
                    "source_id": 1,
                    "title": "RAG Documentation",
                    "chunk_content": "RAG combines...",
                    "score": 0.92,
                }
            ],
        }
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(chat.id),
                "content": "What is RAG?",
                "use_rag": True,
                "collection_name": "documents",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "user_message" in data
        assert "assistant_message" in data
        assert "sources" in data
        assert data["user_message"]["content"] == "What is RAG?"
        assert data["assistant_message"]["role"] == "assistant"
        assert len(data["sources"]) == 1
    
    @pytest.mark.asyncio
    async def test_send_message_without_rag(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Message without RAG just saves user message."""
        chat = await chat_factory(user_id=test_user.id)
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(chat.id),
                "content": "Just a note",
                "use_rag": False,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["user_message"]["content"] == "Just a note"
        assert data["user_message"]["role"] == "user"
        assert data["sources"] == []
    
    @pytest.mark.asyncio
    async def test_send_message_chat_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Non-existent chat returns 404."""
        fake_chat_id = uuid4()
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(fake_chat_id),
                "content": "Hello",
                "use_rag": True,
            },
        )
        
        assert response.status_code == 404
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_send_message_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        chat_factory,
    ):
        """Cannot send message to another user's chat."""
        other_user = await user_factory(email="other@example.com")
        other_chat = await chat_factory(user_id=other_user.id)
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(other_chat.id),
                "content": "Unauthorized message",
                "use_rag": True,
            },
        )
        
        assert response.status_code == 403
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_send_message_empty_content(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Empty content returns 422."""
        chat = await chat_factory(user_id=test_user.id)
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(chat.id),
                "content": "",
                "use_rag": True,
            },
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_content_too_long(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Content exceeding max length returns 422."""
        chat = await chat_factory(user_id=test_user.id)
        long_content = "x" * 10001  # Max is 10000
        
        response = await authenticated_client.post(
            "/api/messages/send",
            json={
                "chat_id": str(chat.id),
                "content": long_content,
                "use_rag": True,
            },
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_unauthorized(
        self,
        client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """No auth token returns 401."""
        chat = await chat_factory(user_id=test_user.id)
        
        response = await client.post(
            "/api/messages/send",
            json={
                "chat_id": str(chat.id),
                "content": "Hello",
                "use_rag": True,
            },
        )
        
        assert response.status_code == 401


class TestGetChatHistory:
    """Test cases for GET /api/messages/{chat_id}/history endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_chat_history_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
        test_db_session,
    ):
        """Owner can retrieve chat history."""
        from app.db.schemas import ChatMessageCreate, ChatRole
        from app.services.chat_service import ChatService
        
        chat = await chat_factory(user_id=test_user.id)
        
        # Add some messages to the chat using test_db_session
        service = ChatService(test_db_session)
        
        # Add user message
        await service.add_message_to_chat(
            ChatMessageCreate(
                chat_id=chat.id,
                role=ChatRole.user,
                content="Hello",
            )
        )
        
        # Add assistant message
        await service.add_message_to_chat(
            ChatMessageCreate(
                chat_id=chat.id,
                role=ChatRole.assistant,
                content="Hi there!",
            )
        )
        
        response = await authenticated_client.get(f"/api/messages/{chat.id}/history")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Hello"
        assert data[1]["role"] == "assistant"
        assert data[1]["content"] == "Hi there!"
    
    @pytest.mark.asyncio
    async def test_get_chat_history_empty(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Empty chat returns empty list."""
        chat = await chat_factory(user_id=test_user.id)
        
        response = await authenticated_client.get(f"/api/messages/{chat.id}/history")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_get_chat_history_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Non-existent chat returns 404."""
        fake_chat_id = uuid4()
        
        response = await authenticated_client.get(f"/api/messages/{fake_chat_id}/history")
        
        assert response.status_code == 404
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_chat_history_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        chat_factory,
    ):
        """Cannot access another user's chat history."""
        other_user = await user_factory(email="other@example.com")
        other_chat = await chat_factory(user_id=other_user.id)
        
        response = await authenticated_client.get(f"/api/messages/{other_chat.id}/history")
        
        assert response.status_code == 403
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_chat_history_unauthorized(
        self,
        client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """No auth token returns 401."""
        chat = await chat_factory(user_id=test_user.id)
        
        response = await client.get(f"/api/messages/{chat.id}/history")
        
        assert response.status_code == 401
