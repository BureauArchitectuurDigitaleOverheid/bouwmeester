"""Persistent dismissal of onboarding feature steps."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class OnboardingDismissal(Base):
    """Tracks permanently dismissed onboarding features per person."""

    __tablename__ = "onboarding_dismissal"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "feature_key",
            name="uq_onboarding_dismissal_person_feature",
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
    )
    feature_key: Mapped[str] = mapped_column(String(50), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    person = relationship("Person", foreign_keys=[person_id])
