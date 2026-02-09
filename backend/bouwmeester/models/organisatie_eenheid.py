"""OrganisatieEenheid model - organizational hierarchy unit.

The unit itself is a stable anchor with a UUID identity. Mutable properties
(naam, parent, manager) are stored as temporal relations in separate tables,
allowing full history tracking. The legacy columns (naam, parent_id,
manager_id) are kept during the transition and dual-written.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.org_manager import OrganisatieEenheidManager
    from bouwmeester.models.org_naam import OrganisatieEenheidNaam
    from bouwmeester.models.org_parent import OrganisatieEenheidParent
    from bouwmeester.models.person import Person
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


class OrganisatieEenheid(Base):
    __tablename__ = "organisatie_eenheid"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Legacy columns — kept for backward compatibility during transition.
    # Authoritative data lives in the temporal relation tables.
    naam: Mapped[str] = mapped_column(nullable=False)
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

    type: Mapped[str] = mapped_column(
        nullable=False,
        comment=(
            "Hierarchy: ministerie > directoraat_generaal > directie "
            "> afdeling > (cluster|bureau) > team"
        ),
    )
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    geldig_van: Mapped[date] = mapped_column(
        nullable=False,
        server_default=text("CURRENT_DATE"),
    )
    geldig_tot: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Legacy self-referential relationships (still used during transition)
    parent: Mapped[Optional["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
        remote_side="OrganisatieEenheid.id",
        back_populates="children",
    )
    children: Mapped[list["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
        back_populates="parent",
    )

    # Legacy manager relationship (still used during transition)
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

    # Temporal relations
    namen: Mapped[list["OrganisatieEenheidNaam"]] = relationship(
        "OrganisatieEenheidNaam",
        back_populates="eenheid",
        cascade="all, delete-orphan",
        order_by="OrganisatieEenheidNaam.geldig_van.desc()",
    )
    parent_records: Mapped[list["OrganisatieEenheidParent"]] = relationship(
        "OrganisatieEenheidParent",
        back_populates="eenheid",
        foreign_keys="OrganisatieEenheidParent.eenheid_id",
        cascade="all, delete-orphan",
        order_by="OrganisatieEenheidParent.geldig_van.desc()",
    )
    manager_records: Mapped[list["OrganisatieEenheidManager"]] = relationship(
        "OrganisatieEenheidManager",
        back_populates="eenheid",
        cascade="all, delete-orphan",
        order_by="OrganisatieEenheidManager.geldig_van.desc()",
    )
