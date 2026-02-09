"""PolitiekeInput model - extends CorpusNode for political inputs."""

import uuid
from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class PolitiekeInput(Base):
    __tablename__ = "politieke_input"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(
        comment="coalitieakkoord|motie|kamerbrief|toezegging|amendement|kamervraag|commissiedebat|schriftelijk_overleg|interpellatie",
        nullable=False,
    )
    referentie: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="e.g. kamerstuknummer",
    )
    datum: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        default="open",
        server_default="open",
        comment="open|in_behandeling|afgedaan",
    )
