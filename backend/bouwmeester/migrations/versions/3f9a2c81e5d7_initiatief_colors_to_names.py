"""initiatief colors to names

initiatief.kleur held a raw Tailwind hex (e.g. "#10B981"), which the frontend
rendered as a hand-styled pill with white text on the pastel fill — roughly
2.2:1, well under the WCAG 4.5:1 minimum. The frontend now renders it through
nldd-tag and nldd-icon, which only accept a closed set of color names
(schema.initiatief.INITIATIEF_COLORS) and paint their own accessible text
color per name, so the stored value has to become one of those names.

Checked the data first: all 4 rows are the 4 seed defaults from seed.py, no
custom colors, so this is a fixed translation table rather than a per-row
guess. The column is nullable with no server_default, so only the values move.

Revision ID: 3f9a2c81e5d7
Revises: 6b1e04a7c8d2
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f9a2c81e5d7"
down_revision: str | None = "6b1e04a7c8d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors initiatieven_data in backend/scripts/seed.py. The hexes are Tailwind
# 500-weights; each maps to the nearest Rijkshuisstijl hue, matching the
# choices the lead_column migration (54ec9a7df491) already made for blue,
# orange and purple.
OLD_TO_NEW: dict[str, str] = {
    "#3B82F6": "lintblauw",  # blue-500
    "#10B981": "groen",  # emerald-500
    "#F59E0B": "oranje",  # amber-500
    "#8B5CF6": "paars",  # violet-500
}


def upgrade() -> None:
    conn = op.get_bind()
    for old_kleur, new_kleur in OLD_TO_NEW.items():
        conn.execute(
            sa.text("UPDATE initiatief SET kleur = :new WHERE kleur = :old"),
            {"new": new_kleur, "old": old_kleur},
        )
    # Any other hex (a color picked in an older UI build) is not translatable
    # to a name, and a hex left behind would render as no color at all. NULL is
    # the column's own "no color", which every consumer already handles.
    conn.execute(sa.text("UPDATE initiatief SET kleur = NULL WHERE kleur LIKE '#%'"))


def downgrade() -> None:
    conn = op.get_bind()
    for old_kleur, new_kleur in OLD_TO_NEW.items():
        conn.execute(
            sa.text("UPDATE initiatief SET kleur = :old WHERE kleur = :new"),
            {"old": old_kleur, "new": new_kleur},
        )
