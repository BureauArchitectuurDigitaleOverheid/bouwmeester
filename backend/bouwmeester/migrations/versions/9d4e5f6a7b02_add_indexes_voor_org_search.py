"""add indexes voor organisatie-zoek op afkorting en naam-prefix

Search-pad in OrganisatieEenheidRepository.search() matcht op
(lower(afkorting) == query) en (lower(naam) LIKE 'query%') voor
ranking. Zonder index doet PostgreSQL een seq-scan over alle
~1900 rijen — voor nu OK, bij doorgroei naar 5k+ niet meer.

Revision ID: 9d4e5f6a7b02
Revises: 9c3d4e5f6a01
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d4e5f6a7b02"
down_revision: str | None = "9c3d4e5f6a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Functionele lower-index op afkorting voor exact-match-ranking.
    op.create_index(
        "ix_organisatie_eenheid_lower_afkorting",
        "organisatie_eenheid",
        [sa.text("lower(afkorting)")],
        unique=False,
    )
    # Functionele lower-index op naam voor prefix-match (lower(naam) LIKE 'q%').
    op.create_index(
        "ix_organisatie_eenheid_lower_naam",
        "organisatie_eenheid",
        [sa.text("lower(naam)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_organisatie_eenheid_lower_naam", table_name="organisatie_eenheid")
    op.drop_index(
        "ix_organisatie_eenheid_lower_afkorting", table_name="organisatie_eenheid"
    )
