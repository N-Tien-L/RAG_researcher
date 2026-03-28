"""drop_collection_name_columns

Revision ID: 9c2f9f5b7a10
Revises: fc5a533f9f45
Create Date: 2026-03-14 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c2f9f5b7a10"
down_revision: Union[str, Sequence[str], None] = "fc5a533f9f45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("document_chunks", "collection_name")
    op.drop_column("sources", "collection_name")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "sources",
        sa.Column(
            "collection_name",
            sa.String(length=255),
            nullable=False,
            server_default="documents",
        ),
    )
    op.alter_column("sources", "collection_name", server_default=None)

    op.add_column(
        "document_chunks",
        sa.Column(
            "collection_name",
            sa.String(length=255),
            nullable=False,
            server_default="documents",
        ),
    )
    op.alter_column("document_chunks", "collection_name", server_default=None)
