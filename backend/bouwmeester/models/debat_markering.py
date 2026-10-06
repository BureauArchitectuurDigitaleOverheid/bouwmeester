"""What was marked in a debate: a question to the bewindspersoon, and later
a toezegging, a claim, a motie or a request for a letter.

A markering is a state, not an event. A question is asked, asked again
after an unsatisfying answer, added to after an interruption, answered. The
row is the question; every later turn at speaking that comes back to it is
a `DebatMarkeringVermelding` on that row. That is what keeps the same
question from getting three threads.

The table is also the memory of the model. Each turn is judged by a fresh
call that gets the open markeringen of the speaker as a short list; nothing
else carries over from one turn to the next.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base

# What was marked. Only the vraag is built; the others are named here so
# the column, the status line and the thread do not have to change shape
# when they arrive.
SOORT_VRAAG = "vraag"
SOORT_TOEZEGGING = "toezegging"
SOORT_FEITELIJKE_CLAIM = "feitelijke_claim"
SOORT_MOTIE = "motie"
SOORT_VERZOEK_OM_BRIEF = "verzoek_om_brief"

# Where a markering stands. Only `open` is set today.
STATUS_OPEN = "open"
STATUS_TOEGEWEZEN = "toegewezen"
STATUS_ANTWOORD_KLAAR = "antwoord_klaar"
STATUS_BEANTWOORD = "beantwoord"
STATUS_VERWORPEN = "verworpen"

# How a later turn relates to a markering. Only `herhaling` is written
# today: the same question, asked again.
VERMELDING_HERHALING = "herhaling"
VERMELDING_AANVULLING = "aanvulling"
VERMELDING_ANTWOORD = "antwoord"


class DebatMarkering(Base):
    """One thing that was marked in a debate, and where it stands."""

    __tablename__ = "debat_markering"
    __table_args__ = (
        # The number the model sees in its list of open questions, and
        # answers with when a turn belongs to one of them. Per debate, so
        # the numbers stay small.
        UniqueConstraint(
            "sessie_id", "volgnummer", name="uq_debat_markering_volgnummer"
        ),
        Index("ix_debat_markering_beurt_post_id", "beurt_post_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    sessie_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("debat_sessie.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The turn at speaking it was found in, if the caller knew the row.
    spreekbeurt_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("debat_spreekbeurt.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # What identifies the turn, so that judging the same turn twice does
    # not mark its questions twice. See `Beurt.sleutel`.
    beurt_sleutel: Mapped[str] = mapped_column(String(255), nullable=False)
    volgnummer: Mapped[int] = mapped_column(Integer, nullable=False)

    soort: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=SOORT_VRAAG
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=STATUS_OPEN
    )

    channel_id: Mapped[str] = mapped_column(String(26), nullable=False)
    # The message of the turn: the thread hangs under it and the status
    # line is appended to it. NULL when the turn had no message.
    beurt_post_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    # The reply that is the thread. NULL means: not in the channel. Only a
    # markering with a thread counts in the status line.
    thread_post_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    # How often posting the thread failed. Past a few attempts it is left
    # alone: a turn whose message was deleted never takes a reply.
    post_pogingen: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # When the status line on the message of the turn last showed this
    # markering as it is now. NULL means it still has to be written, also
    # after a change of status.
    statusregel_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    spreker: Mapped[str] = mapped_column(Text, nullable=False)
    fractie: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Who is asked, in the words of the model ("de minister").
    gericht_aan: Mapped[str] = mapped_column(String(255), nullable=False)
    # Literal, from the automatic transcript, mistakes included.
    citaat: Mapped[str] = mapped_column(Text, nullable=False)
    samenvatting: Mapped[str] = mapped_column(Text, nullable=False)
    # Title of the agenda document it is about, if the model could tell.
    stuk: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Start of the turn, and the link to that moment in the broadcast.
    moment: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    moment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When in the turn the question was asked: the moment of the subtitle
    # line its quote begins in. NULL when that is not known, as for every
    # row from before this column; the thread then shows the start of the
    # turn. Kept, so a thread that is posted again says the same.
    vraag_moment: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DebatMarkeringVermelding(Base):
    """A later turn at speaking that comes back to a markering."""

    __tablename__ = "debat_markering_vermelding"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    markering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("debat_markering.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Also here, so "was this turn judged already" is one lookup per table.
    sessie_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("debat_sessie.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spreekbeurt_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("debat_spreekbeurt.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    beurt_sleutel: Mapped[str] = mapped_column(String(255), nullable=False)
    soort: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=VERMELDING_HERHALING
    )
    beurt_post_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    spreker: Mapped[str] = mapped_column(Text, nullable=False)
    fractie: Mapped[str | None] = mapped_column(String(64), nullable=True)
    citaat: Mapped[str] = mapped_column(Text, nullable=False)
    moment: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    moment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
