"""CorpusNode model - the universal node in the policy corpus graph."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.edge import Edge
    from bouwmeester.models.node_stakeholder import NodeStakeholder
    from bouwmeester.models.node_status import CorpusNodeStatus
    from bouwmeester.models.node_title import CorpusNodeTitle
    from bouwmeester.models.tag import NodeTag
    from bouwmeester.models.task import Task


class CorpusNode(Base):
    __tablename__ = "corpus_node"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    node_type: Mapped[str] = mapped_column(
        comment="dossier|doel|instrument|beleidskader|maatregel|politieke_input|probleem|effect|beleidsoptie|bron",
        index=True,
    )
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(default="actief", server_default="actief")
    geldig_van: Mapped[date] = mapped_column(
        server_default=text("CURRENT_DATE"), default=date.today
    )
    geldig_tot: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    edges_from: Mapped[list["Edge"]] = relationship(
        "Edge",
        foreign_keys="Edge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )
    edges_to: Mapped[list["Edge"]] = relationship(
        "Edge",
        foreign_keys="Edge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    stakeholders: Mapped[list["NodeStakeholder"]] = relationship(
        "NodeStakeholder",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    node_tags: Mapped[list["NodeTag"]] = relationship(
        "NodeTag",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    title_records: Mapped[list["CorpusNodeTitle"]] = relationship(
        "CorpusNodeTitle",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    status_records: Mapped[list["CorpusNodeStatus"]] = relationship(
        "CorpusNodeStatus",
        back_populates="node",
        cascade="all, delete-orphan",
    )
