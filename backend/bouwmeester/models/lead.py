"""Lead model - sales/intake funnel lead."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.externe_organisatie import ExterneOrganisatie
    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.models.lead_activity import LeadActivity
    from bouwmeester.models.lead_attachment import LeadAttachment
    from bouwmeester.models.lead_contact import LeadContact
    from bouwmeester.models.lead_node import LeadNode
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.person import Person
    from bouwmeester.models.tag import LeadTag


class Lead(Base):
    __tablename__ = "lead"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(nullable=True)
    externe_organisatie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("externe_organisatie.id", ondelete="SET NULL"),
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(
        default="verkennen",
        server_default="verkennen",
        comment="verkennen|eerste_gesprek|interne_check|follow_up|in_the_pocket|koelkast",
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    brought_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action_date: Mapped[date | None] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    raw_intake_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Legacy: kept nullable during migration, will be dropped later
    organisatie_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    initiatief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("initiatief.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    assignee: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[assignee_id]
    )
    brought_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[brought_by_id]
    )
    externe_organisatie: Mapped[Optional["ExterneOrganisatie"]] = relationship(
        "ExterneOrganisatie"
    )
    organisatie_eenheid: Mapped[Optional["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid"
    )
    initiatief: Mapped[Optional["Initiatief"]] = relationship(
        "Initiatief", back_populates="leads"
    )
    activities: Mapped[list["LeadActivity"]] = relationship(
        "LeadActivity",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list["LeadAttachment"]] = relationship(
        "LeadAttachment",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[list["LeadContact"]] = relationship(
        "LeadContact",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    linked_nodes: Mapped[list["LeadNode"]] = relationship(
        "LeadNode",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    lead_tags: Mapped[list["LeadTag"]] = relationship(
        "LeadTag",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
