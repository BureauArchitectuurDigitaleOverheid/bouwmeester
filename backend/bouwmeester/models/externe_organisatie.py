"""ExterneOrganisatie model - external organisations (ICTU, Logius, VNG, etc.)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class ExterneOrganisatie(Base):
    __tablename__ = "externe_organisatie"
    __table_args__ = (
        CheckConstraint(
            "type IN ('uitvoeringsorganisatie', 'zbo', 'koepelorganisatie', "
            "'stichting', 'marktpartij', 'overig')",
            name="ck_externe_organisatie_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    afkorting: Mapped[str | None] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(
        comment="uitvoeringsorganisatie|zbo|koepelorganisatie|stichting|marktpartij|overig",
        nullable=False,
    )
    kvk_nummer: Mapped[str | None] = mapped_column(nullable=True)
    website: Mapped[str | None] = mapped_column(nullable=True)
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
