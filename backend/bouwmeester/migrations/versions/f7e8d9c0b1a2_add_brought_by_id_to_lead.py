"""add brought_by_id to lead

Revision ID: f7e8d9c0b1a2
Revises: 91c8f24a28fc
Create Date: 2026-03-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7e8d9c0b1a2"
down_revision: str | None = "91c8f24a28fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead", sa.Column("brought_by_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_lead_brought_by_id"), "lead", ["brought_by_id"], unique=False
    )
    op.create_foreign_key(
        "fk_lead_brought_by",
        "lead",
        "person",
        ["brought_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lead_brought_by", "lead", type_="foreignkey")
    op.drop_index(op.f("ix_lead_brought_by_id"), table_name="lead")
    op.drop_column("lead", "brought_by_id")
