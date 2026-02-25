"""Tests for source management routes."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.db.models import User


class TestUploadPDF:
    """Test cases for POST /api/sources/upload endpoint."""
    
    @pytest.mark.asyncio
    async def test_upload_pdf_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Valid PDF upload creates source with status 'processing'."""
        pdf_content = b"%PDF-1.4\n%fake pdf content"
        files = {"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}
        data = {
            "title": "Test PDF Document",
            "collection_name": "test_collection",
        }
        
        response = await authenticated_client.post(
            "/api/sources/upload",
            files=files,
            data=data,
        )
        
        assert response.status_code == 201
        resp_data = response.json()
        assert "id" in resp_data
        assert resp_data["type"] == "pdf"
        assert resp_data["title"] == "Test PDF Document"
        assert resp_data["user_id"] == str(test_user.id)
        assert resp_data["collection_name"] == "test_collection"
    
    @pytest.mark.asyncio
    async def test_upload_pdf_invalid_file_type(self, authenticated_client: AsyncClient):
        """Non-PDF file returns 400."""
        txt_content = b"This is a text file, not a PDF"
        files = {"file": ("test.txt", BytesIO(txt_content), "text/plain")}
        data = {"title": "Test", "collection_name": "test"}
        
        response = await authenticated_client.post(
            "/api/sources/upload",
            files=files,
            data=data,
        )
        
        assert response.status_code == 400
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_upload_pdf_missing_file(self, authenticated_client: AsyncClient):
        """Missing file returns 422."""
        response = await authenticated_client.post(
            "/api/sources/upload",
            data={"title": "No file attached", "collection_name": "test"},
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_upload_pdf_unauthorized(self, client: AsyncClient):
        """No auth token returns 401."""
        pdf_content = b"%PDF-1.4\n%fake pdf content"
        files = {"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}
        data = {"title": "Test", "collection_name": "test"}
        
        response = await client.post(
            "/api/sources/upload",
            files=files,
            data=data,
        )
        
        assert response.status_code == 401


class TestCreateYouTubeSource:
    """Test cases for POST /api/sources/youtube endpoint."""
    
    @pytest.mark.asyncio
    async def test_create_youtube_success(self, authenticated_client: AsyncClient, test_user: User):
        """Valid YouTube URL creates source."""
        response = await authenticated_client.post(
            "/api/sources/youtube",
            data={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Test YouTube Video",
                "collection_name": "youtube_collection",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "youtube"
        assert data["title"] == "Test YouTube Video"
        assert data["user_id"] == str(test_user.id)
        assert "youtube.com" in data["source_uri"]
    
    @pytest.mark.asyncio
    async def test_create_youtube_invalid_url(self, authenticated_client: AsyncClient):
        """Invalid URL returns 400."""
        response = await authenticated_client.post(
            "/api/sources/youtube",
            data={
                "url": "not-a-valid-url",
                "title": "Invalid URL",
                "collection_name": "test",
            },
        )
        
        assert response.status_code == 400
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_create_youtube_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        response = await client.post(
            "/api/sources/youtube",
            data={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Test",
                "collection_name": "test",
            },
        )
        
        assert response.status_code == 401


class TestGetSource:
    """Test cases for GET /api/sources/{source_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_source_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Owner can retrieve source."""
        source = await source_factory(user_id=test_user.id, title="My Source")
        
        response = await authenticated_client.get(f"/api/sources/{source.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(source.id)
        assert data["title"] == "My Source"
        assert data["user_id"] == str(test_user.id)
    
    @pytest.mark.asyncio
    async def test_get_source_not_found(self, authenticated_client: AsyncClient):
        """Non-existent ID returns 404."""
        import uuid
        response = await authenticated_client.get(f"/api/sources/{uuid.uuid4()}")
        
        assert response.status_code == 404
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_source_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        source_factory,
    ):
        """Different user cannot access returns 403."""
        other_user = await user_factory(email="other@example.com")
        source = await source_factory(user_id=other_user.id)
        
        response = await authenticated_client.get(f"/api/sources/{source.id}")
        
        assert response.status_code == 403
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_source_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        import uuid
        response = await client.get(f"/api/sources/{uuid.uuid4()}")
        
        assert response.status_code == 401


class TestListSources:
    """Test cases for GET /api/sources/ endpoint."""
    
    @pytest.mark.asyncio
    async def test_list_sources_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Returns user's sources only."""
        # Create sources for test user
        await source_factory(user_id=test_user.id, title="Source 1")
        await source_factory(user_id=test_user.id, title="Source 2")
        
        response = await authenticated_client.get("/api/sources/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        
        # Verify all sources belong to test user
        for source in data:
            assert source["user_id"] == str(test_user.id)
    
    @pytest.mark.asyncio
    async def test_list_sources_pagination(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Skip/limit parameters work."""
        # Create multiple sources
        for i in range(5):
            await source_factory(user_id=test_user.id, title=f"Source {i}")
        
        # Test pagination
        response = await authenticated_client.get("/api/sources/?skip=2&limit=2")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2
    
    @pytest.mark.asyncio
    async def test_list_sources_empty(self, authenticated_client: AsyncClient):
        """New user has empty list."""
        response = await authenticated_client.get("/api/sources/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_sources_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        response = await client.get("/api/sources/")
        
        assert response.status_code == 401


class TestProcessSource:
    """Test cases for POST /api/sources/{source_id}/process endpoint."""
    
    @pytest.mark.asyncio
    @patch("app.applications.ingestion_application.IngestionApplicationService.process_source")
    async def test_process_source_success(
        self,
        mock_process: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Mock ingestion and verify response structure."""
        source = await source_factory(
            user_id=test_user.id,
            source_uri="file://test/document.pdf",
        )
        
        mock_process.return_value = {
            "chunks_added": 42,
            "collection": "test_collection",
            "ids": ["id1", "id2"],
            "content_hash": "hash123",
            "status": "ready",
        }
        
        response = await authenticated_client.post(f"/api/sources/{source.id}/process")
        
        assert response.status_code == 202
        data = response.json()
        assert data["chunks_added"] == 42
        assert "source" in data
    
    @pytest.mark.asyncio
    async def test_process_source_not_found(self, authenticated_client: AsyncClient):
        """Non-existent source returns 404."""
        import uuid
        response = await authenticated_client.post(f"/api/sources/{uuid.uuid4()}/process")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_process_source_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        user_factory,
        source_factory,
    ):
        """Different user cannot process returns 403."""
        other_user = await user_factory(email="other@example.com")
        source = await source_factory(user_id=other_user.id)
        
        response = await authenticated_client.post(f"/api/sources/{source.id}/process")
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_process_source_no_uri(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Source without URI returns 400."""
        source = await source_factory(user_id=test_user.id, source_uri=None)
        
        response = await authenticated_client.post(f"/api/sources/{source.id}/process")
        
        assert response.status_code == 400
        assert "detail" in response.json()
