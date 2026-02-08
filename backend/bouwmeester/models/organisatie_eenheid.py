"""OrganisatieEenheid model - organizational hierarchy unit."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


class OrganisatieEenheid(Base):
    __tablename__ = "organisatie_eenheid"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(
        nullable=False,
        comment=(
            "e.g. ministerie|directoraat_generaal|directie|dienst|bureau|afdeling|team"
        ),
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Self-referential relationships
    parent: Mapped[Optional["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
        remote_side="OrganisatieEenheid.id",
        back_populates="children",
    )
    children: Mapped[list["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    # Manager of this unit
    manager: Mapped[Optional["Person"]] = relationship(
        "Person",
        foreign_keys=[manager_id],
        lazy="joined",
    )

    # Placements (people assigned to this unit via junction table)
    plaatsingen: Mapped[list["PersonOrganisatieEenheid"]] = relationship(
        "PersonOrganisatieEenheid",
        back_populates="organisatie_eenheid",
        cascade="all, delete-orphan",
    )
