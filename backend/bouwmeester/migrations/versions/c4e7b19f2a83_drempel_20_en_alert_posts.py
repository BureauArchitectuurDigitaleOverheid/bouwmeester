"""Drempel naar 20, en bewaar waar een alert is gepost

Twee wijzigingen in één migratie, omdat ze samen één probleem oplossen:
een term die te veel ruis binnenhaalt, en het ontbreken van de knop om dat
te merken of te corrigeren.

De drempel stond op 10. Een meting over 146 beoordeelde stukken (28
september 2026) liet zien dat 20 stukken tussen 10 en 19 scoorden en geen
van alle over het dossier gingen. Tussen 19 en 40 zat een gat in de data.

`parlementair_alert_post` bewaart het post-id van een alert, zodat een
emoji-reactie terug te leiden is naar het stuk. Zonder die tabel kon
wegklikken niet werken, en dat was ook de stand: de teller stond sinds de
bouw op nul.

Revision ID: c4e7b19f2a83
Revises: d1a6f3b8c925
Create Date: 2026-09-28

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e7b19f2a83"
down_revision: str | None = "d1a6f3b8c925"
branch_labels: str | None = None
depends_on: str | None = None

OUDE_DREMPEL = 10
NIEUWE_DREMPEL = 20


def upgrade() -> None:
    op.alter_column(
        "parlementair_abonnement",
        "minimum_relevantie",
        server_default=str(NIEUWE_DREMPEL),
    )

    # De server_default geldt alleen voor nieuwe rijen. Zonder deze update
    # verandert er niets aan de termen die er al staan, en dat is precies
    # het probleem dat deze migratie oplost.
    #
    # Alleen rijen die nog exact op de oude default staan. Wie bewust iets
    # anders heeft ingesteld (0 om niets te missen, 40 voor een brede
    # term) houdt dat; een migratie hoort geen keuze te overschrijven.
    op.execute(
        sa.text(
            "UPDATE parlementair_abonnement "
            "SET minimum_relevantie = :nieuw "
            "WHERE minimum_relevantie = :oud"
        ).bindparams(nieuw=NIEUWE_DREMPEL, oud=OUDE_DREMPEL)
    )

    op.create_table(
        "parlementair_alert_post",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "parlementair_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("parlementair_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(26), nullable=False),
        sa.Column("post_id", sa.String(26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "parlementair_item_id", "channel_id", name="uq_alert_post_item_kanaal"
        ),
    )
    # De namen zijn die van SQLAlchemy's eigen conventie voor
    # `index=True` op het model. Wijken ze af, dan ziet een volgende
    # `alembic revision --autogenerate` de modelindexen als ontbrekend
    # en stelt hij voor ze er nóg een keer bij te maken.
    op.create_index(
        "ix_parlementair_alert_post_parlementair_item_id",
        "parlementair_alert_post",
        ["parlementair_item_id"],
    )
    # De leesrichting is van reactie naar stuk: de websocket krijgt een
    # post-id binnen en moet weten welk item daarbij hoort.
    op.create_index(
        "ix_parlementair_alert_post_post_id", "parlementair_alert_post", ["post_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parlementair_alert_post_post_id", table_name="parlementair_alert_post"
    )
    op.drop_index(
        "ix_parlementair_alert_post_parlementair_item_id",
        table_name="parlementair_alert_post",
    )
    op.drop_table("parlementair_alert_post")

    op.alter_column(
        "parlementair_abonnement",
        "minimum_relevantie",
        server_default=str(OUDE_DREMPEL),
    )
    # De waarden zelf blijven op 20 staan. Terugzetten zou een keuze
    # overschrijven die iemand na deze migratie bewust gemaakt kan hebben,
    # en 20 is geen kapotte waarde.
