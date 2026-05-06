"""InitiatiefUpdate model — explicit publication post on an initiatief."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.models.person import Person


class InitiatiefUpdatePost(Base):
    """Author-driven publication on an initiatief.

    Distinct from internal Lead activity: this is what shows on the public
    /c/:slug page when published. `published_at` IS NULL means draft.
    """

    __tablename__ = "initiatief_update"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    initiatief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("initiatief.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titel: Mapped[str] = mapped_column(nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
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

    initiatief: Mapped["Initiatief"] = relationship(
        "Initiatief", back_populates="updates"
    )
    published_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[published_by_id]
    )
