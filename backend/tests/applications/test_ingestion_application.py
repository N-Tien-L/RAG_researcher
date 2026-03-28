"""Tests for IngestionApplicationService - orchestrates document ingestion."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.ingestion_application import IngestionApplicationService
from app.db import schemas
from app.db.models import Source, User
from app.services.exceptions import EmbeddingError, IngestionError, VectorStoreError


@pytest.mark.asyncio
class TestIngestionApplicationService:
    """Test suite for IngestionApplicationService."""

    async def test_process_source_pdf_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test successful PDF source processing."""
        # Create source record
        source = Source(
            title="Test PDF",
            type="pdf",
            source_uri="test.pdf",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        # Mock extraction
        mock_extraction = {
            "page_texts": {"1": "This is page one.", "2": "This is page two."},
            "metadata": {"source_type": "pdf", "total_pages": 2},
        }

        # Mock chunks
        mock_chunks = [
            {"id": str(uuid4()), "text": "This is page one.", "metadata": {}},
            {"id": str(uuid4()), "text": "This is page two.", "metadata": {}},
        ]

        # Mock embeddings
        mock_embeddings = [[0.1] * 768, [0.2] * 768]

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash, \
             patch("app.applications.ingestion_application.insert_chunks") as mock_insert, \
             patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder") as mock_embedder_class:
            
            # Setup mocks
            mock_extract.return_value = mock_extraction
            mock_get_hash.return_value = None  # No existing hash (first import)
            mock_insert.return_value = 2  # 2 chunks inserted
            
            mock_embedder = Mock()
            mock_embedder.embed_documents = AsyncMock(return_value=mock_embeddings)
            mock_embedder_class.return_value = mock_embedder

            # Patch chunking
            with patch.object(service, "_prepare_chunks", return_value=mock_chunks):
                # Execute
                result = await service.process_source(
                    source_id=str(source.id),
                    source="test.pdf",
                    source_type="pdf",
                )

            # Assert result structure
            assert result["chunks_added"] == 2
            assert result["status"] == "ingested"
            assert "content_hash" in result
            assert len(result["ids"]) == 2

            # Verify extraction called
            mock_extract.assert_called_once_with("test.pdf")

            # Verify embedder called
            mock_embedder.embed_documents.assert_called_once()
            texts_embedded = mock_embedder.embed_documents.call_args[0][0]
            assert len(texts_embedded) == 2

            # Verify chunks inserted
            mock_insert.assert_called_once()

    async def test_process_source_youtube_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test successful YouTube source processing."""
        source = Source(
            title="Test Video",
            type="youtube",
            source_uri="https://youtube.com/watch?v=test",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        mock_extraction = {
            "segments": [
                {"text": "First segment", "start": 0, "end": 10},
                {"text": "Second segment", "start": 10, "end": 20},
            ],
            "metadata": {"source_type": "youtube", "duration": 20},
        }

        mock_chunks = [
            {"id": str(uuid4()), "text": "First segment", "metadata": {}},
            {"id": str(uuid4()), "text": "Second segment", "metadata": {}},
        ]

        mock_embeddings = [[0.1] * 768, [0.2] * 768]

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_youtube") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash, \
             patch("app.applications.ingestion_application.insert_chunks") as mock_insert, \
             patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder") as mock_embedder_class:
            
            mock_extract.return_value = mock_extraction
            mock_get_hash.return_value = None
            mock_insert.return_value = 2
            
            mock_embedder = Mock()
            mock_embedder.embed_documents = AsyncMock(return_value=mock_embeddings)
            mock_embedder_class.return_value = mock_embedder

            with patch.object(service, "_prepare_chunks", return_value=mock_chunks):
                result = await service.process_source(
                    source_id=str(source.id),
                    source="https://youtube.com/watch?v=test",
                    source_type="youtube",
                )

            assert result["chunks_added"] == 2
            assert result["status"] == "ingested"
            mock_extract.assert_called_once()

    async def test_process_source_duplicate_detection_skips_reingestion(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that unchanged source skips re-ingestion."""
        source = Source(
            title="Test PDF",
            type="pdf",
            source_uri="test.pdf",
            status="ready",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        mock_extraction = {
            "page_texts": {"1": "Same content"},
            "metadata": {"source_type": "pdf"},
        }

        service = IngestionApplicationService(test_db_session)

        # Compute expected hash
        computed_hash = service._compute_file_hash_from_extraction(mock_extraction)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash:
            
            mock_extract.return_value = mock_extraction
            # Return same hash (content unchanged)
            mock_get_hash.return_value = computed_hash

            result = await service.process_source(
                source_id=str(source.id),
                source="test.pdf",
                source_type="pdf",
            )

        # Assert skipped
        assert result["status"] == "skipped"
        assert result["chunks_added"] == 0
        assert result["content_hash"] == computed_hash

    async def test_process_source_modified_file_reingest(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that modified source deletes old chunks and reingests."""
        source = Source(
            title="Test PDF",
            type="pdf",
            source_uri="test.pdf",
            status="ready",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        # Old extraction (different content)
        old_hash = "old_hash_value"

        # New extraction (modified content)
        mock_extraction = {
            "page_texts": {"1": "New modified content"},
            "metadata": {"source_type": "pdf"},
        }

        mock_chunks = [{"id": str(uuid4()), "text": "New modified content", "metadata": {}}]
        mock_embeddings = [[0.3] * 768]

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash, \
             patch("app.applications.ingestion_application.delete_chunks_by_source") as mock_delete, \
             patch("app.applications.ingestion_application.insert_chunks") as mock_insert, \
             patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder") as mock_embedder_class:
            
            mock_extract.return_value = mock_extraction
            mock_get_hash.return_value = old_hash  # Different hash
            mock_delete.return_value = 5  # Deleted 5 old chunks
            mock_insert.return_value = 1
            
            mock_embedder = Mock()
            mock_embedder.embed_documents = AsyncMock(return_value=mock_embeddings)
            mock_embedder_class.return_value = mock_embedder

            with patch.object(service, "_prepare_chunks", return_value=mock_chunks):
                result = await service.process_source(
                    source_id=str(source.id),
                    source="test.pdf",
                    source_type="pdf",
                )

            # Verify old chunks deleted
            mock_delete.assert_called_once_with(test_db_session, str(source.id))

            # Verify new chunks inserted
            assert result["chunks_added"] == 1
            assert result["status"] == "ingested"

    async def test_process_source_extraction_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling of PDF extraction errors."""
        from app.ingestion.loaders import PDFExtractionError

        source = Source(
            title="Bad PDF",
            type="pdf",
            source_uri="corrupt.pdf",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract:
            mock_extract.side_effect = PDFExtractionError("Corrupted PDF file")

            with pytest.raises(IngestionError) as exc_info:
                await service.process_source(
                    source_id=str(source.id),
                    source="corrupt.pdf",
                    source_type="pdf",
                )

            # Assert error details
            assert exc_info.value.details["stage"] == "extraction"
            assert "Failed to extract content" in exc_info.value.message

        # Verify source status updated to failed
        await test_db_session.refresh(source)
        assert source.status == "failed"

    async def test_process_source_embedding_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling of embedding generation errors."""
        source = Source(
            title="Test PDF",
            type="pdf",
            source_uri="test.pdf",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        mock_extraction = {
            "page_texts": {"1": "Content"},
            "metadata": {"source_type": "pdf"},
        }

        mock_chunks = [{"id": str(uuid4()), "text": "Content", "metadata": {}}]

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash, \
             patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder") as mock_embedder_class:
            
            mock_extract.return_value = mock_extraction
            mock_get_hash.return_value = None
            
            mock_embedder = Mock()
            mock_embedder.embed_documents = AsyncMock(
                side_effect=Exception("Embedding service timeout")
            )
            mock_embedder_class.return_value = mock_embedder

            with patch.object(service, "_prepare_chunks", return_value=mock_chunks):
                with pytest.raises(EmbeddingError) as exc_info:
                    await service.process_source(
                        source_id=str(source.id),
                        source="test.pdf",
                        source_type="pdf",
                    )

                assert "Failed to generate embeddings" in exc_info.value.message

        await test_db_session.refresh(source)
        assert source.status == "failed"

    async def test_process_source_vectorstore_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling of vector store insertion errors."""
        source = Source(
            title="Test PDF",
            type="pdf",
            source_uri="test.pdf",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        mock_extraction = {
            "page_texts": {"1": "Content"},
            "metadata": {"source_type": "pdf"},
        }

        mock_chunks = [{"id": str(uuid4()), "text": "Content", "metadata": {}}]
        mock_embeddings = [[0.1] * 768]

        service = IngestionApplicationService(test_db_session)

        with patch("app.applications.ingestion_application.extract_from_pdf") as mock_extract, \
             patch("app.applications.ingestion_application.get_existing_file_hash") as mock_get_hash, \
             patch("app.applications.ingestion_application.insert_chunks") as mock_insert, \
             patch("app.applications.ingestion_application.HuggingFaceTEIEmbedder") as mock_embedder_class:
            
            mock_extract.return_value = mock_extraction
            mock_get_hash.return_value = None
            mock_insert.side_effect = Exception("Database connection lost")
            
            mock_embedder = Mock()
            mock_embedder.embed_documents = AsyncMock(return_value=mock_embeddings)
            mock_embedder_class.return_value = mock_embedder

            with patch.object(service, "_prepare_chunks", return_value=mock_chunks):
                with pytest.raises(VectorStoreError) as exc_info:
                    await service.process_source(
                        source_id=str(source.id),
                        source="test.pdf",
                        source_type="pdf",
                    )

                assert "Failed to insert chunks" in exc_info.value.message

        await test_db_session.refresh(source)
        assert source.status == "failed"

    async def test_process_source_unsupported_type(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test handling of unsupported source types."""
        source = Source(
            title="Unknown",
            type="pdf",
            source_uri="test.unknown",
            status="processing",
            user_id=test_user.id,
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)

        service = IngestionApplicationService(test_db_session)

        with pytest.raises(IngestionError) as exc_info:
            await service.process_source(
                source_id=str(source.id),
                source="test.unknown",
                source_type="unsupported",
            )

        # Error should be wrapped in IngestionError with "unknown" stage
        assert "Unexpected error during ingestion" in exc_info.value.message

    async def test_compute_content_hash_consistency(self, test_db_session: AsyncSession):
        """Test that content hash is deterministic."""
        service = IngestionApplicationService(test_db_session)

        texts = ["Text one", "Text two"]
        hash1 = service._compute_content_hash(texts, "pdf")
        hash2 = service._compute_content_hash(texts, "pdf")

        # Same inputs = same hash
        assert hash1 == hash2

        # Different inputs = different hash
        hash3 = service._compute_content_hash(["Text one", "Text three"], "pdf")
        assert hash1 != hash3

    async def test_service_initialization(self, test_db_session: AsyncSession):
        """Test service initializes with correct configuration."""
        service = IngestionApplicationService(
            test_db_session,
            max_tokens=500,
            overlap=50,
        )

        assert service.db is test_db_session
        assert service.max_tokens == 500
        assert service.overlap == 50
        assert service.source_service is not None
