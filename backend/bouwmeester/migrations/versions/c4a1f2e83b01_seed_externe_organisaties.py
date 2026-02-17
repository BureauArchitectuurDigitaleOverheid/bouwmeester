"""seed reference data: externe organisaties

Revision ID: c4a1f2e83b01
Revises: 8907cbd8af74
Create Date: 2026-02-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a1f2e83b01"
down_revision: str | None = "8907cbd8af74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reference data: known external organisations in the Dutch government ICT landscape.
# These are stable, well-known entities that should always be available.
EXTERNE_ORGANISATIES = [
    {
        "naam": "Logius",
        "afkorting": "Logius",
        "type": "uitvoeringsorganisatie",
        "beschrijving": (
            "Beheert en ontwikkelt de generieke digitale overheidsinfrastructuur "
            "(DigiD, MijnOverheid, PKIoverheid)."
        ),
    },
    {
        "naam": "ICTU",
        "afkorting": "ICTU",
        "type": "uitvoeringsorganisatie",
        "beschrijving": (
            "Advies- en projectorganisatie voor de overheid op het gebied van "
            "ICT en innovatie."
        ),
    },
    {
        "naam": "Vereniging van Nederlandse Gemeenten",
        "afkorting": "VNG",
        "type": "koepelorganisatie",
        "beschrijving": (
            "Behartigt de belangen van alle 342 Nederlandse gemeenten. "
            "Ondersteunt gemeenten bij digitale transformatie."
        ),
    },
    {
        "naam": "Geonovum",
        "afkorting": "Geonovum",
        "type": "stichting",
        "beschrijving": "Ontwikkelt en beheert geo-standaarden voor de overheid.",
    },
    {
        "naam": "RINIS",
        "afkorting": "RINIS",
        "type": "stichting",
        "beschrijving": (
            "Routeringsinstituut voor (inter)nationale informatiestromen "
            "in de sociale zekerheid."
        ),
    },
    {
        "naam": "Rijksdienst voor Identiteitsgegevens",
        "afkorting": "RvIG",
        "type": "uitvoeringsorganisatie",
        "beschrijving": (
            "Beheerder van de Basisregistratie Personen (BRP) en "
            "identiteitsinfrastructuur."
        ),
    },
    {
        "naam": "Kamer van Koophandel",
        "afkorting": "KvK",
        "type": "zbo",
        "beschrijving": (
            "Beheerder van het Handelsregister en ondersteuner van ondernemers."
        ),
    },
    {
        "naam": "Rijksdienst voor het Wegverkeer",
        "afkorting": "RDW",
        "type": "zbo",
        "beschrijving": (
            "Beheerder van het kentekenregister en toelating van voertuigen."
        ),
    },
    {
        "naam": "CIBG",
        "afkorting": "CIBG",
        "type": "uitvoeringsorganisatie",
        "beschrijving": (
            "Uitvoeringsorganisatie voor registers in de zorg, onderwijs en justitie."
        ),
    },
    {
        "naam": "Atos Nederland",
        "afkorting": "Atos",
        "type": "marktpartij",
        "beschrijving": (
            "IT-dienstverlener, voert opdrachten uit voor diverse overheidssystemen."
        ),
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for org in EXTERNE_ORGANISATIES:
        # Idempotent: only insert if naam does not yet exist.
        conn.execute(
            sa.text(
                "INSERT INTO externe_organisatie "
                "(id, naam, afkorting, type, beschrijving, created_at)"
                " VALUES "
                "(gen_random_uuid(), "
                "  :naam, :afkorting, :type, :beschrijving, now())"
                " ON CONFLICT (naam) DO NOTHING"
            ),
            org,
        )


def downgrade() -> None:
    conn = op.get_bind()
    for org in EXTERNE_ORGANISATIES:
        conn.execute(
            sa.text("DELETE FROM externe_organisatie WHERE naam = :naam"),
            {"naam": org["naam"]},
        )
