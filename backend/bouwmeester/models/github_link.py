"""GitHubLink — koppelt een GitHub-resource aan een lead of initiatief.

Polymorf: `scope_type` ∈ {lead, initiatief}, `scope_id` is geen DB-FK omdat
het naar verschillende tabellen kan wijzen. De route checkt scope vóór gebruik
(zelfde patroon als `MattermostChannelLink`).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person


SCOPE_LEAD = "lead"
SCOPE_INITIATIEF = "initiatief"


class GitHubLink(Base):
    __tablename__ = "github_link"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    scope_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="lead|initiatief",
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    link_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="branch|pull_request|issue|repo|workflow_run|other",
    )
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    created_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[created_by_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "scope_type", "scope_id", "url", name="uq_github_link_scope_url"
        ),
        Index("ix_github_link_owner_repo", "owner", "repo"),
    )
