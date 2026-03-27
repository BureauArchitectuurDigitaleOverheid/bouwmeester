"""FeatureToggle model - per-eenheid feature visibility configuration."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


class FeatureToggle(Base):
    __tablename__ = "feature_toggle"
    __table_args__ = (
        UniqueConstraint(
            "organisatie_eenheid_id",
            "feature_key",
            name="uq_feature_toggle_eenheid_key",
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
    feature_key: Mapped[str] = mapped_column(nullable=False)
    enabled: Mapped[bool] = mapped_column(
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    organisatie_eenheid: Mapped["OrganisatieEenheid"] = relationship(
        "OrganisatieEenheid",
    )
