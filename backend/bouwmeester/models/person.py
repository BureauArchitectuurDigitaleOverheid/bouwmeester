"""Person model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.attributes import instance_state

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person_email import PersonEmail
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
    from bouwmeester.models.person_phone import PersonPhone


class Person(Base):
    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str | None] = mapped_column(nullable=True)
    functie: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    is_agent: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    api_key_hash: Mapped[str | None] = mapped_column(nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    organisatie_plaatsingen: Mapped[list["PersonOrganisatieEenheid"]] = relationship(
        "PersonOrganisatieEenheid",
        back_populates="person",
        cascade="all, delete-orphan",
    )
    emails: Mapped[list["PersonEmail"]] = relationship(
        "PersonEmail",
        back_populates="person",
        cascade="all, delete-orphan",
    )
    phones: Mapped[list["PersonPhone"]] = relationship(
        "PersonPhone",
        back_populates="person",
        cascade="all, delete-orphan",
    )

    @property
    def default_email(self) -> str | None:
        """Return the default email, falling back to legacy email field."""
        if "emails" not in instance_state(self).dict:
            return self.email
        for e in self.emails:
            if e.is_default:
                return e.email
        return self.email

    @property
    def default_phone(self) -> str | None:
        """Return the default phone number."""
        if "phones" not in instance_state(self).dict:
            return None
        for p in self.phones:
            if p.is_default:
                return p.phone_number
        return None
