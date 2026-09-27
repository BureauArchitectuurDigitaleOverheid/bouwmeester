"""Confirm existing manual placements

From now on only a trusted placement gives access: one a manager made or
approved (bron 'leidinggevende'), or one an official sync brought.  A
manual placement by someone else keeps bron 'handmatig' and is
informational only; a manager's detachering gets bron 'detachering'.

Placements made before this change cannot tell these apart, and today they
all give access: a manager's placement of a new hire, a partner at a
gemeente who works on an initiatief through that gemeente.  So that nobody
loses access at deploy, every active 'handmatig' placement is confirmed
here, inside the internal organisation and in external organisations alike.
Only placements created after deploy need confirmation.

Downgrade is exact: before this revision 'leidinggevende' and
'detachering' did not exist and every manual placement was 'handmatig', so
both turn back into 'handmatig'.

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

CONFIRM_SQL = """
UPDATE person_organisatie_eenheid
SET bron = 'leidinggevende'
WHERE bron = 'handmatig'
  AND (eind_datum IS NULL OR eind_datum >= CURRENT_DATE)
"""

REVERT_SQL = """
UPDATE person_organisatie_eenheid
SET bron = 'handmatig'
WHERE bron IN ('leidinggevende', 'detachering')
"""


def upgrade() -> None:
    op.execute(CONFIRM_SQL)


def downgrade() -> None:
    op.execute(REVERT_SQL)
