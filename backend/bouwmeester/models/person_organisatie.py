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
