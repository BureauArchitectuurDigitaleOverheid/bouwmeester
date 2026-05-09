"""add wikidata_qid op person en cor_oin verrijkingsveld

Revision ID: 9c3d4e5f6a01
Revises: 9b2c3d4e5f60
Create Date: 2026-05-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c3d4e5f6a01"
down_revision: str | None = "9b2c3d4e5f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person",
        sa.Column(
            "wikidata_qid",
            sa.String(),
            nullable=True,
            comment="Wikidata Q-identifier (bv. Q33181); cross-link naar foto/loopbaan",
        ),
    )
    op.create_index(
        op.f("ix_person_wikidata_qid"),
        "person",
        ["wikidata_qid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_person_wikidata_qid"), table_name="person")
    op.drop_column("person", "wikidata_qid")
