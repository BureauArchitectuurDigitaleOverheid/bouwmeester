"""Edge model - directed typed relation between two corpus nodes."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.edge_type import EdgeType


class Edge(Base):
    __tablename__ = "edge"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "edge_type_id",
            name="uq_edge_from_to_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type_id: Mapped[str] = mapped_column(
        ForeignKey("edge_type.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    weight: Mapped[float] = mapped_column(default=1.0, server_default="1.0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    from_node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        foreign_keys=[from_node_id],
        back_populates="edges_from",
    )
    to_node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        foreign_keys=[to_node_id],
        back_populates="edges_to",
    )
    edge_type: Mapped["EdgeType"] = relationship("EdgeType")
