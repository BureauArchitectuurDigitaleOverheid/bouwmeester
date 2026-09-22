"""ParlementairTreffer - koppelt een geïmporteerd item aan de term die het aandroeg.

Eén document matcht in de praktijk op meerdere termen tegelijk: de
startnotitie NLDD van 21 september 2026 kwam bij een meting op zeven van de
elf geteste termen binnen. Daarom is de treffer een aparte rij en niet een
kolom op het item: het item wordt één keer geïmporteerd en één keer gepost,
met alle termen die hem aandroegen eronder.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class ParlementairTreffer(Base):
    """Eén (item, abonnement)-paar."""

    __tablename__ = "parlementair_treffer"
    __table_args__ = (
        UniqueConstraint(
            "parlementair_item_id",
            "abonnement_id",
            name="uq_treffer_item_abonnement",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    parlementair_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parlementair_item.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    abonnement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parlementair_abonnement.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
