"""Business logic for sources CRUD operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models, schemas
from app.services.exceptions import ResourceNotFound


class SourceService:
    """Service layer for source CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # CRUD -------------------------------------------------------------------
    async def create_source(self, source_in: schemas.SourceCreate) -> schemas.SourceRead:
        """Create a new source.
        
        Args:
            source_in: Source creation data.
            
        Returns:
            Created source data.
        """
        # Status defaults to processing at creation
        source = models.Source(
            user_id=source_in.user_id,
            type=source_in.type.value,
            title=source_in.title,
            status=source_in.status.value if isinstance(source_in.status, schemas.SourceStatus) else source_in.status,
            collection_name=source_in.collection_name,
            source_key=source_in.source_key,
            source_uri=source_in.source_uri,
            external_id=source_in.external_id,
            content_hash=source_in.content_hash,
            last_ingested_at=source_in.last_ingested_at,
        )
        self.db.add(source)
        await self.db.commit()
        await self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)

    async def get_source(self, source_id: UUID) -> schemas.SourceRead:
        """Get source by ID.
        
        Args:
            source_id: UUID of the source.
            
        Returns:
            Source data.
            
        Raises:
            ResourceNotFound: If source does not exist.
        """
        source = await self.db.get(models.Source, source_id)
        if not source:
            raise ResourceNotFound("Source not found")
        return schemas.SourceRead.model_validate(source)

    async def list_sources_for_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[schemas.SourceRead]:
        """List sources for a user with pagination.
        
        Args:
            user_id: UUID of the user.
            
        Returns:
            List of sources ordered by creation date descending.
        """
        stmt = (
            select(models.Source)
            .where(models.Source.user_id == user_id)
            .order_by(models.Source.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        sources = result.scalars().all()
        return [schemas.SourceRead.model_validate(src) for src in sources]

    async def update_source_status(
        self, source_id: UUID, status: schemas.SourceStatus
    ) -> schemas.SourceRead:
        """Update source status.
        
        Args:
            source_id: UUID of the source.
            status: New status value.
            
        Returns:
            Updated source data.
            
        Raises:
            ResourceNotFound: If source does not exist.
        """
        source = await self.db.get(models.Source, source_id)
        if not source:
            raise ResourceNotFound("Source not found")

        source.status = status.value
        await self.db.commit()
        await self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)

    async def update_source_ingestion_metadata(
        self,
        source_id: UUID,
        content_hash: str | None,
        last_ingested_at: datetime | None = None,
    ) -> schemas.SourceRead:
        """Update source ingestion metadata after processing.
        
        Args:
            source_id: UUID of the source.
            content_hash: Hash of ingested content.
            last_ingested_at: Timestamp of ingestion completion.
            
        Returns:
            Updated source data.
            
        Raises:
            ResourceNotFound: If source does not exist.
        """
        source = await self.db.get(models.Source, source_id)
        if not source:
            raise ResourceNotFound("Source not found")

        if content_hash is not None:
            source.content_hash = content_hash
        if last_ingested_at is not None:
            source.last_ingested_at = last_ingested_at

        await self.db.commit()
        await self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)
