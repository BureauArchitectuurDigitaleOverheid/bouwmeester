"""Confirm existing manual placements in the internal organisation

From now on a placement made by a manager (or an approved placement request)
is stored with bron 'leidinggevende'; a manual placement by someone else
keeps bron 'handmatig' and becomes a placement request when the person
first logs in (``core.authority.hold_unconfirmed_placements``).

Placements made before this change cannot tell the two apart, and many are
a manager's placement of a new hire who has not logged in yet.  Holding
those would take their placement away on first login, so every active
'handmatig' placement in an internal eenheid, or in an eenheid below one,
is confirmed here.  Only placements created after deploy are held.

Downgrade turns every 'leidinggevende' placement back into 'handmatig': the
code before this revision does not know the value, and 'handmatig' was what
all of them were.

Revision ID: 7c1e5a9d3b20
Revises: 2765100a6afa
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c1e5a9d3b20"
down_revision: str | None = "2765100a6afa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with INTERNAL_EENHEID_TYPES (models/organisatie_eenheid.py);
# a migration does not import application code.
_INTERNAL_TYPES = (
    "ministerie",
    "directoraat_generaal",
    "directie",
    "dienst",
    "afdeling",
    "cluster",
    "bureau",
    "team",
)

CONFIRM_SQL = f"""
WITH RECURSIVE up(start_id, id, parent_id) AS (
    SELECT id, id, parent_id FROM organisatie_eenheid
    UNION
    SELECT up.start_id, oe.id, oe.parent_id
    FROM organisatie_eenheid oe JOIN up ON oe.id = up.parent_id
),
touches_organisation AS (
    SELECT DISTINCT up.start_id AS eenheid_id
    FROM up JOIN organisatie_eenheid t ON t.id = up.id
    WHERE t.type IN ({", ".join(f"'{t}'" for t in _INTERNAL_TYPES)})
)
UPDATE person_organisatie_eenheid
SET bron = 'leidinggevende'
WHERE bron = 'handmatig'
  AND (eind_datum IS NULL OR eind_datum >= CURRENT_DATE)
  AND organisatie_eenheid_id IN (SELECT eenheid_id FROM touches_organisation)
"""

REVERT_SQL = """
UPDATE person_organisatie_eenheid
SET bron = 'handmatig'
WHERE bron = 'leidinggevende'
"""


def upgrade() -> None:
    op.execute(CONFIRM_SQL)


def downgrade() -> None:
    op.execute(REVERT_SQL)
