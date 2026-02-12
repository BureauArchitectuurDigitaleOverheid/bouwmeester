"""add person_email and person_phone tables

Revision ID: 97ccf3b922b4
Revises: 6fc2b9738eea
Create Date: 2026-02-12 20:34:20.463704

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "97ccf3b922b4"
down_revision: str | None = "6fc2b9738eea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create person_email table
    op.create_table(
        "person_email",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Create person_phone table
    op.create_table(
        "person_phone",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column(
            "label",
            sa.String(),
            nullable=False,
            comment="werk|mobiel|prive",
        ),
        sa.Column(
            "is_default", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Migrate existing person.email data into person_email table
    op.execute(
        """
        INSERT INTO person_email (id, person_id, email, is_default)
        SELECT gen_random_uuid(), id, email, true
        FROM person
        WHERE email IS NOT NULL
        """
    )

    # Drop the unique constraint on person.email (keep column as fallback)
    op.drop_constraint("person_email_key", "person", type_="unique")


def downgrade() -> None:
    # Restore unique constraint on person.email
    op.create_unique_constraint("person_email_key", "person", ["email"])

    # Drop the new tables
    op.drop_table("person_phone")
    op.drop_table("person_email")
