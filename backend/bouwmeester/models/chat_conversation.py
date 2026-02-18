"""Chat conversation model — persists multi-turn LLM conversations."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person


class ChatConversation(Base):
    __tablename__ = "chat_conversation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    messages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="OpenAI-format message history (system/user/assistant/tool)",
    )
    pending_actions: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Write actions awaiting user confirmation, keyed by action_id",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    person: Mapped["Person | None"] = relationship("Person", lazy="noload")
