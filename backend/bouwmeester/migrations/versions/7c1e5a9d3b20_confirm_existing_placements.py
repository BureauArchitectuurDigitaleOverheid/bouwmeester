"""Confirm existing manual placements

From now on only a trusted placement gives access: one a manager made or
approved (bron 'leidinggevende'), or one an official sync brought.  A
manual placement by someone else keeps bron 'handmatig' and is
informational only; a manager's detachering gets bron 'detachering'.

Placements made before this change cannot tell these apart, and today they
all give access: a manager's placement of a new hire, a partner at a
gemeente who works on an initiatief through that gemeente.  So that nobody
loses access at deploy, every active 'handmatig' placement of an account
(someone who logged in, an agent, or anyone holding a role: see
``core.authority.is_account``) is confirmed here, inside the internal
organisation and in external organisations alike.  A contact's placement
stays informational: anyone with people:update could make one, and a
contact that later logs in gets a placement request for it instead.
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
UPDATE person_organisatie_eenheid AS poe
SET bron = 'leidinggevende'
FROM person AS p
WHERE p.id = poe.person_id
  AND poe.bron = 'handmatig'
  AND (poe.eind_datum IS NULL OR poe.eind_datum >= CURRENT_DATE)
  AND (
    p.oidc_subject IS NOT NULL
    OR p.is_agent
    OR EXISTS (SELECT 1 FROM person_role AS pr WHERE pr.person_id = p.id)
  )
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
