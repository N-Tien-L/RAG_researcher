"""Tests for chat service business logic."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage
from app.db.schemas import ChatMessageCreate, ChatSessionCreate
from app.services.chat_service import ChatService
from app.services.exceptions import ResourceConflict, ResourceNotFound


class TestCreateChatSession:
    """Test cases for create_chat_session method."""
    
    @pytest.mark.asyncio
    async def test_create_chat_session_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        monkeypatch,
    ):
        """Creates chat in database."""
        async def fail_if_called(_: str) -> str:
            raise AssertionError("title generation should not run")

        monkeypatch.setattr(
            "app.services.chat_service.generate_chat_title",
            fail_if_called,
        )

        chat_data = ChatSessionCreate(
            user_id=test_user.id,
            title="My Chat Session",
        )
        
        result = await ChatService(test_db_session).create_chat_session(chat_data)
        
        assert result.id is not None
        assert result.user_id == test_user.id
        assert result.title == "My Chat Session"
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_create_chat_session_generates_title_from_first_message(
        self,
        test_db_session: AsyncSession,
        test_user,
        monkeypatch,
    ):
        """Generates a title from the first user message."""
        async def fake_generate_title(message: str) -> str:
            assert message == "How do I evaluate retrieval quality in RAG systems?"
            return "Evaluate retrieval quality in RAG"

        monkeypatch.setattr(
            "app.services.chat_service.generate_chat_title",
            fake_generate_title,
        )

        chat_data = ChatSessionCreate(
            user_id=test_user.id,
            first_message="How do I evaluate retrieval quality in RAG systems?",
        )

        result = await ChatService(test_db_session).create_chat_session(chat_data)

        assert result.title == "Evaluate retrieval quality in RAG"

    @pytest.mark.asyncio
    async def test_create_chat_session_uses_fallback_when_groq_fails(
        self,
        test_db_session: AsyncSession,
        test_user,
        monkeypatch,
    ):
        """Falls back to a truncated message when title generation fails."""
        async def fail_generate_title(_: str) -> str:
            raise RuntimeError("groq unavailable")

        monkeypatch.setattr(
            "app.services.chat_service.generate_chat_title",
            fail_generate_title,
        )

        chat_data = ChatSessionCreate(
            user_id=test_user.id,
            first_message="Need a practical plan for evaluating RAG answers quickly",
        )

        result = await ChatService(test_db_session).create_chat_session(chat_data)

        assert result.title == "Need a practical plan for evaluating"
    
    @pytest.mark.asyncio
    async def test_create_chat_session_user_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound for invalid user_id."""
        chat_data = ChatSessionCreate(
            user_id=uuid4(),  # Non-existent user
            title="Chat Session",
        )
        
        with pytest.raises(ResourceNotFound) as exc_info:
            await ChatService(test_db_session).create_chat_session(chat_data)
        
        assert "User" in str(exc_info.value)


class TestGetChatSession:
    """Test cases for get_chat_session method."""
    
    @pytest.mark.asyncio
    async def test_get_chat_session_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Retrieves existing chat."""
        chat = await chat_factory(
            user_id=test_user.id,
            title="Test Chat",
        )
        
        result = await ChatService(test_db_session).get_chat_session(chat.id)
        
        assert result is not None
        assert result.id == chat.id
        assert result.title == "Test Chat"
        assert result.user_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_get_chat_session_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound."""
        with pytest.raises(ResourceNotFound) as exc_info:
            await ChatService(test_db_session).get_chat_session(uuid4())
        
        assert "Chat session not found" in str(exc_info.value)


class TestListChatSessionsForUser:
    """Test cases for list_chat_sessions_for_user method."""
    
    @pytest.mark.asyncio
    async def test_list_chat_sessions_for_user(
        self,
        test_db_session: AsyncSession,
        test_user,
        user_factory,
        chat_factory,
    ):
        """Returns only user's chats."""
        # Create chats for test user
        await chat_factory(user_id=test_user.id, title="Chat 1")
        await chat_factory(user_id=test_user.id, title="Chat 2")
        
        # Create chat for different user
        other_user = await user_factory(email="other@example.com")
        await chat_factory(user_id=other_user.id, title="Other Chat")
        
        result = await ChatService(test_db_session).list_chat_sessions_for_user(
            test_user.id,
        )
        
        assert len(result) == 2
        for chat in result:
            assert chat.user_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_list_chat_sessions_ordered(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Ordered by created_at desc."""
        # Create chats
        chat1 = await chat_factory(user_id=test_user.id, title="First")
        chat2 = await chat_factory(user_id=test_user.id, title="Second")
        
        result = await ChatService(test_db_session).list_chat_sessions_for_user(
            test_user.id,
        )
        
        # Newest should be first
        assert result[0].id == chat2.id
        assert result[1].id == chat1.id


class TestGetChatHistory:
    """Test cases for get_chat_history method."""
    
    @pytest.mark.asyncio
    async def test_get_chat_history_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Returns messages for chat."""
        chat = await chat_factory(user_id=test_user.id)
        
        # Add messages
        msg1 = ChatMessage(
            chat_id=chat.id,
            role="user",
            content="Hello",
        )
        msg2 = ChatMessage(
            chat_id=chat.id,
            role="assistant",
            content="Hi there!",
        )
        test_db_session.add_all([msg1, msg2])
        await test_db_session.commit()
        
        result = await ChatService(test_db_session).get_chat_history(chat.id)
        
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there!"
    
    @pytest.mark.asyncio
    async def test_get_chat_history_empty(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Returns empty list for new chat."""
        chat = await chat_factory(user_id=test_user.id)
        
        result = await ChatService(test_db_session).get_chat_history(chat.id)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_chat_history_chat_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound."""
        with pytest.raises(ResourceNotFound):
            await ChatService(test_db_session).get_chat_history(uuid4())


class TestAddMessageToChat:
    """Test cases for add_message_to_chat method."""
    
    @pytest.mark.asyncio
    async def test_add_message_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Creates message in database."""
        chat = await chat_factory(user_id=test_user.id)
        
        message_data = ChatMessageCreate(
            chat_id=chat.id,
            role="user",
            content="Test message",
        )
        
        result = await ChatService(test_db_session).add_message_to_chat(
            message_data,
        )
        
        assert result.id is not None
        assert result.chat_id == chat.id
        assert result.role == "user"
        assert result.content == "Test message"
        assert result.created_at is not None
    
    @pytest.mark.asyncio
    async def test_add_message_chat_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound."""
        message_data = ChatMessageCreate(
            chat_id=uuid4(),
            role="user",
            content="Test",
        )
        
        with pytest.raises(ResourceNotFound):
            await ChatService(test_db_session).add_message_to_chat(
                message_data,
            )


class TestLinkSourceToChat:
    """Test cases for link_source_to_chat method."""
    
    @pytest.mark.asyncio
    async def test_link_source_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
        source_factory,
    ):
        """Creates link in database."""
        chat = await chat_factory(user_id=test_user.id)
        source = await source_factory(user_id=test_user.id)
        
        result = await ChatService(test_db_session).link_source_to_chat(
            chat.id,
            source.id,
        )
        
        assert result.chat_session_id == chat.id
        assert result.source_id == source.id
    
    @pytest.mark.asyncio
    async def test_link_source_chat_not_found(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Raises ResourceNotFound for invalid chat."""
        source = await source_factory(user_id=test_user.id)
        
        with pytest.raises(ResourceNotFound) as exc_info:
            await ChatService(test_db_session).link_source_to_chat(
                uuid4(),
                source.id,
            )
        
        assert "Chat session not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_link_source_source_not_found(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
    ):
        """Raises ResourceNotFound for invalid source."""
        chat = await chat_factory(user_id=test_user.id)
        
        with pytest.raises(ResourceNotFound) as exc_info:
            await ChatService(test_db_session).link_source_to_chat(
                chat.id,
                uuid4(),
            )
        
        assert "Source" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_link_source_duplicate(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
        source_factory,
    ):
        """Raises ResourceConflict for duplicate link."""
        chat = await chat_factory(user_id=test_user.id)
        source = await source_factory(user_id=test_user.id)
        
        # Create first link
        await ChatService(test_db_session).link_source_to_chat(
            chat.id,
            source.id,
        )
        
        # Try to create duplicate
        with pytest.raises(ResourceConflict) as exc_info:
            await ChatService(test_db_session).link_source_to_chat(
                chat.id,
                source.id,
            )
        
        assert "link already exists" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_link_source_duplicate_ignore_existing_returns_link(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
        source_factory,
    ):
        """Returns existing link when ignore_existing is enabled."""
        service = ChatService(test_db_session)
        chat = await chat_factory(user_id=test_user.id)
        source = await source_factory(user_id=test_user.id)

        first = await service.link_source_to_chat(chat.id, source.id)
        second = await service.link_source_to_chat(
            chat.id,
            source.id,
            ignore_existing=True,
        )

        assert second.chat_session_id == first.chat_session_id
        assert second.source_id == first.source_id
        assert second.created_at == first.created_at


class TestListSourcesForChat:
    """Test cases for list_sources_for_chat method."""

    @pytest.mark.asyncio
    async def test_list_sources_for_chat_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        chat_factory,
        source_factory,
    ):
        """Returns linked sources for the target chat session."""
        service = ChatService(test_db_session)
        chat = await chat_factory(user_id=test_user.id)
        source_one = await source_factory(user_id=test_user.id, title="Source One")
        source_two = await source_factory(user_id=test_user.id, title="Source Two")

        await service.link_source_to_chat(chat.id, source_one.id)
        await service.link_source_to_chat(chat.id, source_two.id)

        linked = await service.list_sources_for_chat(chat.id)

        assert len(linked) == 2
        assert {item.id for item in linked} == {source_one.id, source_two.id}

    @pytest.mark.asyncio
    async def test_list_sources_for_chat_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound for unknown chat session."""
        service = ChatService(test_db_session)

        with pytest.raises(ResourceNotFound):
            await service.list_sources_for_chat(uuid4())
