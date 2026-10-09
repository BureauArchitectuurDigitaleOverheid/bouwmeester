"""A debate that was announced in the channels of an initiatief.

Next to `debat_sessie`, not in it: a sessie is a channel of its own for one
debate, where the bot listens along. An aankondiging is one message in a
channel that already exists, for people who want to know the debate is
coming and do not need a channel for it.

The key is the activiteit from the TK API, for the same reason as on a
sessie: it exists weeks before the debate, and Debat Direct does not know
the debate until the day itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base

# Announced, and still to be reminded of on the day itself.
STAND_AANGEKONDIGD = "aangekondigd"
# The reminder of the day itself went out.
STAND_HERINNERD = "herinnerd"
# Cancelled, moved without a new date, or gone from the agenda. The
# channels were told.
STAND_AFGELAST = "afgelast"
# The day went by without a reminder (the worker was down, or Mattermost
# was). Nothing is posted about a debate that is over.
STAND_VOORBIJ = "voorbij"


class DebatAankondiging(Base):
    """One debate, announced for one initiatief."""

    __tablename__ = "debat_aankondiging"
    __table_args__ = (
        UniqueConstraint(
            "initiatief_id", "activiteit_id", name="uq_debat_aankondiging_activiteit"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    initiatief_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("initiatief.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # `Id` of the Activiteit in the TK OData API. Of the meeting as it
    # stands: when the Kamer moves a meeting the new date is a new
    # activiteit, and the row follows it there on the day it is read again.
    activiteit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    activiteit_nummer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    soort: Mapped[str | None] = mapped_column(String(128), nullable=True)
    onderwerp: Mapped[str] = mapped_column(Text, nullable=False)
    commissie: Mapped[str | None] = mapped_column(Text, nullable=True)
    # As read when the debate was announced. 10% of activiteiten is
    # cancelled or moved (25 of 250 measured), so the reminder reads them
    # again.
    aanvang: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    einde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The one channel the reminder goes to, for a meeting that was put on
    # the list with the reaction under an alert: whoever pressed there
    # asked for that channel, not for every channel of the initiatief.
    # NULL is all of them, which is what announcing on the tab means.
    channel_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    stand: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=STAND_AANGEKONDIGD,
        server_default=STAND_AANGEKONDIGD,
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
