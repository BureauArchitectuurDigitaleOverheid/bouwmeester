"""add onboarding_dismissal

Revision ID: 2d4ae903b0f0
Revises: b5e3c1a2f490
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2d4ae903b0f0"
down_revision = "b5e3c1a2f490"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_dismissal",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("person.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_key", sa.String(50), nullable=False),
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "person_id", "feature_key", name="uq_onboarding_dismissal_person_feature"
        ),
    )


def downgrade() -> None:
    op.drop_table("onboarding_dismissal")
