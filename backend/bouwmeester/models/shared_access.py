"""SharedAccess model - cross-org data sharing grants.

Enables controlled sharing of corpus nodes or entire organisatie-eenheid
data with other eenheden, supporting cross-ministry collaboration.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class SharedAccess(Base):
    """Grants an eenheid access to a node or another eenheid's data."""

    __tablename__ = "shared_access"
    __table_args__ = (
        CheckConstraint(
            """
            (source_node_id IS NOT NULL AND source_eenheid_id IS NULL)
            OR
            (source_node_id IS NULL AND source_eenheid_id IS NOT NULL)
            """,
            name="ck_shared_access_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_level: Mapped[str] = mapped_column(
        nullable=False,
        comment="read|edit",
    )
    shared_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    geldig_van: Mapped[date] = mapped_column(Date, nullable=False)
    geldig_tot: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    source_node: Mapped["CorpusNode"] = relationship(  # noqa: F821
        "CorpusNode", foreign_keys=[source_node_id]
    )
    source_eenheid: Mapped["OrganisatieEenheid"] = relationship(  # noqa: F821
        "OrganisatieEenheid", foreign_keys=[source_eenheid_id]
    )
    target_eenheid: Mapped["OrganisatieEenheid"] = relationship(  # noqa: F821
        "OrganisatieEenheid", foreign_keys=[target_eenheid_id]
    )
    shared_by: Mapped["Person"] = relationship("Person")  # noqa: F821
