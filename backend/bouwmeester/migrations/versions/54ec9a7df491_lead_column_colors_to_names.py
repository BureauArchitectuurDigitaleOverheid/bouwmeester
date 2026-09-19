"""lead column colors to names

lead_column.color held raw Tailwind chip classes (e.g. "bg-indigo-100
text-indigo-800"), left over from before the Tailwind removal. The frontend
now renders it through nldd-tag, which only accepts a closed set of color
names (schema.lead_column.LEAD_COLUMN_COLORS), so the stored value has to
become one of those names.

Checked the data first: every row is one of the 7 seed defaults from
DEFAULT_COLUMNS (28 rows total, no custom colors), so this is a fixed
translation table rather than a per-row guess. Also updates the column's
server_default from the old Tailwind string to "neutral".

Revision ID: 54ec9a7df491
Revises: 74c4d614b7f5
Create Date: 2026-09-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "54ec9a7df491"
down_revision: str | None = "d8f2a6c41b75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors DEFAULT_COLUMNS in bouwmeester/schema/lead_column.py.
OLD_TO_NEW: dict[str, str] = {
    "bg-indigo-100 text-indigo-800": "lintblauw",
    "bg-blue-100 text-blue-800": "hemelblauw",
    "bg-yellow-100 text-yellow-800": "geel",
    "bg-orange-100 text-orange-800": "oranje",
    "bg-purple-100 text-purple-800": "paars",
    "bg-green-100 text-green-800": "success",
    "bg-gray-100 text-gray-800": "neutral",
}


def upgrade() -> None:
    conn = op.get_bind()
    for old_color, new_color in OLD_TO_NEW.items():
        conn.execute(
            sa.text("UPDATE lead_column SET color = :new WHERE color = :old"),
            {"new": new_color, "old": old_color},
        )
    op.alter_column(
        "lead_column",
        "color",
        server_default="neutral",
    )


def downgrade() -> None:
    conn = op.get_bind()
    for old_color, new_color in OLD_TO_NEW.items():
        conn.execute(
            sa.text("UPDATE lead_column SET color = :old WHERE color = :new"),
            {"old": old_color, "new": new_color},
        )
    op.alter_column(
        "lead_column",
        "color",
        server_default="bg-gray-100 text-gray-800",
    )
