"""add org placement request table

Revision ID: 74d499ccc116
Revises: 4b5754ddc63c
Create Date: 2026-03-26 21:34:41.542117

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "74d499ccc116"
down_revision: str | None = "4b5754ddc63c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_placement_request",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default="pending",
            nullable=False,
            comment="pending|approved|denied",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["decided_by"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_org_placement_request_organisatie_eenheid_id"),
        "org_placement_request",
        ["organisatie_eenheid_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_org_placement_request_person_id"),
        "org_placement_request",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_org_placement_request_person_id"), table_name="org_placement_request"
    )
    op.drop_index(
        op.f("ix_org_placement_request_organisatie_eenheid_id"),
        table_name="org_placement_request",
    )
    op.drop_table("org_placement_request")
