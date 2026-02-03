"""Business logic for sources and ingestion orchestration placeholders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.applications.ingestion_service import IngestionService
from app.db import models, schemas


class ServiceError(Exception):
    """Raised when a business rule is violated or a resource is missing."""


class SourceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # CRUD -------------------------------------------------------------------
    def create_source(self, source_in: schemas.SourceCreate) -> schemas.SourceRead:
        # status defaults to processing at creation
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
        self.db.commit()
        self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)

    def get_source(self, source_id: UUID) -> schemas.SourceRead:
        source = self.db.get(models.Source, source_id)
        if not source:
            raise ServiceError("Source not found")
        return schemas.SourceRead.model_validate(source)

    def list_sources_for_user(self, user_id: UUID) -> List[schemas.SourceRead]:
        sources = (
            self.db.query(models.Source)
            .filter(models.Source.user_id == user_id)
            .order_by(models.Source.created_at.desc())
            .all()
        )
        return [schemas.SourceRead.model_validate(src) for src in sources]

    def update_source_status(
        self, source_id: UUID, status: schemas.SourceStatus
    ) -> schemas.SourceRead:
        source = self.db.get(models.Source, source_id)
        if not source:
            raise ServiceError("Source not found")

        source.status = status.value
        self.db.commit()
        self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)

    # Placeholder ingestion pipeline ----------------------------------------
    def process_and_embed_source(self, source_id: UUID) -> schemas.SourceRead:
        """
        Run ingestion for a Source, handling re-import logic:
        - if content unchanged → skip
        - if changed → delete existing chunks then re-add
        """

        source = self.db.get(models.Source, source_id)
        if not source:
            raise ServiceError("Source not found")

        ingestion_input = source.source_uri or source.external_id or source.title
        if not ingestion_input:
            raise ServiceError("Source has no uri/external_id to ingest")

        # Determine a stable key if missing
        if not source.source_key:
            source.source_key = source.external_id or source.source_uri or str(source.id)

        ingestion_service = IngestionService()

        try:
            source.status = schemas.SourceStatus.processing.value
            self.db.commit()

            result = ingestion_service.ingest(
                source=ingestion_input,
                source_type=source.type,
                collection_name=source.collection_name,
                extra_metadata={
                    "source_name": source.title,
                    "source_uri": source.source_uri,
                    "external_id": source.external_id,
                },
                source_uuid=str(source.id),
                source_key=source.source_key,
                delete_existing=True,
            )

            source.status = schemas.SourceStatus.ready.value
            source.content_hash = result.get("content_hash")
            source.last_ingested_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception as exc:  # broad to ensure status flip to failed
            self.db.rollback()
            source.status = schemas.SourceStatus.failed.value
            self.db.commit()
            raise ServiceError("Processing failed") from exc

        self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)
