"""add chat_attachment table

Revision ID: cee2c456b55d
Revises: 5a7b3c8d9e01
Create Date: 2026-02-20 07:15:46.029163

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cee2c456b55d"
down_revision: str | None = "5a7b3c8d9e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_attachment",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("bestandsnaam", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("bestandsgrootte", sa.Integer(), nullable=False),
        sa.Column("pad", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["chat_conversation.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_attachment_conversation_id"),
        "chat_attachment",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_attachment_person_id"),
        "chat_attachment",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_chat_attachment_person_id"),
        table_name="chat_attachment",
    )
    op.drop_index(
        op.f("ix_chat_attachment_conversation_id"),
        table_name="chat_attachment",
    )
    op.drop_table("chat_attachment")
