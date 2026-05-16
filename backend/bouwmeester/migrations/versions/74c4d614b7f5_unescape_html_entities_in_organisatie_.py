"""unescape html entities in organisatie names

Bestaande rijen zijn geimporteerd voordat de import-extractie HTML-entities
ontescapete. Namen als "Directie Ambtenaar &amp; Organisatie (A&amp;O)" staan
letterlijk in de DB. Deze data-only migratie draait html.unescape() over
organisatie_eenheid.naam en .afkorting voor elke rij die nog een entity bevat.

Geen schema-wijziging. downgrade() is een no-op: re-escapen is niet
betrouwbaar omkeerbaar (we weten niet welke '&' origineel '&amp;' was).

Revision ID: 74c4d614b7f5
Revises: 9d4e5f6a7b02
Create Date: 2026-05-16 00:00:00.000000

"""

import html
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "74c4d614b7f5"
down_revision: str | None = "9d4e5f6a7b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, naam, afkorting FROM organisatie_eenheid "
            "WHERE naam LIKE '%&%;%' OR afkorting LIKE '%&%;%'"
        )
    ).fetchall()
    for row_id, naam, afkorting in rows:
        new_naam = html.unescape(naam) if naam is not None else None
        new_afkorting = html.unescape(afkorting) if afkorting is not None else None
        if new_naam == naam and new_afkorting == afkorting:
            continue
        conn.execute(
            sa.text(
                "UPDATE organisatie_eenheid SET naam = :naam, afkorting = :afkorting "
                "WHERE id = :id"
            ),
            {"naam": new_naam, "afkorting": new_afkorting, "id": row_id},
        )


def downgrade() -> None:
    # No-op: re-escaping is not reliably reversible.
    pass
