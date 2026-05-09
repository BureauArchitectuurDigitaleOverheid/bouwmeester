"""Pending reconciliation: kandidaat-duplicaten tussen handmatige en TOOI-data.

Wanneer TOOI-sync een organisatie binnenkrijgt waarvan de naam (case-insensitive)
overeenkomt met een bestaande `bron='handmatig'` rij, wordt geen automatische
merge uitgevoerd. In plaats daarvan komt er een reconciliation-rij waar een
admin via de Beheer-UI kan kiezen: mergen op TOOI-rij of negeren.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class PendingReconciliation(Base):
    __tablename__ = "pending_reconciliation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    resource_type: Mapped[str] = mapped_column(
        nullable=False,
        comment="organisatie_eenheid | person",
    )
    handmatige_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID van de bestaande handmatige rij",
    )
    kandidaat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="ID van de TOOI/sync-rij die als duplicate-kandidaat is gevonden",
    )
    kandidaat_bron: Mapped[str] = mapped_column(
        nullable=False,
        comment="tooi | tk_odata | kabinet | organogram_scrape",
    )
    match_reden: Mapped[str] = mapped_column(
        nullable=False,
        comment="naam_exact | naam_normalized | afkorting | tk_persoon_id_match | etc.",
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        nullable=False,
        server_default=text("'open'"),
        comment="open | merged | ignored",
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
