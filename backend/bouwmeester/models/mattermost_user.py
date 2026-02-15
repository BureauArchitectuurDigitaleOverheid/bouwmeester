"""Mattermost integration models - Person <-> Mattermost user mapping and link codes."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class MattermostUser(Base):
    """Maps a Bouwmeester Person to a Mattermost user account."""

    __tablename__ = "mattermost_user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    mattermost_user_id: Mapped[str] = mapped_column(
        String(26), unique=True, nullable=False
    )
    mattermost_username: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    person = relationship("Person", foreign_keys=[person_id])


class MattermostLinkCode(Base):
    """Short-lived code for linking a Bouwmeester account to Mattermost."""

    __tablename__ = "mattermost_link_code"

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
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    person = relationship("Person", foreign_keys=[person_id])
