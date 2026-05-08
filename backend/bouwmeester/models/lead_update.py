"""LeadUpdatePost model — published update on a lead, used for community page + mail."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.person import Person


class LeadUpdatePost(Base):
    """Per-lead update post: rich body for the project team mail and a short
    public version that surfaces under the casus on /c/:slug.

    `published_at` IS NULL means draft.
    """

    __tablename__ = "lead_update"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titel: Mapped[str] = mapped_column(nullable=False)
    body_internal: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_public: Mapped[str | None] = mapped_column(Text, nullable=True)
    mail_subject: Mapped[str | None] = mapped_column(nullable=True)
    mail_to: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    mail_cc: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="updates")
    published_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[published_by_id]
    )
    created_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[created_by_id]
    )
