"""PersoonSamenwerkingsverband junction model — temporal lidmaatschap."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person
    from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband


class PersoonSamenwerkingsverband(Base):
    __tablename__ = "persoon_samenwerkingsverband"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "samenwerkingsverband_id",
            "start_datum",
            name="uq_persoon_samenwerkingsverband_lidmaatschap",
        ),
    )

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
    samenwerkingsverband_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("samenwerkingsverband.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rol: Mapped[str | None] = mapped_column(nullable=True)
    start_datum: Mapped[date] = mapped_column(Date, nullable=False)
    eind_datum: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    person: Mapped["Person"] = relationship("Person")
    samenwerkingsverband: Mapped["Samenwerkingsverband"] = relationship(
        "Samenwerkingsverband",
        back_populates="leden",
    )
