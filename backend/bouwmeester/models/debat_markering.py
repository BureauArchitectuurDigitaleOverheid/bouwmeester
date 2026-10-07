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
    Boolean,
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

# What was marked. The vraag, the motie and the toezegging are built; the
# others are named here so the column, the status line and the thread do
# not have to change shape when they arrive. A request for a letter is not
# a kind that is stored: it is a question that asks for something on paper,
# and `vraagt_om` on the row of that question says so. The name stays for
# the gold sets, which label it apart.
SOORT_VRAAG = "vraag"
SOORT_TOEZEGGING = "toezegging"
SOORT_FEITELIJKE_CLAIM = "feitelijke_claim"
SOORT_MOTIE = "motie"
SOORT_VERZOEK_OM_BRIEF = "verzoek_om_brief"

# Where a markering stands. A markering starts as `open`; the people who
# follow the debate set the others with a reaction on its reply (see
# `debat_vraag_reacties`). `antwoord_klaar` is not set by anything yet.
#
# The names are those of a question, and a motie uses the same ones: it is
# not answered but gets an oordeel, so `beantwoord` is shown as "oordeel
# gegeven", `vervalt` as "hoeft geen oordeel" and `verworpen` as "geen
# motie". Which oordeel it was is not stored: reading that from the debate
# is not built, and it will need a column of its own. A toezegging is kept
# and not answered: `beantwoord` is shown as "nagekomen", `toegewezen` as
# "wordt opgepakt", `vervalt` as "hoeft niet", `verworpen` as "geen
# toezegging".
STATUS_OPEN = "open"
# Someone said they are on it.
STATUS_TOEGEWEZEN = "toegewezen"
STATUS_ANTWOORD_KLAAR = "antwoord_klaar"
STATUS_BEANTWOORD = "beantwoord"
# A real question that needs no answer from us: rhetorical, answered
# elsewhere, or not ours. No longer open, still a question.
STATUS_VERVALT = "vervalt"
# Not a question at all: the marking was wrong. The row is kept, with its
# quote and summary, because that is what the prompt is improved with.
STATUS_VERWORPEN = "verworpen"

# How a later turn relates to a markering. `herhaling` is the same question
# asked again, or the same toezegging said again. `antwoord` is written on
# a question when a toezegging of the bewindspersoon answers it; it does
# not change where the question stands, people do that with a reaction.
# `aanvulling` is not written by anything yet. `bevestiging` is written on a
# toezegging when the chairman reads it out in the list at the end of the
# debate: its reply then says so. At most one per toezegging.
VERMELDING_HERHALING = "herhaling"
VERMELDING_AANVULLING = "aanvulling"
VERMELDING_ANTWOORD = "antwoord"
VERMELDING_BEVESTIGING = "bevestiging"

# What `beurt_sleutel` begins with for a toezegging that was not found in a
# turn of the bewindspersoon but taken from the list the chairman reads at
# the end. Its row carries the chairman as speaker, and the words of the
# chairman as its quote; its reply says where it came from. The key, and
# not a column of its own: it is what makes the list a turn that is read
# once, and nothing else asks for it.
SLEUTEL_SLOTLIJST = "slotlijst:"


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
        # Every reaction in every channel of the bot asks "is this the
        # reply of a markering", so that has to be one lookup.
        Index("ix_debat_markering_thread_post_id", "thread_post_id"),
        # The few rows whose reactions changed and are not worked in yet.
        Index(
            "ix_debat_markering_reacties_gewijzigd_at",
            "reacties_gewijzigd_at",
            postgresql_where=text("reacties_gewijzigd_at IS NOT NULL"),
        ),
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

    # Since when the status is what it is, and whose reaction made it so.
    # All NULL for a markering nobody reacted to; after a reaction was
    # taken away again only `status_at` is set, to when that was noticed.
    status_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_door_mattermost_user_id: Mapped[str | None] = mapped_column(
        String(26), nullable=True
    )
    # The person behind that Mattermost user, if the account is linked.
    status_door_person_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        # Removing a person looks up every row that points at them.
        index=True,
    )
    # When a reaction was last put on or taken off the reply. NULL means
    # the status, the reply and the status line all show the reactions as
    # they are. The websocket only sets this; the round of the questions
    # reads the reactions and writes what follows from them.
    reacties_gewijzigd_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    # By when, in the words of whoever spoke. For a toezegging: when the
    # bewindspersoon promised it by ("voor het kerstreces"). For a question
    # that asks for something on paper (`vraagt_om`): when the member wants
    # it by ("voor de begrotingsbehandeling"). One column for both, because
    # it is one thing seen from two sides: the moment that was said with
    # this markering. Text, because that is what was said; working out a
    # date from it is for whoever registers it. NULL when no moment was
    # named, for a question that asks for nothing on paper, and for a motie.
    termijn: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For a question: what it asks for on paper, when it does ("een brief",
    # "een overzicht"). One of `debat_vraag_brief.PRODUCTS`: our word for
    # the word the member used, picked by a rule on the quote, never a
    # word of a model. NULL for a question that can be answered on the
    # spot, and for every other kind.
    vraagt_om: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # For a toezegging: the number of the question in this debate it
    # answers, if the model named one that was open. The number and not the
    # row: it is what the reply shows ("bij vraag 12"), and numbers of a
    # debate never change. The question carries a vermelding of the kind
    # `antwoord` for the same link, seen from its side.
    bij_volgnummer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Whether its reply carries the note that goes under the first reply of
    # a thread. Kept, because the reply is written again when its status
    # changes, and must then say what it said.
    met_noot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
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
