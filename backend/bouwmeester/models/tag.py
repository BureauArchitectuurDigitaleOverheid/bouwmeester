from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tag.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    parent: Mapped[Tag | None] = relationship(
        "Tag", remote_side=[id], back_populates="children"
    )
    children: Mapped[list[Tag]] = relationship(
        "Tag", back_populates="parent", cascade="all, delete-orphan"
    )
    node_tags: Mapped[list[NodeTag]] = relationship(
        "NodeTag", back_populates="tag", cascade="all, delete-orphan"
    )


class NodeTag(Base):
    __tablename__ = "node_tag"
    __table_args__ = (UniqueConstraint("node_id", "tag_id", name="uq_node_tag"),)

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("corpus_node.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    node: Mapped[CorpusNode] = relationship("CorpusNode", back_populates="node_tags")
    tag: Mapped[Tag] = relationship("Tag", back_populates="node_tags")
