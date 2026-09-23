"""Add nieuwsbron en nieuws_alerts_enabled

Vakmedia naast de kamerstukken. Een eigen vinkje per kanaal, omdat een
kanaal dat kamerstukken wil niet vanzelf nieuws wil: dat zijn andere
stukken voor een ander gesprek.

De twee bronnen staan in de migratie omdat ze gemeten zijn (23 september
2026: beide 150 items, teaser 345 respectievelijk 131 tekens) en omdat een
lege tabel betekent dat de feature niets doet tot iemand raadt welke URL
werkt. Een bron uitzetten kan in de database; een bron verzinnen niet.

Revision ID: b8c3e21d75f4
Revises: a7f2d18c94e3
Create Date: 2026-09-23

"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c3e21d75f4"
down_revision: str | None = "a7f2d18c94e3"
branch_labels: str | None = None
depends_on: str | None = None

BRONNEN = [
    ("Binnenlands Bestuur", "https://www.binnenlandsbestuur.nl/feeds/articles.rss"),
    ("iBestuur", "https://ibestuur.nl/feeds/articles.rss"),
]


def upgrade() -> None:
    nieuwsbron = op.create_table(
        "nieuwsbron",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("naam", sa.String(120), nullable=False),
        sa.Column("feed_url", sa.String(500), nullable=False, unique=True),
        sa.Column(
            "actief", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("laatste_ronde_op", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.bulk_insert(
        nieuwsbron,
        [
            {"id": uuid.uuid4(), "naam": naam, "feed_url": url, "actief": True}
            for naam, url in BRONNEN
        ],
    )

    # Naast `parlementaire_alerts_enabled`, niet in plaats daarvan. Een
    # kanaal kan het een willen en het ander niet.
    op.add_column(
        "mattermost_channel_link",
        sa.Column(
            "nieuws_alerts_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "Of artikelen uit de vakpers in dit kanaal verschijnen. "
                "Standaard uit: wie kamerstukken volgt heeft niet vanzelf "
                "om nieuws gevraagd."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("mattermost_channel_link", "nieuws_alerts_enabled")
    op.drop_table("nieuwsbron")
