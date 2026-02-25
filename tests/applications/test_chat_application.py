"""Tests for ChatApplicationService - orchestrates chat with RAG."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.chat_application import ChatApplicationService
from app.db import schemas
from app.db.models import ChatSession, User


@pytest.mark.asyncio
class TestChatApplicationService:
    """Test suite for ChatApplicationService."""

    async def test_send_message_with_rag_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test sending message with RAG returns both user and assistant messages."""
        # Create chat session
        chat = ChatSession(
            title="Test Chat",
            user_id=test_user.id,
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)

        # Mock RAG service response
        mock_rag_result = {
            "answer": "Madrid is the capital of Spain.",
            "sources": [
                {
                    "source_id": "test-source-1",
                    "chunk_id": "chunk-1",
                    "content": "Madrid is the capital...",
                }
            ],
        }

        # Initialize service and mock RAG
        service = ChatApplicationService(test_db_session)
        service.rag_service.query = AsyncMock(return_value=mock_rag_result)

        # Execute
        result = await service.send_message_with_rag(
            chat_session_id=chat.id,
            user_message="What is the capital of Spain?",
            collection_name="test_collection",
        )

        # Assert structure
        assert "user_message" in result
        assert "assistant_message" in result
        assert "sources" in result

        # Assert user message saved correctly
        user_msg = result["user_message"]
        assert user_msg.content == "What is the capital of Spain?"
        assert user_msg.role == schemas.ChatRole.user
        assert user_msg.chat_id == chat.id

        # Assert assistant message saved correctly
        assistant_msg = result["assistant_message"]
        assert assistant_msg.content == "Madrid is the capital of Spain."
        assert assistant_msg.role == schemas.ChatRole.assistant
        assert assistant_msg.chat_id == chat.id

        # Assert sources passed through
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source_id"] == "test-source-1"

        # Verify RAG service was called with correct params
        service.rag_service.query.assert_called_once_with(
            question="What is the capital of Spain?",
            collection_name="test_collection",
        )

    async def test_send_message_with_rag_empty_response(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling RAG response with no sources."""
        # Create chat session
        chat = ChatSession(
            title="Test Chat",
            user_id=test_user.id,
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)

        # Mock RAG service with empty sources
        mock_rag_result = {
            "answer": "I don't have information about that.",
            "sources": [],
        }

        service = ChatApplicationService(test_db_session)
        service.rag_service.query = AsyncMock(return_value=mock_rag_result)

        # Execute
        result = await service.send_message_with_rag(
            chat_session_id=chat.id,
            user_message="What is unknown topic?",
            collection_name="test_collection",
        )

        # Assert messages created even with no sources
        assert result["user_message"].content == "What is unknown topic?"
        assert result["assistant_message"].content == "I don't have information about that."
        assert len(result["sources"]) == 0

    async def test_send_message_with_rag_preserves_message_order(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that messages are saved in correct chronological order."""
        # Create chat session
        chat = ChatSession(
            title="Test Chat",
            user_id=test_user.id,
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)

        mock_rag_result = {
            "answer": "First answer",
            "sources": [],
        }

        service = ChatApplicationService(test_db_session)
        service.rag_service.query = AsyncMock(return_value=mock_rag_result)

        # Send first message
        result1 = await service.send_message_with_rag(
            chat_session_id=chat.id,
            user_message="First question",
            collection_name="test_collection",
        )

        # Send second message
        mock_rag_result["answer"] = "Second answer"
        result2 = await service.send_message_with_rag(
            chat_session_id=chat.id,
            user_message="Second question",
            collection_name="test_collection",
        )

        # Assert first set of messages created before second
        assert result1["user_message"].created_at < result2["user_message"].created_at
        assert result1["assistant_message"].created_at < result2["assistant_message"].created_at

    async def test_send_message_with_rag_handles_long_messages(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling of very long user messages."""
        # Create chat session
        chat = ChatSession(
            title="Test Chat",
            user_id=test_user.id,
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)

        # Long message
        long_message = "What is the capital? " * 100  # ~2400 chars

        mock_rag_result = {
            "answer": "Response to long question",
            "sources": [],
        }

        service = ChatApplicationService(test_db_session)
        service.rag_service.query = AsyncMock(return_value=mock_rag_result)

        # Execute
        result = await service.send_message_with_rag(
            chat_session_id=chat.id,
            user_message=long_message,
            collection_name="test_collection",
        )

        # Assert full message preserved
        assert result["user_message"].content == long_message
        assert len(result["user_message"].content) > 2000

    async def test_send_message_with_rag_rag_service_error_propagates(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that RAG service errors are propagated correctly."""
        # Create chat session
        chat = ChatSession(
            title="Test Chat",
            user_id=test_user.id,
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)

        # Mock RAG service to raise error
        service = ChatApplicationService(test_db_session)
        service.rag_service.query = AsyncMock(
            side_effect=Exception("RAG pipeline failed")
        )

        # Execute and expect error
        with pytest.raises(Exception) as exc_info:
            await service.send_message_with_rag(
                chat_session_id=chat.id,
                user_message="Test question",
                collection_name="test_collection",
            )

        assert "RAG pipeline failed" in str(exc_info.value)

    async def test_chat_application_service_initialization(
        self,
        test_db_session: AsyncSession,
    ):
        """Test service initializes with correct dependencies."""
        service = ChatApplicationService(test_db_session)

        # Assert dependencies initialized
        assert service.db is test_db_session
        assert service.chat_service is not None
        assert service.rag_service is not None
        assert hasattr(service.chat_service, "add_message_to_chat")
        assert hasattr(service.rag_service, "query")
