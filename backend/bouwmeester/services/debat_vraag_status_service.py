"""Work the reactions on the reply of a question into where it stands.

Someone puts a reaction on the reply of a question, or takes one away. The
websocket does one thing with that: it marks the markering as "reactions
changed" (`reacties_gewijzigd_at`). This service, called at the start of
every round of the questions, does the rest for each marked markering:

1. It asks Mattermost which reactions are on the reply now, and derives the
   status from that list (`stand_uit_reacties`). Not from the event: a
   burst of clicks is then one read and at most two writes, a click that
   was missed while the websocket was away is made up for by the next one,
   and "is someone else's reaction still there" needs no bookkeeping.
2. It stores the status, with whose reaction decided it and since when.
3. It rewrites the reply, so its first line says where the question stands.
4. It rewrites the status block under the message of the turn.
5. Only then it takes the mark away, and only if no reaction came in
   meanwhile. Anything that failed is tried again the next round, for an
   hour.

No row is locked while Mattermost is asked something: the websocket sets
its mark on the same row, and must never wait for an HTTP call of this
round. Every step can be done twice without harm instead.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    SOORT_VRAAG,
    STATUS_TOEGEWEZEN,
    STATUS_VERWORPEN,
    DebatMarkering,
)
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.services.debat_vraag_reacties import (
    STATUS_PER_REACTIE,
    Stand,
    stand_uit_reacties,
)
from bouwmeester.services.debat_vraag_service import (
    format_thread,
    is_bevestigd,
    komt_uit_slotlijst,
    later_op_papier,
    schrijf_statusregel,
    toezeggingen_bij,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    PostNotFoundError,
)

logger = logging.getLogger(__name__)

# How many markeringen one round works in. A round comes every quarter of a
# minute; what is left waits for the next one.
MAX_PER_RONDE = 25
# How long a markering whose reactions could not be worked in is tried
# again. Past this it is left as it is until someone reacts once more: a
# reply Mattermost keeps refusing must not be asked for every round for
# ever.
GEEF_OP_NA = timedelta(hours=1)


@dataclass
class StatusRonde:
    # Markeringen that are fully up to date again.
    bijgewerkt: int = 0
    # Of those, the ones whose status changed.
    gewijzigd: int = 0
    # Markeringen left for the next round.
    mislukt: int = 0


def is_status_reactie(emoji_name: str) -> bool:
    """Whether this emoji says something about a question at all."""
    return emoji_name in STATUS_PER_REACTIE


async def markeer_reactie(session: AsyncSession, post_id: str) -> bool:
    """Note that the reactions on a post changed, if it is a question's reply.

    For the websocket: one statement on an index, no Mattermost. Returns
    whether the post is the reply of a markering. The caller commits.
    """
    result = await session.execute(
        update(DebatMarkering)
        .where(DebatMarkering.thread_post_id == post_id)
        .values(reacties_gewijzigd_at=datetime.now(UTC))
        .returning(DebatMarkering.id)
    )
    return result.first() is not None


async def verworpen_markeringen(
    session: AsyncSession,
    *,
    sessie_id: uuid.UUID | None = None,
    limit: int = 200,
    soort: str = SOORT_VRAAG,
) -> list[DebatMarkering]:
    """What was marked and rejected by a reader, newest first.

    This is what a prompt is improved with: what the model took for a
    question to the bewindspersoon, or with `soort` for a toezegging or a
    motie, with the quote, its summary, and who said so when.
    """
    stmt = (
        select(DebatMarkering)
        .where(
            DebatMarkering.soort == soort,
            DebatMarkering.status == STATUS_VERWORPEN,
        )
        .order_by(DebatMarkering.status_at.desc().nulls_last(), DebatMarkering.id)
        .limit(limit)
    )
    if sessie_id is not None:
        stmt = stmt.where(DebatMarkering.sessie_id == sessie_id)
    return list((await session.execute(stmt)).scalars().all())


class DebatVraagStatusService:
    def __init__(self, session: AsyncSession, mattermost: MattermostService) -> None:
        self.session = session
        self.mattermost = mattermost

    async def werk_bij(self, now: datetime | None = None) -> StatusRonde:
        """Work in the reactions of every markering that is marked for it.

        Costs one query on a small index when nothing is marked, which is
        nearly always.
        """
        now = now or datetime.now(UTC)
        ronde = StatusRonde()
        rows = (
            await self.session.execute(
                select(DebatMarkering.id, DebatMarkering.reacties_gewijzigd_at)
                .where(
                    DebatMarkering.reacties_gewijzigd_at.is_not(None),
                    DebatMarkering.reacties_gewijzigd_at > now - GEEF_OP_NA,
                    DebatMarkering.thread_post_id.is_not(None),
                )
                # Newest first: who clicked just now is waiting, and rows
                # that keep failing must not hold up the ones after them.
                .order_by(DebatMarkering.reacties_gewijzigd_at.desc())
                .limit(MAX_PER_RONDE)
            )
        ).all()
        # Nothing is held between rounds or while Mattermost is asked.
        await self.session.commit()
        if not rows:
            return ronde
        if not await self.mattermost.is_enabled():
            return ronde
        # Without knowing who the bot is, its own reaction under every
        # reply would count as "beantwoord". Then nothing is derived, and
        # the marks stay for a round in which it is known.
        bot_user_id = await self.mattermost.get_bot_user_id()
        if not bot_user_id:
            logger.warning("Bot onbekend; reacties op vragen wachten")
            ronde.mislukt = len(rows)
            return ronde

        for markering_id, gezien in rows:
            try:
                klaar, gewijzigd = await self._werk_een_bij(
                    markering_id, gezien, bot_user_id, now
                )
            except Exception:
                # One markering that breaks must not stop the others.
                await self.session.rollback()
                logger.exception("Reacties op markering %s niet verwerkt", markering_id)
                klaar, gewijzigd = False, False
            ronde.gewijzigd += int(gewijzigd)
            if klaar:
                ronde.bijgewerkt += 1
            else:
                ronde.mislukt += 1
        return ronde

    async def _werk_een_bij(
        self,
        markering_id: uuid.UUID,
        gezien: datetime,
        bot_user_id: str,
        now: datetime,
    ) -> tuple[bool, bool]:
        """One markering, as (everything written, status changed)."""
        markering = (
            await self.session.execute(
                select(DebatMarkering)
                .where(DebatMarkering.id == markering_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if markering is None or not markering.thread_post_id:
            await self.session.commit()
            return True, False
        thread_post_id = markering.thread_post_id
        beurt_post_id = markering.beurt_post_id

        try:
            reacties = await self.mattermost.get_post_reactions(thread_post_id)
        except PostNotFoundError:
            # The reply was deleted. There is nothing to react to and
            # nothing to rewrite; the status stays what it was.
            logger.info("Thread %s is weg; reacties vervallen", thread_post_id)
            await self._klaar(markering_id, gezien)
            return True, False
        if reacties is None:
            await self.session.commit()
            return False, False

        stand = stand_uit_reacties(reacties, bot_user_id)
        gewijzigd = (
            stand.status != markering.status
            or stand.mattermost_user_id != markering.status_door_mattermost_user_id
        )
        gebruiker = await self._gebruiker(stand.mattermost_user_id)
        later = (
            await later_op_papier(self.session, markering_id)
            if markering.soort == SOORT_VRAAG and markering.vraagt_om is None
            else None
        )
        # What the reply is made from, read before the commit expires it.
        tekst = format_thread(
            markering.soort,
            volgnummer=markering.volgnummer,
            gericht_aan=markering.gericht_aan,
            citaat=markering.citaat,
            samenvatting=markering.samenvatting,
            stuk=markering.stuk,
            moment=markering.moment,
            moment_url=markering.moment_url,
            vraag_moment=markering.vraag_moment,
            first_in_thread=markering.met_noot,
            status=stand.status,
            door=await self._naam(stand, gebruiker),
            termijn=markering.termijn,
            bij_volgnummer=markering.bij_volgnummer,
            bevestigd=await is_bevestigd(self.session, markering_id),
            uit_lijst=komt_uit_slotlijst(markering.beurt_sleutel),
            vraagt_om=markering.vraagt_om,
            toegezegd=(
                await toezeggingen_bij(
                    self.session, markering.sessie_id, markering.volgnummer
                )
                if markering.soort == SOORT_VRAAG
                else ()
            ),
            later_om=later.product if later else None,
            later_termijn=later.moment if later else None,
        )
        # A toezegging that is rejected, or taken back in, changes what the
        # reply of its question says: that one is written again as well.
        vraag_bij = (
            markering.bij_volgnummer
            if markering.soort == SOORT_TOEZEGGING
            and STATUS_VERWORPEN in (stand.status, markering.status)
            and stand.status != markering.status
            else None
        )
        sessie_id = markering.sessie_id
        if gewijzigd:
            await self.session.execute(
                update(DebatMarkering)
                .where(DebatMarkering.id == markering_id)
                .values(
                    status=stand.status,
                    status_at=stand.sinds or now,
                    status_door_mattermost_user_id=stand.mattermost_user_id,
                    status_door_person_id=gebruiker[0] if gebruiker else None,
                    # The status block under the turn counts per status.
                    statusregel_at=None,
                )
            )
            logger.info(
                "Markering %s is nu %s (reactie van %s)",
                markering_id,
                stand.status,
                stand.mattermost_user_id or "niemand",
            )
        if vraag_bij is not None:
            await self.session.execute(
                update(DebatMarkering)
                .where(
                    DebatMarkering.sessie_id == sessie_id,
                    DebatMarkering.volgnummer == vraag_bij,
                    DebatMarkering.soort == SOORT_VRAAG,
                )
                .values(reacties_gewijzigd_at=now)
            )
        # Committed before the channel is touched: what the channel shows
        # is derived from the row, by this round or by a later one.
        await self.session.commit()

        klaar = await self._schrijf_thread(thread_post_id, tekst)
        if beurt_post_id:
            geschreven = await schrijf_statusregel(
                self.session, self.mattermost, beurt_post_id
            )
            if geschreven is None:
                # A message of the transcription: the row says its count
                # is out of date, and the transcription writes it.
                pass
            elif geschreven:
                await self.session.execute(
                    update(DebatMarkering)
                    .where(
                        DebatMarkering.beurt_post_id == beurt_post_id,
                        DebatMarkering.thread_post_id.is_not(None),
                    )
                    .values(statusregel_at=datetime.now(UTC))
                )
                await self.session.commit()
            else:
                klaar = False
        if klaar:
            await self._klaar(markering_id, gezien)
        return klaar, gewijzigd

    async def _klaar(self, markering_id: uuid.UUID, gezien: datetime) -> None:
        """Take the mark away, unless a reaction came in since it was read."""
        await self.session.execute(
            update(DebatMarkering)
            .where(
                DebatMarkering.id == markering_id,
                DebatMarkering.reacties_gewijzigd_at == gezien,
            )
            .values(reacties_gewijzigd_at=None)
        )
        await self.session.commit()

    async def _gebruiker(self, mattermost_user_id: str | None) -> tuple | None:
        """(person id, username) of a linked Mattermost account, or ``None``."""
        if not mattermost_user_id:
            return None
        row = (
            await self.session.execute(
                select(
                    MattermostUser.person_id, MattermostUser.mattermost_username
                ).where(MattermostUser.mattermost_user_id == mattermost_user_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def _naam(self, stand: Stand, gebruiker: tuple | None) -> str | None:
        """The username to show for who picked a question up, if any.

        Only asked for when it is shown. From the link with a person when
        there is one, which saves a call; otherwise from Mattermost.
        """
        if stand.status != STATUS_TOEGEWEZEN or not stand.mattermost_user_id:
            return None
        if gebruiker and gebruiker[1]:
            return gebruiker[1]
        try:
            naam = await self.mattermost.get_username(stand.mattermost_user_id)
        except Exception:
            logger.warning("Naam van %s niet te lezen", stand.mattermost_user_id)
            return None
        # `get_username` gives the id back when the lookup fails, and an
        # id is not a name.
        return naam if naam and naam != stand.mattermost_user_id else None

    async def _schrijf_thread(self, post_id: str, tekst: str) -> bool:
        """Make the reply say where the question stands.

        ``True`` when it does, or never will because the reply is gone.
        """
        try:
            post = await self.mattermost.get_post(post_id)
        except PostNotFoundError:
            return True
        except Exception:
            logger.exception("Thread %s niet te lezen", post_id)
            return False
        if not post:
            return False
        if str(post.get("message") or "") == tekst:
            return True
        try:
            # The props go back as they came: an update without them is an
            # update that clears them.
            return bool(
                await self.mattermost.update_post(
                    post_id, tekst, post.get("props") or None
                )
            )
        except Exception:
            logger.exception("Thread %s niet bijgewerkt", post_id)
            return False
