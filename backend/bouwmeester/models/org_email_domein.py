"""Email-domein voor een OrganisatieEenheid.

Gevoed vanuit het Register Internetdomeinen Overheid (RIO). Eén eenheid kan
meerdere domeinen hebben (`minbzk.nl`, `rijksoverheid.nl`, etc.). Gebruikt
voor email -> organisatie matching bij persoon-aanmaak.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


class OrganisatieEmailDomein(Base):
    __tablename__ = "organisatie_email_domein"
    __table_args__ = (
        UniqueConstraint("domein", name="uq_organisatie_email_domein_domein"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    organisatie_eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domein: Mapped[str] = mapped_column(nullable=False, index=True)
    bron: Mapped[str] = mapped_column(
        nullable=False,
        server_default=text("'rio'"),
        comment="rio | handmatig",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisatie_eenheid: Mapped["OrganisatieEenheid"] = relationship(
        "OrganisatieEenheid",
        back_populates="email_domeinen",
    )
