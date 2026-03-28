"""create_chat_message_sources

Revision ID: b7f2c0d91a22
Revises: 6986bcb24a93
Create Date: 2026-03-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7f2c0d91a22"
down_revision: Union[str, Sequence[str], None] = "6986bcb24a93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chat_message_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_message_sources_chat_message_id",
        "chat_message_sources",
        ["chat_message_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chat_message_sources_chat_message_id", table_name="chat_message_sources")
    op.drop_table("chat_message_sources")
