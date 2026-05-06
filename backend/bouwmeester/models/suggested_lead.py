"""SuggestedLead - LLM-voorgestelde lead op basis van een Mattermost-bericht."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.person import Person


STATUS_PENDING = "pending"
STATUS_APPROVED_NEW = "approved_new"
STATUS_APPROVED_LINKED = "approved_linked"
STATUS_REJECTED = "rejected"


class SuggestedLead(Base):
    """Voorstel om van een Mattermost-bericht een lead te maken.

    Approval gebeurt in Mattermost zelf (interactive buttons) of via een
    fallback-lijst in de UI. Bij approval wordt ``status`` bijgewerkt en
    ``approved_lead_id`` gezet.
    """

    __tablename__ = "suggested_lead"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="mattermost",
        server_default="mattermost",
    )
    source_post_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_channel_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_root_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    initiatief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("initiatief.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_title: Mapped[str] = mapped_column(String(500), nullable=False)
    proposed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_existing_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STATUS_PENDING,
        server_default=STATUS_PENDING,
        comment="pending|approved_new|approved_linked|rejected",
        index=True,
    )
    mm_thread_post_id: Mapped[str | None] = mapped_column(
        String(26),
        nullable=True,
        comment="Bot-reply-post met de approval-knoppen, voor latere edit",
    )
    approved_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_source: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="mattermost|ui",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    initiatief: Mapped[Optional["Initiatief"]] = relationship(
        "Initiatief", foreign_keys=[initiatief_id]
    )
    match_existing_lead: Mapped[Optional["Lead"]] = relationship(
        "Lead", foreign_keys=[match_existing_lead_id]
    )
    approved_lead: Mapped[Optional["Lead"]] = relationship(
        "Lead", foreign_keys=[approved_lead_id]
    )
    reviewed_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[reviewed_by_id]
    )
