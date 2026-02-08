"""Person model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


class Person(Base):
    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    functie: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    is_agent: Mapped[bool] = mapped_column(default=False, server_default="false")
    api_key: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    organisatie_plaatsingen: Mapped[list["PersonOrganisatieEenheid"]] = relationship(
        "PersonOrganisatieEenheid",
        back_populates="person",
        cascade="all, delete-orphan",
    )
