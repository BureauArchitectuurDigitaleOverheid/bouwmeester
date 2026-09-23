"""Add parlementair_signaalcontext

De beschrijving van een initiatief is publiek (`/public/initiatief` geeft
hem uit) en werd tegelijk als context aan de suggestie-prompt gevoerd. Dat
zijn twee publieken met tegengestelde eisen: een mens wil lezen wat het
initiatief doet, een taalmodel moet weten welk woord hier een metafoor is.
Dit is het tweede veld, en het is niet publiek.

Revision ID: a7f2d18c94e3
Revises: e1a4c9f73b26
Create Date: 2026-09-23

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7f2d18c94e3"
down_revision: str | None = "e1a4c9f73b26"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "parlementair_signaalcontext",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        # Polymorf, net als bij `parlementair_abonnement`: geen FK, want de
        # scope kan een initiatief of een lead zijn.
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tekst",
            sa.Text(),
            nullable=False,
            comment=(
                "Wat het taalmodel moet weten om een treffer van ruis te "
                "scheiden. Niet publiek: dit is afstelling, geen omschrijving."
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("scope_type", "scope_id", name="uq_signaalcontext_scope"),
    )


def downgrade() -> None:
    op.drop_table("parlementair_signaalcontext")
