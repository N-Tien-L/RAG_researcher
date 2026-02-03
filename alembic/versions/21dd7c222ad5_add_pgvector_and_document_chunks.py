"""add pgvector extension and document chunks table

Revision ID: 21dd7c222ad5
Revises: 6cbf24872409
Create Date: 2026-02-03 00:00:00.000000

"""
from typing import Sequence, Union

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "21dd7c222ad5"
down_revision: Union[str, Sequence[str], None] = "6cbf24872409"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=EMBEDDING_DIM), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "chunk_index", name="uq_document_chunk_per_source"),
    )

    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_l2_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.execute("DROP EXTENSION IF EXISTS vector")
