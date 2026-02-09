"""ParlementairItem and SuggestedEdge models."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.edge import Edge
    from bouwmeester.models.edge_type import EdgeType
    from bouwmeester.models.person import Person


class ParlementairItem(Base):
    __tablename__ = "parlementair_item"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    type: Mapped[str] = mapped_column(
        nullable=False,
        server_default="motie",
        comment="motie|kamervraag|toezegging|amendement|commissiedebat|schriftelijk_overleg|interpellatie",
    )
    zaak_id: Mapped[str] = mapped_column(unique=True, nullable=False)
    zaak_nummer: Mapped[str] = mapped_column(nullable=False)
    titel: Mapped[str] = mapped_column(nullable=False)
    onderwerp: Mapped[str] = mapped_column(nullable=False)
    bron: Mapped[str] = mapped_column(
        nullable=False,
        comment="tweede_kamer|eerste_kamer",
    )
    datum: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending|imported|reviewed|rejected|out_of_scope",
    )
    corpus_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="SET NULL"),
        nullable=True,
    )
    indieners: Mapped[list | None] = mapped_column(JSON, nullable=True)
    document_tekst: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_samenvatting: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_api_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deadline: Mapped[date | None] = mapped_column(nullable=True)
    ministerie: Mapped[str | None] = mapped_column(nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    corpus_node: Mapped["CorpusNode | None"] = relationship("CorpusNode")
    reviewer: Mapped["Person | None"] = relationship(
        "Person", foreign_keys=[reviewed_by]
    )
    suggested_edges: Mapped[list["SuggestedEdge"]] = relationship(
        "SuggestedEdge",
        back_populates="parlementair_item",
        cascade="all, delete-orphan",
    )


class SuggestedEdge(Base):
    __tablename__ = "suggested_edge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    parlementair_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parlementair_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type_id: Mapped[str] = mapped_column(
        ForeignKey("edge_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending|approved|rejected",
    )
    edge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("edge.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    parlementair_item: Mapped["ParlementairItem"] = relationship(
        "ParlementairItem",
        back_populates="suggested_edges",
    )
    target_node: Mapped["CorpusNode"] = relationship(
        "CorpusNode", foreign_keys=[target_node_id]
    )
    edge_type: Mapped["EdgeType"] = relationship("EdgeType")
    edge: Mapped["Edge | None"] = relationship("Edge", foreign_keys=[edge_id])
    reviewer: Mapped["Person | None"] = relationship(
        "Person", foreign_keys=[reviewed_by]
    )
