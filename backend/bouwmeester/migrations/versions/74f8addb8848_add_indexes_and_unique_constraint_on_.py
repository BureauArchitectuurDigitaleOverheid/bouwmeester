"""add indexes and unique constraint on person_organisatie_eenheid

Revision ID: 74f8addb8848
Revises: 233399b40e1a
Create Date: 2026-02-08 17:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "74f8addb8848"
down_revision: str | None = "233399b40e1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_person_organisatie_eenheid_person_id",
        "person_organisatie_eenheid",
        ["person_id"],
    )
    op.create_index(
        "ix_person_organisatie_eenheid_org_id",
        "person_organisatie_eenheid",
        ["organisatie_eenheid_id"],
    )
    # Partial unique index: prevent duplicate active placements
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_placement
        ON person_organisatie_eenheid (person_id, organisatie_eenheid_id)
        WHERE eind_datum IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_placement")
    op.drop_index(
        "ix_person_organisatie_eenheid_org_id",
        table_name="person_organisatie_eenheid",
    )
    op.drop_index(
        "ix_person_organisatie_eenheid_person_id",
        table_name="person_organisatie_eenheid",
    )
