"""add stakeholder_assessment table

Revision ID: a5c6d7e8f024
Revises: f4b5c6d7e913
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5c6d7e8f024"
down_revision: str | None = "f4b5c6d7e913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stakeholder_assessment",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "scope_type",
            sa.String(),
            nullable=False,
            comment="corpus_node|initiatief",
        ),
        sa.Column("scope_id", sa.UUID(), nullable=False),
        sa.Column("belang", sa.Integer(), nullable=True),
        sa.Column(
            "houding",
            sa.String(),
            nullable=True,
            comment="tegen|kritisch|neutraal|welwillend|voorstander",
        ),
        sa.Column("invloed", sa.Integer(), nullable=True),
        sa.Column("notitie", sa.Text(), nullable=True),
        sa.Column("assessed_by_id", sa.UUID(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessed_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "scope_type",
            "scope_id",
            name="uq_stakeholder_assessment_person_scope",
        ),
    )
    op.create_index(
        op.f("ix_stakeholder_assessment_person_id"),
        "stakeholder_assessment",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stakeholder_assessment_scope_id"),
        "stakeholder_assessment",
        ["scope_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_stakeholder_assessment_scope_id"),
        table_name="stakeholder_assessment",
    )
    op.drop_index(
        op.f("ix_stakeholder_assessment_person_id"),
        table_name="stakeholder_assessment",
    )
    op.drop_table("stakeholder_assessment")
