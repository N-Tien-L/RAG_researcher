"""Tests for pgvector store operations."""

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.vectorstore.pgvector_store import (
    get_existing_file_hash,
    delete_chunks_by_source,
    insert_chunks,
    query_chunks,
)
from app.services.exceptions import VectorStoreError


class TestGetExistingFileHash:
    """Tests for get_existing_file_hash function."""
    
    @pytest.mark.asyncio
    async def test_get_existing_file_hash_found(self, test_db_session: AsyncSession):
        """Returns file hash when chunks exist for source."""
        # Insert a chunk first
        chunks = [{"id": "test-chunk-1", "text": "Test content"}]
        embeddings = [[0.1] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="test-source-123",
            file_hash="abc123hash",
        )
        
        # Query for file hash
        file_hash = await get_existing_file_hash(test_db_session, "test-source-123")
        
        assert file_hash == "abc123hash"
    
    @pytest.mark.asyncio
    async def test_get_existing_file_hash_not_found(self, test_db_session: AsyncSession):
        """Returns None when no chunks exist for source."""
        file_hash = await get_existing_file_hash(test_db_session, "nonexistent-source")
        
        assert file_hash is None


class TestDeleteChunksBySource:
    """Tests for delete_chunks_by_source function."""
    
    @pytest.mark.asyncio
    async def test_delete_chunks_by_source_success(self, test_db_session: AsyncSession):
        """Successfully deletes all chunks for a source."""
        # Insert chunks
        chunks = [
            {"id": "chunk-1", "text": "Content 1"},
            {"id": "chunk-2", "text": "Content 2"},
            {"id": "chunk-3", "text": "Content 3"},
        ]
        embeddings = [[0.1] * 384, [0.2] * 384, [0.3] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="source-to-delete",
            file_hash="hash123",
        )
        
        # Delete chunks
        deleted_count = await delete_chunks_by_source(test_db_session, "source-to-delete")
        
        assert deleted_count == 3
        
        # Verify they're actually gone
        file_hash = await get_existing_file_hash(test_db_session, "source-to-delete")
        assert file_hash is None
    
    @pytest.mark.asyncio
    async def test_delete_chunks_by_source_nonexistent(self, test_db_session: AsyncSession):
        """Deleting nonexistent source returns 0."""
        deleted_count = await delete_chunks_by_source(test_db_session, "does-not-exist")
        
        assert deleted_count == 0
    
    @pytest.mark.asyncio
    async def test_delete_chunks_preserves_other_sources(self, test_db_session: AsyncSession):
        """Deletion is scoped to specific source only."""
        # Insert chunks for two different sources
        chunks_a = [{"id": "a-1", "text": "Source A content"}]
        chunks_b = [{"id": "b-1", "text": "Source B content"}]
        embeddings = [[0.1] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_a,
            embeddings=embeddings,
            source_id="source-a",
            file_hash="hash-a",
        )
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_b,
            embeddings=embeddings,
            source_id="source-b",
            file_hash="hash-b",
        )
        
        # Delete only source-a
        await delete_chunks_by_source(test_db_session, "source-a")
        
        # Source A should be gone
        hash_a = await get_existing_file_hash(test_db_session, "source-a")
        assert hash_a is None
        
        # Source B should still exist
        hash_b = await get_existing_file_hash(test_db_session, "source-b")
        assert hash_b == "hash-b"
    
    @pytest.mark.asyncio
    async def test_delete_chunks_error_handling(self, test_db_session: AsyncSession):
        """Raises VectorStoreError on database error."""
        with patch.object(test_db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            with patch.object(test_db_session, 'rollback', new_callable=AsyncMock) as mock_rollback:
                mock_execute.side_effect = Exception("Database error")
                
                with pytest.raises(VectorStoreError) as exc_info:
                    await delete_chunks_by_source(test_db_session, "test-source")
                
                assert "Failed to delete chunks" in str(exc_info.value)
                # Verify rollback was called
                assert mock_rollback.call_count == 1


class TestInsertChunks:
    """Tests for insert_chunks function."""
    
    @pytest.mark.asyncio
    async def test_insert_chunks_success(self, test_db_session: AsyncSession):
        """Successfully inserts chunks with embeddings."""
        chunks = [
            {"id": "chunk-1", "text": "First chunk"},
            {"id": "chunk-2", "text": "Second chunk"},
        ]
        embeddings = [[0.1] * 384, [0.2] * 384]
        
        inserted_count = await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="test-source",
            file_hash="test-hash",
        )
        
        assert inserted_count == 2
    
    @pytest.mark.asyncio
    async def test_insert_chunks_single_chunk(self, test_db_session: AsyncSession):
        """Can insert a single chunk."""
        chunks = [{"id": "single-chunk", "text": "Only chunk"}]
        embeddings = [[0.5] * 384]
        
        inserted_count = await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="single-source",
            file_hash="single-hash",
        )
        
        assert inserted_count == 1
        
        # Verify it exists
        file_hash = await get_existing_file_hash(test_db_session, "single-source")
        assert file_hash == "single-hash"
    
    @pytest.mark.asyncio
    async def test_insert_chunks_empty_list(self, test_db_session: AsyncSession):
        """Inserting empty list returns 0."""
        inserted_count = await insert_chunks(
            test_db_session,
            chunks=[],
            embeddings=[],
            source_id="empty-source",
            file_hash="empty-hash",
        )
        
        assert inserted_count == 0
    
    @pytest.mark.asyncio
    async def test_insert_chunks_large_batch(self, test_db_session: AsyncSession):
        """Can insert many chunks at once."""
        num_chunks = 50
        chunks = [{"id": f"chunk-{i}", "text": f"Content {i}"} for i in range(num_chunks)]
        embeddings = [[0.1 * i] * 384 for i in range(num_chunks)]
        
        inserted_count = await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="large-batch",
            file_hash="large-hash",
        )
        
        assert inserted_count == num_chunks


class TestInsertChunksErrorHandling:
    """Tests for insert_chunks error handling."""
    
    @pytest.mark.asyncio
    async def test_insert_chunks_database_error(self, test_db_session: AsyncSession):
        """Raises VectorStoreError on database error."""
        chunks = [{"id": "error-chunk", "text": "Error test"}]
        embeddings = [[0.1] * 384]
        
        with patch.object(test_db_session, 'commit', new_callable=AsyncMock) as mock_commit:
            with patch.object(test_db_session, 'rollback', new_callable=AsyncMock) as mock_rollback:
                mock_commit.side_effect = Exception("Database commit failed")
                
                with pytest.raises(VectorStoreError) as exc_info:
                    await insert_chunks(
                        test_db_session,
                        chunks=chunks,
                        embeddings=embeddings,
                        source_id="error-source",
                        file_hash="error-hash",
                    )
                
                assert "Failed to insert chunks" in str(exc_info.value)
                # Verify rollback was called
                assert mock_rollback.call_count == 1


class TestQueryChunks:
    """Tests for query_chunks function."""
    
    @pytest.mark.asyncio
    async def test_query_chunks_basic(self, test_db_session: AsyncSession):
        """Basic vector similarity query returns results."""
        # Insert test chunks
        chunks = [
            {"id": "doc-1", "text": "Machine learning is fascinating"},
            {"id": "doc-2", "text": "Python is a programming language"},
            {"id": "doc-3", "text": "Data science uses statistics"},
        ]
        # Create embeddings (in real app, from actual embedder)
        embeddings = [
            [0.9] * 384,  # Similar to query
            [0.5] * 384,
            [0.3] * 384,
        ]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="query-test",
            file_hash="query-hash",
        )
        
        # Query with similar embedding
        query_embedding = [0.95] * 384
        results = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=2,
        )
        
        assert len(results) <= 2
        assert len(results) > 0
        
        # Check result structure
        for result in results:
            assert "id" in result
            assert "text" in result
            assert "source_id" in result
            assert "distance" in result
            assert "score" in result
            assert "metadata" in result
    
    @pytest.mark.asyncio
    async def test_query_chunks_respects_top_k(self, test_db_session: AsyncSession):
        """Query respects top_k parameter."""
        # Insert 10 chunks
        chunks = [{"id": f"chunk-{i}", "text": f"Content {i}"} for i in range(10)]
        embeddings = [[0.1 + i * 0.05] * 384 for i in range(10)]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="topk-test",
            file_hash="topk-hash",
        )
        
        # Query with top_k=3
        query_embedding = [0.5] * 384
        results = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=3,
        )
        
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_query_chunks_filters_by_source_id(self, test_db_session: AsyncSession):
        """Query can filter by source_id."""
        # Insert chunks from two sources
        chunks_a = [{"id": "a-1", "text": "Source A"}]
        chunks_b = [{"id": "b-1", "text": "Source B"}]
        embedding = [[0.7] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_a,
            embeddings=embedding,
            source_id="source-a",
            file_hash="hash-a",
        )
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_b,
            embeddings=embedding,
            source_id="source-b",
            file_hash="hash-b",
        )
        
        # Query filtered by source-a
        query_embedding = [0.7] * 384
        results = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=10,
            where={"source_id": "source-a"},
        )
        
        assert len(results) == 1
        assert results[0]["source_id"] == "source-a"
    
    @pytest.mark.asyncio
    async def test_query_chunks_empty_store(self, test_db_session: AsyncSession):
        """Query on empty store returns empty list."""
        query_embedding = [0.5] * 384
        results = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=5,
        )
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_query_chunks_filters_by_source_ids(self, test_db_session: AsyncSession):
        """Query only returns results from specified source IDs."""
        chunks_1 = [{"id": "chunk-src-1", "text": "Content from source 1"}]
        chunks_2 = [{"id": "chunk-src-2", "text": "Content from source 2"}]
        embedding = [[0.5] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_1,
            embeddings=embedding,
            source_id="test-source-1",
            file_hash="test-hash-1",
        )
        
        await insert_chunks(
            test_db_session,
            chunks=chunks_2,
            embeddings=embedding,
            source_id="test-source-2",
            file_hash="test-hash-2",
        )
        
        # Query only source-1
        query_embedding = [0.5] * 384
        results_1 = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=10,
            where={"source_ids": ["test-source-1"]},
        )
        
        # Query only source-2
        results_2 = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=10,
            where={"source_ids": ["test-source-2"]},
        )
        
        # Both should have results, but from different sources
        assert len(results_1) == 1
        assert len(results_2) == 1
        assert results_1[0]["source_id"] == "test-source-1"
        assert results_2[0]["source_id"] == "test-source-2"
    
    @pytest.mark.asyncio
    async def test_query_chunks_score_calculation(self, test_db_session: AsyncSession):
        """Verify score is calculated as 1 - distance."""
        chunks = [{"id": "test-chunk", "text": "Test content"}]
        embeddings = [[0.5] * 384]
        
        await insert_chunks(
            test_db_session,
            chunks=chunks,
            embeddings=embeddings,
            source_id="score-test",
            file_hash="score-hash",
        )
        
        query_embedding = [0.5] * 384
        results = await query_chunks(
            test_db_session,
            embedding=query_embedding,
            top_k=1,
        )
        
        assert len(results) == 1
        result = results[0]
        
        # Score should be 1 - distance
        assert abs(result["score"] - (1 - result["distance"])) < 0.0001
        
        # For identical embeddings, distance should be ~0, score ~1
        assert result["distance"] < 0.1  # Very similar
        assert result["score"] > 0.9  # High similarity


class TestQueryChunksErrorHandling:
    """Tests for query_chunks error handling."""
    
    @pytest.mark.asyncio
    async def test_query_chunks_database_error(self, test_db_session: AsyncSession):
        """Raises VectorStoreError on database error."""
        query_embedding = [0.5] * 384
        
        with patch.object(test_db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Database query failed")
            
            with pytest.raises(VectorStoreError) as exc_info:
                await query_chunks(
                    test_db_session,
                    embedding=query_embedding,
                    top_k=5,
                )
            
            assert "Failed to query chunks" in str(exc_info.value)
