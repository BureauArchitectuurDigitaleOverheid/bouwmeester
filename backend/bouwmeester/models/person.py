"""Person model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


class Person(Base):
    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    afdeling: Mapped[str | None] = mapped_column(nullable=True)
    functie: Mapped[str | None] = mapped_column(nullable=True)
    rol: Mapped[str | None] = mapped_column(nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    organisatie_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    organisatie_eenheid: Mapped[Optional["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
        back_populates="personen",
        foreign_keys=[organisatie_eenheid_id],
    )
