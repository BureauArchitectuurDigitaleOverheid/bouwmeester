"""Een RSS-bron die naast de kamerstukken wordt gevolgd.

Een tabel en geen lijst in de code, omdat een bron toevoegen een redactionele
keuze is en geen wijziging van het systeem. Wie merkt dat een vakblad
structureel over dit dossier schrijft, zet de feed erbij; dat hoeft niet langs
een deploy.

Waarom bronnen globaal zijn en niet per initiatief: de feeds dragen geen
zoekfunctie, dus we halen ze één keer op en matchen alle abonnementen
ertegen. Per initiatief een eigen kopie van dezelfde feed zou hetzelfde
verzoek vermenigvuldigen met het aantal dossiers.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Nieuwsbron(Base):
    """Eén feed-url, met de naam die in het bericht komt te staan."""

    __tablename__ = "nieuwsbron"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    naam: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Zoals de bron in het Mattermost-bericht wordt genoemd",
    )
    feed_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    actief: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "Uit betekent: niet meer ophalen. De al gevonden artikelen "
            "blijven staan, net als bij een gepauzeerde zoekterm."
        ),
    )

    laatste_ronde_op: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Wanneer deze feed voor het laatst met succes is gelezen",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
