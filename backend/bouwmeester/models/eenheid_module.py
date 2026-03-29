"""EenheidModule model — per-eenheid module toggles."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class EenheidModule(Base):
    """Toggles a module on/off for an organisatie-eenheid."""

    __tablename__ = "eenheid_module"
    __table_args__ = (
        UniqueConstraint(
            "organisatie_eenheid_id",
            "module",
            name="uq_eenheid_module",
        ),
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
    module: Mapped[str] = mapped_column(
        nullable=False,
        comment="corpus|taken|leads|initiatieven|opdrachten",
    )
    enabled: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    eenheid: Mapped["OrganisatieEenheid"] = relationship(  # noqa: F821
        "OrganisatieEenheid"
    )
