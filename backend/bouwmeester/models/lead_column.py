"""LeadColumn model - per-initiatief funnel-kolommen."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.initiatief import Initiatief


class LeadColumn(Base):
    __tablename__ = "lead_column"
    __table_args__ = (
        UniqueConstraint(
            "initiatief_id", "slug", name="uq_lead_column_initiatief_slug"
        ),
        UniqueConstraint(
            "initiatief_id", "name", name="uq_lead_column_initiatief_name"
        ),
        Index("ix_lead_column_initiatief_sort", "initiatief_id", "sort_order"),
    )

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
    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # One of the nldd-tag color names in schema.lead_column.LEAD_COLUMN_COLORS
    # (five semantic roles plus the Rijkshuisstijl hue set), e.g. "lintblauw"
    # or "success". Never a CSS class or a hex value: the frontend passes this
    # straight to nldd-tag's `color`, which ignores anything outside its own
    # set. Pydantic validates it on every write via LeadColumnCreate and
    # LeadColumnUpdate; there is no CHECK constraint behind it.
    color: Mapped[str] = mapped_column(
        nullable=False,
        server_default="neutral",
    )
    is_active_stage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_public_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    initiatief: Mapped["Initiatief"] = relationship(
        "Initiatief", back_populates="lead_columns"
    )
