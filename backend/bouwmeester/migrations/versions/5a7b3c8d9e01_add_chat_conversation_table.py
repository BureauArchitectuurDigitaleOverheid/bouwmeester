"""add chat_conversation table

Revision ID: 5a7b3c8d9e01
Revises: 4c3acd9ee813
Create Date: 2026-02-18 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a7b3c8d9e01"
down_revision: str | None = "4c3acd9ee813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_conversation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "pending_actions",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_chat_conversation_person_id",
        "chat_conversation",
        ["person_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_conversation_person_id", table_name="chat_conversation")
    op.drop_table("chat_conversation")
