"""NodeStakeholder model - links people to corpus nodes."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.person import Person


class NodeStakeholder(Base):
    __tablename__ = "node_stakeholder"

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
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
    )
    rol: Mapped[str] = mapped_column(
        comment="eigenaar|betrokken|adviseur",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        back_populates="stakeholders",
    )
    person: Mapped["Person"] = relationship("Person")
