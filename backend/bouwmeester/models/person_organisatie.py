"""PersonOrganisatieEenheid junction model — temporal org membership."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.person import Person


# ``PersonOrganisatieEenheid.bron`` values written by the application.
# A placement a manager of the eenheid made or approved.
PLACEMENT_BRON_LEIDINGGEVENDE = "leidinggevende"
# Contact administration by anyone with people:update: informational.
PLACEMENT_BRON_HANDMATIG = "handmatig"
# A manager linking their own staff to an external organisation: records
# who works where, never access.
PLACEMENT_BRON_DETACHERING = "detachering"

# Trusted placements (see ``core.authz``): confirmed by who decides about
# the members, or brought by an official sync.  Only these give access.
TRUSTED_PLACEMENT_BRONNEN = frozenset(
    {
        PLACEMENT_BRON_LEIDINGGEVENDE,
        "tk_odata",  # services.tk_persoon_sync
        "kabinet_yaml",  # services.kabinet_sync, historische_kabinetten_sync
        "abd_scrape",  # services.abd_scrape
        "roo_leidinggevende",  # ROO import of managers
    }
)


class PersonOrganisatieEenheid(Base):
    __tablename__ = "person_organisatie_eenheid"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organisatie_eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dienstverband: Mapped[str] = mapped_column(
        nullable=False,
        server_default="in_dienst",
        comment="in_dienst|ingehuurd|extern",
    )
    functietitel: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="Bv. 'Tweede Kamerlid', 'Minister', 'SG', 'directeur'",
    )
    bron: Mapped[str] = mapped_column(
        nullable=False,
        server_default=text("'handmatig'"),
        comment="handmatig | tk_odata | kabinet_yaml | roo_leidinggevende",
    )
    start_datum: Mapped[date] = mapped_column(nullable=False)
    eind_datum: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="organisatie_plaatsingen",
    )
    organisatie_eenheid: Mapped["OrganisatieEenheid"] = relationship(
        "OrganisatieEenheid",
        back_populates="plaatsingen",
    )
