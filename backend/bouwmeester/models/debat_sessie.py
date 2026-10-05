"""The channel that was set up for one debate.

A row is the answer to "is there already a channel for this debate?", and
later the place where the listening worker finds what to listen to.

The key is the activiteit from the TK API, not a Debat Direct debate. A
convocatie arrives days to weeks ahead (median 20.5 days, measured over 80
convocaties), and Debat Direct does not know the debate until the day
itself. The activiteit already exists.

Own table, not a third scope on `mattermost_channel_link`: a linked channel
is read for leads and notes, and a debate channel must not be.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class DebatSessie(Base):
    """One debate, in one team, with the channel that belongs to it."""

    __tablename__ = "debat_sessie"
    __table_args__ = (
        # One channel per debate per team. This constraint is also the
        # lock: the row is inserted before the channel is created, so two
        # people pressing start at the same moment cannot both get one.
        UniqueConstraint("activiteit_id", "team_id", name="uq_debat_sessie_activiteit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # `Id` of the Activiteit in the TK OData API.
    activiteit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # `Nummer`, such as 2026A06386: what a human recognises and what the
    # page on tweedekamer.nl is keyed on.
    activiteit_nummer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    onderwerp: Mapped[str] = mapped_column(Text, nullable=False)
    # As read when the channel was set up. 10% of activiteiten is cancelled
    # or moved (25 of 250 measured), so whoever uses this on the day itself
    # reads it again.
    aanvang: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    team_id: Mapped[str] = mapped_column(String(26), nullable=False)
    # NULL while the channel is being created: the row is the claim, the
    # channel follows. A claim that stays NULL is a start that broke off
    # halfway, and may be taken over.
    channel_id: Mapped[str | None] = mapped_column(
        String(26), nullable=True, unique=True
    )
    channel_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The pinned message with the agenda, so it can be updated in place
    # when the agenda changes.
    stukken_post_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    # The convocatie under which start was pressed.
    parlementair_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parlementair_item.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_by_mattermost_user_id: Mapped[str | None] = mapped_column(
        String(26), nullable=True
    )

    # The Debat Direct debates that are this activiteit, found on the day
    # itself. A list, because Debat Direct cuts a plenary debate in two
    # around a break against one activiteit.
    debat_direct_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Where the timeline stands: NULL (not yet found on Debat Direct),
    # gekoppeld, loopt, afgelopen or afgelast.
    tijdlijn_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # When the activiteit and the Debat Direct agenda were last read, so
    # that is not done on every tick.
    tijdlijn_gecontroleerd_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


TIJDLIJN_GEKOPPELD = "gekoppeld"
TIJDLIJN_LOOPT = "loopt"
TIJDLIJN_AFGELOPEN = "afgelopen"
TIJDLIJN_AFGELAST = "afgelast"


class DebatSpreekbeurt(Base):
    """One event of a debate that the timeline has dealt with.

    The table is the memory of what was seen: an event that is in here is
    never posted again, also after a restart. `post_id` is the message it
    became, or NULL for an event that was deliberately not posted (the
    chairman giving the floor, or everything that happened before the
    timeline joined a running debate).

    Named after the spreekbeurt because that is what a row will grow into:
    the transcript is added to the same message later.
    """

    __tablename__ = "debat_spreekbeurt"
    __table_args__ = (
        UniqueConstraint(
            "sessie_id",
            "debat_direct_id",
            "event_type",
            "event_start",
            "object_id",
            name="uq_debat_spreekbeurt_event",
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
        index=True,
    )
    debat_direct_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # The politician for a speaker event, the debate itself for a start or
    # an end. Empty string, not NULL, so the unique key holds.
    object_id: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=""
    )
    post_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
