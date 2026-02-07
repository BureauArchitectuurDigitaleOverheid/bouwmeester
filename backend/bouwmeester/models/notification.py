"""Notification model - user notifications for events in the corpus."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.person import Person
    from bouwmeester.models.task import Task


class Notification(Base):
    __tablename__ = "notification"

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
    type: Mapped[str] = mapped_column(
        nullable=False,
        comment="task_assigned|task_overdue|node_updated|edge_created|coverage_needed",
    )
    title: Mapped[str] = mapped_column(nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(default=False, server_default="false")
    related_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    person: Mapped["Person"] = relationship("Person")
    related_node: Mapped[Optional["CorpusNode"]] = relationship("CorpusNode")
    related_task: Mapped[Optional["Task"]] = relationship("Task")
