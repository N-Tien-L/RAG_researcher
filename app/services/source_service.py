"""Business logic for sources and ingestion orchestration placeholders."""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

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
        Placeholder for the ingestion pipeline.

        Intended flow:
        1. Load document (PDF/YouTube/text) based on Source metadata.
        2. Chunk and embed via TEI/Ollama.
        3. Upsert into ChromaDB.
        4. Mark Source as ready (or failed on error).
        """

        source = self.db.get(models.Source, source_id)
        if not source:
            raise ServiceError("Source not found")

        try:
            source.status = schemas.SourceStatus.processing.value
            self.db.commit()

            # TODO: hook up real ingestion + embedding logic here

            source.status = schemas.SourceStatus.ready.value
            self.db.commit()
        except Exception as exc:  # broad to ensure status flip to failed
            self.db.rollback()
            source.status = schemas.SourceStatus.failed.value
            self.db.commit()
            raise ServiceError("Processing failed") from exc

        self.db.refresh(source)
        return schemas.SourceRead.model_validate(source)
