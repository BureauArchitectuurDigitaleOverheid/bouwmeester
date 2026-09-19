"""verwijder vlam-sleutel, model en base-url uit app_config

Revision ID: d8f2a6c41b75
Revises: c7b3e1d9a204
Create Date: 2026-09-19

Deze drie instellingen komen voortaan alleen uit de omgeving: ``zad env``
voor de sleutel en het model, de ZAD-dienst ``vlam`` voor het adres. Ze uit
het beheerscherm halen is niet genoeg — ``_load_config`` leest AppConfig
vóór de omgeving, dus achtergebleven rijen zouden blijven winnen terwijl ze
niet meer zichtbaar of aanpasbaar zijn. Dat is erger dan de situatie die we
oplossen.

Precies dat ging mis: een ``VLAM_MODEL_ID`` uit februari overrulede stil de
waarde die in ZAD stond, en de logs toonden een fout met het oude model
terwijl het beheerscherm de nieuwe waarde liet zien.

``VLAM_API_URL`` blijft bestaan als noodrem voor een verkeerd platformadres.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8f2a6c41b75"
down_revision: str | Sequence[str] | None = "c7b3e1d9a204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alleen instellingen die een equivalent in de omgeving hebben. VLAM_API_URL
#: staat hier bewust niet bij.
_VERWIJDERDE_KEYS = ("VLAM_API_KEY", "VLAM_BASE_URL", "VLAM_MODEL_ID")


def upgrade() -> None:
    keys = ", ".join(f"'{k}'" for k in _VERWIJDERDE_KEYS)
    op.execute(f"DELETE FROM app_config WHERE key IN ({keys})")  # noqa: S608


def downgrade() -> None:
    # Niets terug te zetten: de waarden stonden in de database en zijn
    # bewust weggehaald. Ze opnieuw aanmaken zou lege rijen opleveren die
    # niets doen, of — erger — de oude waarden terugzetten die we net
    # hebben opgeruimd. Wie terug wil, zet ze via het beheerscherm of
    # draait deze migratie niet.
    pass
