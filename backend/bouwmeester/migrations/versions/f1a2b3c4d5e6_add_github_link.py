"""add github_link

Revision ID: f1a2b3c4d5e6
Revises: 2c4d6e8f9a01
Create Date: 2026-05-06 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "2c4d6e8f9a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_link",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "scope_type",
            sa.String(length=32),
            nullable=False,
            comment="lead|initiatief",
        ),
        sa.Column(
            "scope_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column(
            "link_type",
            sa.String(length=32),
            nullable=False,
            comment="branch|pull_request|issue|repo|workflow_run|other",
        ),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("repo", sa.String(length=200), nullable=False),
        sa.Column("ref", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type", "scope_id", "url", name="uq_github_link_scope_url"
        ),
    )
    op.create_index(
        "ix_github_link_scope_id", "github_link", ["scope_id"], unique=False
    )
    op.create_index(
        "ix_github_link_owner_repo", "github_link", ["owner", "repo"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_github_link_owner_repo", table_name="github_link")
    op.drop_index("ix_github_link_scope_id", table_name="github_link")
    op.drop_table("github_link")
