"""parlementaire abonnementen op zoektermen

Revision ID: e1a4c9f73b26
Revises: 3f9a2c81e5d7
Create Date: 2026-09-22

Twee tabellen voor het volgen van zoektermen in kamerstukken.

``parlementair_abonnement`` hangt een term aan een initiatief of lead, niet
aan een Mattermost-kanaal. Een kanaal hangt via ``mattermost_channel_link``
(unique op ``channel_id``) al aan precies één scope, dus termen aan het
kanaal hangen legt dezelfde relatie via een omweg die breekt zodra iemand
het kanaal ontkoppelt. Bezorging wordt daarmee een join in plaats van een
tweede configuratieplek.

``parlementair_treffer`` legt vast welke term welk document aandroeg. Dat is
een aparte tabel omdat één document op meerdere termen tegelijk matcht: bij
een meting op 22 september 2026 kwam de startnotitie NLDD binnen op zeven
van de elf geteste termen. Zonder deze normalisatie zou dat ofwel zeven
berichten opleveren, ofwel de informatie welke term aansloeg weggooien.

Er wordt bewust geen ``getraw``-cache-kolom toegevoegd: de documenttekst
past al in ``parlementair_item.document_tekst``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a4c9f73b26"
down_revision: str | Sequence[str] | None = "3f9a2c81e5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parlementair_abonnement",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("term_genormaliseerd", sa.String(255), nullable=False),
        sa.Column("is_frase", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("actief", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("laatste_treffer_op", sa.DateTime(timezone=True), nullable=True),
        sa.Column("treffers_totaal", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "weggeklikt_totaal", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("notitie", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            "term_genormaliseerd",
            name="uq_abonnement_scope_term",
        ),
    )
    op.create_index(
        "ix_parlementair_abonnement_scope_id",
        "parlementair_abonnement",
        ["scope_id"],
    )
    # Elke FK krijgt een index; `test_fk_index_inventory` bewaakt dat.
    op.create_index(
        "ix_parlementair_abonnement_created_by_id",
        "parlementair_abonnement",
        ["created_by_id"],
    )
    # De poller haalt elke ronde de actieve termen op; dat is de enige
    # query die op volume draait.
    op.create_index(
        "ix_parlementair_abonnement_actief",
        "parlementair_abonnement",
        ["actief"],
        postgresql_where=sa.text("actief"),
    )

    op.create_table(
        "parlementair_treffer",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "parlementair_item_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("abonnement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parlementair_item_id"], ["parlementair_item.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["abonnement_id"], ["parlementair_abonnement.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parlementair_item_id",
            "abonnement_id",
            name="uq_treffer_item_abonnement",
        ),
    )
    op.create_index(
        "ix_parlementair_treffer_item",
        "parlementair_treffer",
        ["parlementair_item_id"],
    )
    op.create_index(
        "ix_parlementair_treffer_abonnement",
        "parlementair_treffer",
        ["abonnement_id"],
    )


def downgrade() -> None:
    op.drop_table("parlementair_treffer")
    op.drop_index(
        "ix_parlementair_abonnement_actief", table_name="parlementair_abonnement"
    )
    op.drop_index(
        "ix_parlementair_abonnement_created_by_id",
        table_name="parlementair_abonnement",
    )
    op.drop_index(
        "ix_parlementair_abonnement_scope_id", table_name="parlementair_abonnement"
    )
    op.drop_table("parlementair_abonnement")
