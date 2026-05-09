"""Audit-log voor TOOI / RIO / organogram-sync.

Eén rij per change (add, rename, soft-delete, parent-move) zodat een foute
sync handmatig teruggedraaid kan worden via een script dat de log leest.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class TooiSyncLog(Base):
    __tablename__ = "tooi_sync_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Gegroepeerd per sync-run zodat je een hele run kan terugdraaien",
    )
    bron: Mapped[str] = mapped_column(
        nullable=False,
        comment="tooi | rio | ministeries_csv | organogram | tk_odata | kabinet | roo_leidinggevenden",  # noqa: E501
    )
    action: Mapped[str] = mapped_column(
        nullable=False,
        comment="add | rename | move | soft_delete | enrich | conflict",
    )
    tooi_uri: Mapped[str | None] = mapped_column(nullable=True, index=True)
    organisatie_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
