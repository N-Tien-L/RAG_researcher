"""restructure document chunks for pgvector

Revision ID: 7b5cc4f9a3c2
Revises: 21dd7c222ad5
Create Date: 2026-02-03 00:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "7b5cc4f9a3c2"
down_revision: Union[str, Sequence[str], None] = "21dd7c222ad5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def upgrade() -> None:
    """Recreate document_chunks with pgvector-friendly schema and cosine index."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_table("document_chunks")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("chunk_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=EMBEDDING_DIM), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Drop new schema and restore previous structure (simplified)."""
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=EMBEDDING_DIM), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
