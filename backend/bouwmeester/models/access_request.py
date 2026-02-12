"""AccessRequest model — tracks access requests from non-whitelisted users."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class AccessRequest(Base):
    __tablename__ = "access_request"
    __table_args__ = (
        Index("ix_access_request_email", "email"),
        Index(
            "uq_access_request_pending_email",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(nullable=False)
    naam: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    deny_reason: Mapped[str | None] = mapped_column(nullable=True)

    reviewed_by = relationship("Person", foreign_keys=[reviewed_by_id])
