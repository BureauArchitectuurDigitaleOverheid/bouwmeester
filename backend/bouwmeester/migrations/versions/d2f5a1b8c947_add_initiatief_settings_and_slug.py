"""add initiatief settings and slug

Revision ID: d2f5a1b8c947
Revises: c1d4e7a3b9f2
Create Date: 2026-05-05

"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f5a1b8c947"
down_revision: str | None = "c1d4e7a3b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_RESERVED = frozenset(
    {"api", "auth", "admin", "c", "i", "public", "health", "static", "assets"}
)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    hyphenated = _NON_ALNUM.sub("-", ascii_only.lower())
    return hyphenated.strip("-")


def upgrade() -> None:
    op.add_column("initiatief", sa.Column("slug", sa.String(), nullable=True))
    op.add_column(
        "initiatief",
        sa.Column(
            "funnel_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "initiatief",
        sa.Column(
            "public_page_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "initiatief", sa.Column("score_strategisch_label", sa.String(), nullable=True)
    )
    op.add_column(
        "initiatief", sa.Column("score_politiek_label", sa.String(), nullable=True)
    )
    op.add_column(
        "initiatief", sa.Column("score_positie_label", sa.String(), nullable=True)
    )

    # Backfill slugs from existing naam values, ensuring uniqueness.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, naam FROM initiatief")).fetchall()
    used: set[str] = set()
    for row_id, naam in rows:
        base = _slugify(naam or "")
        if not base or base in _RESERVED:
            continue
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        bind.execute(
            sa.text("UPDATE initiatief SET slug = :slug WHERE id = :id"),
            {"slug": candidate, "id": row_id},
        )

    op.create_unique_constraint("uq_initiatief_slug", "initiatief", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_initiatief_slug", "initiatief", type_="unique")
    op.drop_column("initiatief", "score_positie_label")
    op.drop_column("initiatief", "score_politiek_label")
    op.drop_column("initiatief", "score_strategisch_label")
    op.drop_column("initiatief", "public_page_enabled")
    op.drop_column("initiatief", "funnel_enabled")
    op.drop_column("initiatief", "slug")
