"""backfill unit_manager roles from organisatie_eenheid manager_id

Revision ID: bab492de98f7
Revises: 99587849a1a3
Create Date: 2026-03-28 20:34:14.597388

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bab492de98f7"
down_revision: str | None = "99587849a1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfill unit_manager person_role entries for managers defined via
    # the legacy organisatie_eenheid.manager_id column.
    op.execute(
        sa.text("""
            INSERT INTO person_role (
                person_id, role_id, organisatie_eenheid_id, start_datum
            )
            SELECT manager_id, 'unit_manager', id, CURRENT_DATE
            FROM organisatie_eenheid
            WHERE manager_id IS NOT NULL
              AND geldig_tot IS NULL
            ON CONFLICT DO NOTHING
        """)
    )


def downgrade() -> None:
    # Remove only the backfilled unit_manager entries.
    op.execute(
        sa.text("""
            DELETE FROM person_role
            WHERE role_id = 'unit_manager'
              AND organisatie_eenheid_id IN (
                  SELECT id FROM organisatie_eenheid
                  WHERE manager_id = person_role.person_id
              )
        """)
    )
