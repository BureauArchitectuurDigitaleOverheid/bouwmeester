"""MattermostPostLink - idempotency-record voor verwerkte Mattermost-posts."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.lead_activity import LeadActivity
    from bouwmeester.models.person import Person


class MattermostPostLink(Base):
    """Eén record per Mattermost-post die we hebben gezien.

    Dient drie doelen:
    - Idempotency: ``post_id`` is unique, dubbele verwerking onmogelijk.
    - Audit-trail: welke post leidde tot welke `LeadActivity` of `SuggestedLead`.
    - Recovery: na reconnect weten we welke posts al verwerkt zijn.
    """

    __tablename__ = "mattermost_post_link"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    post_id: Mapped[str] = mapped_column(
        String(26), unique=True, nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    root_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    scope_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="initiatief|lead",
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    lead_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_activity.id", ondelete="SET NULL"),
        nullable=True,
    )
    suggested_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suggested_lead.id", ondelete="SET NULL"),
        nullable=True,
    )
    mm_user_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    skipped_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="bot_self|noise|no_link|other — voor diagnose",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    lead_activity: Mapped[Optional["LeadActivity"]] = relationship(
        "LeadActivity", foreign_keys=[lead_activity_id]
    )
    person: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[person_id]
    )
