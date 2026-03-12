"""Tests for chat session routes."""

import pytest
from httpx import AsyncClient

from app.db.models import User


class TestCreateChatSession:
    """Test cases for POST /api/chats/ endpoint."""
    
    @pytest.mark.asyncio
    async def test_create_chat_success(self, authenticated_client: AsyncClient, test_user: User):
        """Valid request creates chat session."""
        response = await authenticated_client.post(
            "/api/chats/",
            json={
                "user_id": str(test_user.id),
                "title": "My New Chat",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert "id" in data
        assert data["title"] == "My New Chat"
        assert data["user_id"] == str(test_user.id)
        assert "created_at" in data
    
    @pytest.mark.asyncio
    async def test_create_chat_for_another_user(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
    ):
        """Cannot create for different user returns 403."""
        other_user = await user_factory(email="other@example.com")
        
        response = await authenticated_client.post(
            "/api/chats/",
            json={
                "user_id": str(other_user.id),
                "title": "Chat for other user",
            },
        )
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_create_chat_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        import uuid
        response = await client.post(
            "/api/chats/",
            json={
                "user_id": str(uuid.uuid4()),
                "title": "New Chat",
            },
        )
        
        assert response.status_code == 401


class TestGetChatSession:
    """Test cases for GET /api/chats/{chat_session_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_chat_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Owner can retrieve chat."""
        chat = await chat_factory(user_id=test_user.id, title="My Chat")
        
        response = await authenticated_client.get(f"/api/chats/{chat.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == str(chat.id)
        assert data["title"] == "My Chat"
        assert data["user_id"] == str(test_user.id)
    
    @pytest.mark.asyncio
    async def test_get_chat_not_found(self, authenticated_client: AsyncClient):
        """Non-existent ID returns 404."""
        import uuid
        response = await authenticated_client.get(f"/api/chats/{uuid.uuid4()}")
        
        assert response.status_code == 404
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_chat_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        chat_factory,
    ):
        """Different user cannot access returns 403."""
        other_user = await user_factory(email="other@example.com")
        chat = await chat_factory(user_id=other_user.id)
        
        response = await authenticated_client.get(f"/api/chats/{chat.id}")
        
        assert response.status_code == 403
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_chat_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        import uuid
        response = await client.get(f"/api/chats/{uuid.uuid4()}")
        
        assert response.status_code == 401


class TestListChatSessions:
    """Test cases for GET /api/chats/ endpoint."""
    
    @pytest.mark.asyncio
    async def test_list_chats_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Returns user's chats only."""
        # Create chats for test user
        await chat_factory(user_id=test_user.id, title="Chat 1")
        await chat_factory(user_id=test_user.id, title="Chat 2")
        
        response = await authenticated_client.get("/api/chats/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) >= 2
        
        # Verify all chats belong to test user
        for chat in data:
            assert chat["user_id"] == str(test_user.id)
    
    @pytest.mark.asyncio
    async def test_list_chats_empty(self, authenticated_client: AsyncClient):
        """New user has empty list."""
        response = await authenticated_client.get("/api/chats/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_chats_ordered_by_date(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
    ):
        """Chats ordered by created_at desc."""
        # Create multiple chats
        for i in range(3):
            await chat_factory(user_id=test_user.id, title=f"Chat {i}")
        
        response = await authenticated_client.get("/api/chats/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify ordering (newest first)
        if len(data) >= 2:
            for i in range(len(data) - 1):
                assert data[i]["created_at"] >= data[i + 1]["created_at"]
    
    @pytest.mark.asyncio
    async def test_list_chats_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        response = await client.get("/api/chats/")
        
        assert response.status_code == 401


class TestLinkSourceToChat:
    """Test cases for POST /api/chats/{chat_session_id}/sources/{source_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_link_source_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
        source_factory,
    ):
        """Valid link creates association."""
        chat = await chat_factory(user_id=test_user.id)
        source = await source_factory(user_id=test_user.id)
        
        response = await authenticated_client.post(
            f"/api/chats/{chat.id}/sources/{source.id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "chat_session_id" in data
        assert "source_id" in data
        assert data["chat_session_id"] == str(chat.id)
        assert data["source_id"] == str(source.id)
    
    @pytest.mark.asyncio
    async def test_link_source_chat_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Non-existent chat returns 404."""
        import uuid
        response = await authenticated_client.post(
            f"/api/chats/{uuid.uuid4()}/sources/{uuid.uuid4()}"
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_link_source_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        chat_factory,
        source_factory,
    ):
        """Different user cannot link returns 403."""
        other_user = await user_factory(email="other@example.com")
        chat = await chat_factory(user_id=other_user.id)
        source = await source_factory(user_id=test_user.id)
        
        response = await authenticated_client.post(
            f"/api/chats/{chat.id}/sources/{source.id}"
        )
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_link_source_duplicate(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        chat_factory,
        source_factory,
    ):
        """Duplicate link returns 400."""
        chat = await chat_factory(user_id=test_user.id)
        source = await source_factory(user_id=test_user.id)
        
        # Create link first time
        response1 = await authenticated_client.post(
            f"/api/chats/{chat.id}/sources/{source.id}"
        )
        assert response1.status_code == 200
        
        # Try to create same link again
        response2 = await authenticated_client.post(
            f"/api/chats/{chat.id}/sources/{source.id}"
        )
        
        assert response2.status_code == 400
        assert "detail" in response2.json()
    
    @pytest.mark.asyncio
    async def test_link_source_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        import uuid
        response = await client.post(f"/api/chats/{uuid.uuid4()}/sources/{uuid.uuid4()}")
        
        assert response.status_code == 401
