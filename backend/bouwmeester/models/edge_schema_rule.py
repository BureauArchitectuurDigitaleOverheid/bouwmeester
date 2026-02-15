"""EdgeSchemaRule model - defines which edge types are valid between node type pairs."""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class EdgeSchemaRule(Base):
    __tablename__ = "edge_schema_rule"
    __table_args__ = (
        UniqueConstraint(
            "from_node_type",
            "to_node_type",
            "edge_type_id",
            name="uq_edge_schema_rule",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    from_node_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    to_node_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    edge_type_id: Mapped[str] = mapped_column(
        ForeignKey("edge_type.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    edge_type = relationship("EdgeType")
