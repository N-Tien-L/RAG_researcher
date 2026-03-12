"""Tests for source service business logic."""

from datetime import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import SourceCreate
from app.services.exceptions import ResourceNotFound
from app.services.source_service import SourceService


class TestCreateSource:
    """Test cases for create_source method."""
    
    @pytest.mark.asyncio
    async def test_create_source_success(
        self,
        test_db_session: AsyncSession,
        test_user,
    ):
        """Creates source in database."""
        service = SourceService(test_db_session)
        source_data = SourceCreate(
            user_id=test_user.id,
            type="pdf",
            title="Test Document",
            source_uri="file://test/document.pdf",
            collection_name="test_collection",
        )
        
        result = await service.create_source(source_data)
        
        assert result.id is not None
        assert result.user_id == test_user.id
        assert result.type == "pdf"
        assert result.title == "Test Document"
        assert result.source_uri == "file://test/document.pdf"
        assert result.status == "processing"  # Default status
    
    @pytest.mark.asyncio
    async def test_create_source_with_all_fields(
        self,
        test_db_session: AsyncSession,
        test_user,
    ):
        """All optional fields saved correctly."""
        service = SourceService(test_db_session)
        source_data = SourceCreate(
            user_id=test_user.id,
            type="youtube",
            title="YouTube Video",
            source_uri="https://youtube.com/watch?v=test",
            collection_name="youtube_collection",
            status="processing",
            content_hash="abc123hash",
        )
        
        result = await service.create_source(source_data)
        
        assert result.type == "youtube"
        assert result.status == "processing"
        assert result.content_hash == "abc123hash"
        assert result.created_at is not None


class TestGetSource:
    """Test cases for get_source method."""
    
    @pytest.mark.asyncio
    async def test_get_source_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Retrieves existing source."""
        service = SourceService(test_db_session)
        source = await source_factory(
            user_id=test_user.id,
            title="My Source",
        )
        
        result = await service.get_source(source.id)
        
        assert result is not None
        assert result.id == source.id
        assert result.title == "My Source"
        assert result.user_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_get_source_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound for non-existent ID."""
        service = SourceService(test_db_session)
        with pytest.raises(ResourceNotFound) as exc_info:
            await service.get_source(uuid.uuid4())
        
        assert "Source" in str(exc_info.value)


class TestListSourcesForUser:
    """Test cases for list_sources_for_user method."""
    
    @pytest.mark.asyncio
    async def test_list_sources_for_user(
        self,
        test_db_session: AsyncSession,
        test_user,
        user_factory,
        source_factory,
    ):
        """Returns only user's sources."""
        service = SourceService(test_db_session)
        # Create sources for test user
        await source_factory(user_id=test_user.id, title="Source 1")
        await source_factory(user_id=test_user.id, title="Source 2")
        
        # Create source for different user
        other_user = await user_factory(email="other@example.com")
        await source_factory(user_id=other_user.id, title="Other Source")
        
        result = await service.list_sources_for_user(
            test_user.id,
        )
        
        assert len(result) == 2
        for source in result:
            assert source.user_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_list_sources_pagination(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Skip/limit work correctly."""
        service = SourceService(test_db_session)
        # Create 5 sources
        for i in range(5):
            await source_factory(user_id=test_user.id, title=f"Source {i}")
        
        # Test skip and limit
        result = await service.list_sources_for_user(
            test_user.id,
            skip=2,
            limit=2,
        )
        
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_list_sources_ordered_by_date(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Sources ordered by created_at desc."""
        service = SourceService(test_db_session)
        # Create sources
        source1 = await source_factory(user_id=test_user.id, title="First")
        source2 = await source_factory(user_id=test_user.id, title="Second")
        
        result = await service.list_sources_for_user(
            test_user.id,
        )
        
        # Newest should be first
        assert result[0].id == source2.id
        assert result[1].id == source1.id


class TestUpdateSourceStatus:
    """Test cases for update_source_status method."""
    
    @pytest.mark.asyncio
    async def test_update_source_status_success(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Updates status correctly."""
        from app.db.schemas import SourceStatus
        service = SourceService(test_db_session)
        source = await source_factory(
            user_id=test_user.id,
            status=SourceStatus.processing,
        )
        
        result = await service.update_source_status(
            source.id,
            SourceStatus.ready,
        )
        
        assert result.status == SourceStatus.ready
    
    @pytest.mark.asyncio
    async def test_update_source_status_not_found(
        self,
        test_db_session: AsyncSession,
    ):
        """Raises ResourceNotFound."""
        from app.db.schemas import SourceStatus
        service = SourceService(test_db_session)
        with pytest.raises(ResourceNotFound):
            await service.update_source_status(
                uuid.uuid4(),
                SourceStatus.ready,
            )


class TestUpdateIngestionMetadata:
    """Test cases for update_ingestion_metadata method."""
    
    @pytest.mark.asyncio
    async def test_update_ingestion_metadata(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Updates content_hash and last_ingested_at."""
        service = SourceService(test_db_session)
        source = await source_factory(user_id=test_user.id)
        
        result = await service.update_source_ingestion_metadata(
            source.id,
            content_hash="new_hash_123",
            last_ingested_at=datetime.utcnow(),
        )
        
        assert result.content_hash == "new_hash_123"
        assert result.last_ingested_at is not None
    
    @pytest.mark.asyncio
    async def test_update_ingestion_metadata_partial(
        self,
        test_db_session: AsyncSession,
        test_user,
        source_factory,
    ):
        """Can update only content_hash or timestamp."""
        service = SourceService(test_db_session)
        source = await source_factory(user_id=test_user.id)
        
        # Update only content_hash
        result = await service.update_source_ingestion_metadata(
            source.id,
            content_hash="partial_hash",
        )
        
        assert result.content_hash == "partial_hash"
