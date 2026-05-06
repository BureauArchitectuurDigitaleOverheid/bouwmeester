"""WorkerHeartbeat model — last-tick registry for background worker loops.

Each loop in ``bouwmeester.worker`` (parlementair, mattermost-link,
mattermost-websocket, opdracht-task, fcc-sync) writes a row here on every
iteration. The admin UI reads it to answer "is the worker alive?" without
forcing operators to dig through container logs.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    loop_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    last_tick_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
