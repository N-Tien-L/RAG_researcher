"""E2E journey: source upload → ingestion pipeline → pgvector storage.

Patches only the two I/O boundaries that require live external services:
- ``extract_from_pdf`` (reads a real file from disk)
- ``HuggingFaceTEIEmbedder`` in the ingestion path (calls TEI HTTP server)

Everything else — chunking, DB writes, pgvector inserts, status updates — runs for real.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, Source, User
from tests.e2e.conftest import E2E_EMBEDDING, E2E_PDF_EXTRACTION

pytestmark = pytest.mark.e2e


def _make_embedder_mock() -> MagicMock:
    """Return a MagicMock that mimics HuggingFaceTEIEmbedder for the ingestion path."""
    mock_emb = MagicMock()
    mock_emb.embed_documents = AsyncMock(return_value=[E2E_EMBEDDING])
    mock_emb.dimension = len(E2E_EMBEDDING)
    return mock_emb


class TestSourceProcessJourney:
    """Tests for POST /api/sources/{id}/process ingestion pipeline."""

    @pytest.mark.asyncio
    @patch(
        "app.applications.ingestion_application.extract_from_pdf",
        return_value=E2E_PDF_EXTRACTION,
    )
    @patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder")
    async def test_process_pdf_source_ingests_chunks(
        self,
        mock_embedder_cls: MagicMock,
        mock_extract: MagicMock,
        authenticated_client: AsyncClient,
        test_user: User,
        test_db_session: AsyncSession,
        seeded_source_processing: Source,
    ) -> None:
        """POST /sources/{id}/process stores chunks in pgvector and sets status='ready'.

        Verifies
        --------
        - HTTP 202 response with status='ingested' and chunks_added >= 1.
        - ``source.status`` in the response body is 'ready'.
        - At least one DocumentChunk row exists in the DB for this source.
        """
        mock_embedder_cls.return_value = _make_embedder_mock()

        resp = await authenticated_client.post(
            f"/api/sources/{seeded_source_processing.id}/process"
        )

        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] == "ingested"
        assert data["chunks_added"] >= 1
        assert data["content_hash"]
        assert data["source"]["status"] == "ready"

        # Verify DocumentChunk rows exist in the DB
        result = await test_db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.source_id == str(seeded_source_processing.id)
            )
        )
        chunks = result.scalars().all()
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    @patch(
        "app.applications.ingestion_application.extract_from_pdf",
        return_value=E2E_PDF_EXTRACTION,
    )
    @patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder")
    async def test_process_source_updates_content_hash(
        self,
        mock_embedder_cls: MagicMock,
        mock_extract: MagicMock,
        authenticated_client: AsyncClient,
        seeded_source_processing: Source,
        test_db_session: AsyncSession,
    ) -> None:
        """After processing, content_hash is returned and persisted to the source row."""
        mock_embedder_cls.return_value = _make_embedder_mock()

        resp = await authenticated_client.post(
            f"/api/sources/{seeded_source_processing.id}/process"
        )

        assert resp.status_code == 202, resp.text
        content_hash = resp.json()["content_hash"]
        assert content_hash is not None
        assert len(content_hash) == 64  # SHA-256 hex digest length

        refreshed = await test_db_session.get(Source, seeded_source_processing.id)
        assert refreshed is not None
        assert refreshed.content_hash == content_hash
        assert refreshed.last_ingested_at is not None

    @pytest.mark.asyncio
    async def test_process_source_not_found(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """Processing a non-existent source ID returns 404."""
        resp = await authenticated_client.post(
            f"/api/sources/{uuid.uuid4()}/process"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_process_source_forbidden(
        self,
        authenticated_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory,
    ) -> None:
        """Attempting to process a source owned by another user returns 403."""
        other_user = await user_factory()
        source = Source(
            user_id=other_user.id,
            type="pdf",
            title="Someone Else's PDF",
            status="processing",
            source_uri="file://e2e/other.pdf",
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        resp = await authenticated_client.post(f"/api/sources/{source.id}/process")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("app.api.routes.sources.save_upload_file")
    @patch(
        "app.applications.ingestion_application.extract_from_pdf",
        return_value=E2E_PDF_EXTRACTION,
    )
    @patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder")
    async def test_upload_and_process_full_journey(
        self,
        mock_embedder_cls: MagicMock,
        mock_extract: MagicMock,
        mock_save: MagicMock,
        authenticated_client: AsyncClient,
        test_user: User,
        test_db_session: AsyncSession,
    ) -> None:
        """Full journey: upload PDF → trigger processing → chunks appear in pgvector.

        Steps
        -----
        1. ``POST /api/sources/upload`` — source created with status='processing'.
        2. ``POST /api/sources/{id}/process`` — ingestion pipeline runs.
        3. Response confirms status='ready' and chunks_added >= 1.
        4. DB query confirms DocumentChunk rows for this source.
        """
        mock_save.return_value = Path("e2e/uploaded_test.pdf")
        mock_embedder_cls.return_value = _make_embedder_mock()

        # 1. Upload
        pdf_bytes = b"%PDF-1.4\n%e2e journey test content"
        files = {"file": ("e2e_journey.pdf", BytesIO(pdf_bytes), "application/pdf")}
        upload_resp = await authenticated_client.post(
            "/api/sources/upload",
            files=files,
            data={"title": "E2E Upload & Process"},
        )
        assert upload_resp.status_code == 201, upload_resp.text
        source_id = upload_resp.json()["id"]
        assert upload_resp.json()["status"] == "processing"

        # 2. Process
        process_resp = await authenticated_client.post(
            f"/api/sources/{source_id}/process"
        )
        assert process_resp.status_code == 202, process_resp.text
        process_data = process_resp.json()
        assert process_data["source"]["status"] == "ready"
        assert process_data["chunks_added"] >= 1

        # 3. Verify DB side-effects
        result = await test_db_session.execute(
            select(DocumentChunk).where(DocumentChunk.source_id == source_id)
        )
        assert len(result.scalars().all()) >= 1
