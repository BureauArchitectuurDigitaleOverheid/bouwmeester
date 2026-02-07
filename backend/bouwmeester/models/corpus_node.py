"""CorpusNode model - the universal node in the policy corpus graph."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.edge import Edge
    from bouwmeester.models.node_stakeholder import NodeStakeholder
    from bouwmeester.models.task import Task


class CorpusNode(Base):
    __tablename__ = "corpus_node"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    node_type: Mapped[str] = mapped_column(
        comment="dossier|doel|instrument|beleidskader|maatregel|politieke_input",
    )
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(default="actief", server_default="actief")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        onupdate=func.now(), nullable=True
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
