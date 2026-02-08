"""Task model - always linked to a corpus_node."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.motie_import import MotieImport
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.person import Person


class Task(Base):
    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    organisatie_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    motie_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("motie_import.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        default="open",
        server_default="open",
        comment="open|in_progress|done|cancelled",
    )
    priority: Mapped[str] = mapped_column(
        default="normaal",
        server_default="normaal",
        comment="laag|normaal|hoog|kritiek",
    )
    deadline: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        onupdate=func.now(), nullable=True
    )

    # Relationships
    node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        back_populates="tasks",
    )
    assignee: Mapped[Optional["Person"]] = relationship("Person")
    organisatie_eenheid: Mapped[Optional["OrganisatieEenheid"]] = relationship(
        "OrganisatieEenheid",
    )
    parent: Mapped[Optional["Task"]] = relationship(
        "Task",
        remote_side="Task.id",
        back_populates="subtasks",
    )
    subtasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    motie_import: Mapped[Optional["MotieImport"]] = relationship("MotieImport")
