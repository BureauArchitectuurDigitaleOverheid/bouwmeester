"""add webauthn_credential table

Revision ID: 76f60edf7c9c
Revises: 025becdecf77
Create Date: 2026-02-14 16:08:26.220352

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "76f60edf7c9c"
down_revision: str | None = "025becdecf77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webauthn_credential",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index(
        op.f("ix_webauthn_credential_person_id"),
        "webauthn_credential",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_webauthn_credential_person_id"),
        table_name="webauthn_credential",
    )
    op.drop_table("webauthn_credential")
