"""Verwerking van Mattermost-posts in gekoppelde kanalen.

Per binnenkomend ``posted``-event:
- skip bot-eigen berichten en niet-gekoppelde kanalen
- match auteur via bestaande ``mattermost_user``-link
- voor lead-scope met ``auto_note_enabled``: maak ``LeadActivity`` (note),
  haal doc-links op naar ``LeadAttachment(soort=link)`` en download
  native Mattermost file-uploads naar ``LeadAttachment(soort=file)``
- voor initiatief-scope met ``suggest_leads_enabled``: nog niet — komt in
  PR3 (hier alleen ``mattermost_post_link``-record)
- altijd: schrijf ``mattermost_post_link`` zodat de post niet opnieuw
  wordt verwerkt
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.core.storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_SIZE,
    ensure_bijlagen_dir,
    verify_content_type,
    write_upload_to_disk,
)
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    SCOPE_LEAD,
)
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.models.suggested_lead import (
    STATUS_PENDING,
    SuggestedLead,
)
from bouwmeester.repositories.mattermost_channel_link import (
    MattermostChannelLinkRepository,
)
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.services.mattermost_doc_link_extractor import (
    derive_attachment_label,
    extract_doc_links,
)
from bouwmeester.services.mattermost_mention_renderer import (
    render_mattermost_message_to_tiptap,
)
from bouwmeester.services.mention_helper import sync_and_notify_mentions

logger = logging.getLogger(__name__)


# Selectie van bestaande leads die meegaan in de LLM-prompt voor
# duplicate-detection. We nemen een unie van twee groepen, dedupliceren op
# id en cappen op MAX_LEADS_FOR_LLM:
#   1. de N nieuwste leads (vangt kwesties op die nog actief gespeeld worden)
#   2. de M leads waarvan titel/organisatie het meest lijkt op het
#      bericht via pg_trgm word_similarity (vangt oude leads waarvan de
#      naam expliciet genoemd wordt)
RECENT_LEADS_FOR_LLM = 25
SIMILAR_LEADS_FOR_LLM = 50
SIMILAR_LEAD_THRESHOLD = 0.3
MAX_LEADS_FOR_LLM = 60


# Fallback labels voor de 7 default-stages. De echte naam komt sinds
# per-initiatief lead_columns uit `lead_column.name`; deze map dient
# alleen als reservering wanneer de stage-slug niet (meer) als kolom
# bestaat (orphan-data, oude rij).
_DEFAULT_STAGE_LABELS = {
    "inbox": "Inbox",
    "verkennen": "Verkennen",
    "eerste_gesprek": "Eerste gesprek",
    "interne_check": "Interne check",
    "follow_up": "Follow-up",
    "in_the_pocket": "In the pocket",
    "koelkast": "Koelkast",
}


async def handle_dm_post(post: dict, *, bot_user_id: str | None = None) -> bool:
    """Verwerk een DM naar de bot: zoek link-code, koppel account.

    Draait in een eigen ``async_session`` zodat fouten in
    ``MattermostLinkPoller`` (bijvoorbeeld een ``IntegrityError`` op een
    race-conditie bij ``create_mapping``) niet doorslaan naar de session
    waar de caller in zit. Bij een crash is alleen deze ene DM verloren.

    Skip bot-eigen DMs als ``bot_user_id`` bekend is — anti
    feedback-loop voor bevestigingsreplies van de bot zelf. Bot-skips
    tellen als ``True`` (niets te doen, geslaagd).

    Returns ``True`` als de post zonder fouten is doorgelopen, ``False``
    als er een exception was. De caller gebruikt dit om te beslissen
    of de post in een dedup-cache mag — een mislukte DM moet bij
    recovery opnieuw kunnen worden geprobeerd.
    """
    if bot_user_id and post.get("user_id") == bot_user_id:
        return True

    from bouwmeester.services.mattermost_link_poller import MattermostLinkPoller
    from bouwmeester.services.mattermost_service import MattermostService

    async with async_session() as dm_session:
        mm_service = MattermostService(dm_session)
        try:
            poller = MattermostLinkPoller(dm_session, mm_service=mm_service)
            try:
                await poller.process_posts([post])
                await dm_session.commit()
                return True
            except Exception:
                await dm_session.rollback()
                logger.exception("DM-handling faalde voor post %s", post.get("id"))
                return False
        finally:
            await mm_service.close()


class MattermostIngestService:
    """Stateless verwerking — instantieer per session, gooi daarna weg."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        bot_user_id: str | None = None,
        mm_base_url: str | None = None,
    ):
        self.session = session
        self.bot_user_id = bot_user_id
        self.mm_base_url = mm_base_url.rstrip("/") if mm_base_url else None

    async def ingest_post(self, post: dict, *, channel_type: str | None = None) -> None:
        """Verwerk één Mattermost-post.

        De caller is verantwoordelijk voor commit/rollback van de session.

        ``channel_type`` komt uit de ``data.channel_type`` van het Mattermost
        ``posted``-event: ``"D"`` = 1-op-1 DM (link-code-pad),
        ``"G"`` = group-DM (genegeerd, consistent met legacy poller-gedrag),
        andere waardes (``"O"`` open, ``"P"`` private) of ``None`` vallen
        door naar de channel-link-flow.
        """
        post_id = post.get("id")
        channel_id = post.get("channel_id")
        if not post_id or not channel_id:
            return

        mm_user_id = post.get("user_id") or None
        root_id = post.get("root_id") or None

        # Skip bot's eigen posts (anti feedback-loop).
        if self.bot_user_id and mm_user_id == self.bot_user_id:
            return

        if channel_type == "D":
            await handle_dm_post(post, bot_user_id=self.bot_user_id)
            return
        if channel_type == "G":
            return

        link_repo = MattermostChannelLinkRepository(self.session)
        channel_link = await link_repo.get_by_channel_id(channel_id)
        if channel_link is None or channel_link.disabled_at is not None:
            return

        # Idempotency-check vóór insert vermijdt een IntegrityError-rollback
        # die in een ge-savepointe testtransactie de hele session sloopt.
        existing_stmt = select(MattermostPostLink.id).where(
            MattermostPostLink.post_id == post_id
        )
        if (await self.session.execute(existing_stmt)).scalar_one_or_none():
            return

        # Auteur-match via mattermost_user (alleen via expliciete koppeling).
        person_id: UUID | None = None
        if mm_user_id:
            mm_repo = MattermostUserRepository(self.session)
            mapping = await mm_repo.get_by_mattermost_user_id(mm_user_id)
            if mapping is not None:
                person_id = mapping.person_id

        # Claim de post NU, vóór de LLM-call en eventuele bot-reply naar
        # Mattermost. Twee overlappende workers (bv. tijdens een
        # deploy-overlap) kunnen de pre-check-SELECT hierboven allebei
        # passeren vóórdat een van beiden commit; zonder deze insert-
        # first-claim zouden beiden de LLM aanroepen en allebei een
        # zichtbare suggestie-post naar Mattermost sturen, en pas de
        # állerlaatste insert zou de unique constraint raken — te laat om
        # de dubbele Mattermost-post nog te voorkomen.
        record = MattermostPostLink(
            post_id=post_id,
            channel_id=channel_id,
            root_id=root_id,
            scope_type=channel_link.scope_type,
            scope_id=channel_link.scope_id,
            mm_user_id=mm_user_id,
            person_id=person_id,
        )
        self.session.add(record)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except (IntegrityError, PendingRollbackError):
            # Race-condition op unique post_id — andere worker was sneller.
            # Bij een conflict tegen een nog-niet-gecommitte rij van de
            # andere worker (i.p.v. een al-gecommitte rij) blokkeert onze
            # INSERT eerst op de rij-lock en faalt pas zodra de andere
            # transactie commit; dat laat de *outer* transactie hier
            # poisoned achter (niet alleen het savepoint), dus zonder
            # expliciete rollback zou de volgende `session.commit()` bij
            # de caller alsnog een PendingRollbackError geven.
            await self.session.rollback()
            return

        message = post.get("message") or ""
        lead_activity_id: UUID | None = None
        suggested_lead_id: UUID | None = None
        skipped_reason: str | None = None

        if (
            channel_link.scope_type == SCOPE_LEAD
            and channel_link.auto_note_enabled
            and message.strip()
        ):
            if await self._is_noise(message):
                skipped_reason = "noise"
            else:
                lead_activity_id = await self._create_auto_note(
                    lead_id=channel_link.scope_id,
                    post=post,
                    message=message,
                    author_person_id=person_id,
                    mm_user_id=mm_user_id,
                    post_id=post_id,
                    channel_id=channel_id,
                )
        elif (
            channel_link.scope_type == SCOPE_INITIATIEF
            and channel_link.suggest_leads_enabled
            and message.strip()
        ):
            suggested_lead_id, suggest_reason = await self._create_suggested_lead(
                channel_link_initiatief_id=channel_link.scope_id,
                channel_display_name=channel_link.channel_display_name,
                channel_id=channel_id,
                post=post,
                message=message,
            )
            if suggested_lead_id is None:
                skipped_reason = suggest_reason
        elif channel_link.scope_type == SCOPE_LEAD and not message.strip():
            # Joins, leaves, system-events — nuttig om vast te leggen
            # zodat we de post niet opnieuw zien, maar geen note van maken.
            skipped_reason = "no_link"

        record.lead_activity_id = lead_activity_id
        record.suggested_lead_id = suggested_lead_id
        record.skipped_reason = skipped_reason
        await self.session.flush()

        # Eén regel per verwerkte post in production logs zodat we
        # kunnen zien waarom een note wel/niet ontstaat zonder DB-query.
        outcome = (
            f"note={lead_activity_id}"
            if lead_activity_id
            else f"suggested={suggested_lead_id}"
            if suggested_lead_id
            else f"skipped={skipped_reason or 'none'}"
        )
        logger.info(
            "Ingest %s scope=%s/%s %s",
            post_id,
            channel_link.scope_type,
            channel_link.scope_id,
            outcome,
        )

        # Bump last_seen_post_at zodat recovery na reconnect klopt.
        create_at = post.get("create_at")
        if isinstance(create_at, int):
            await link_repo.update_last_seen(channel_link, create_at)

    async def _is_noise(self, message: str) -> bool:
        """Vraag VLAM of dit een triviaal/ack-bericht is.

        Korte heuristiek vooraf: berichten van < 4 chars of alleen emoji's
        zijn sowieso ruis — daar verspillen we geen LLM-call aan.
        """
        stripped = message.strip()
        if len(stripped) < 4:
            return True
        from bouwmeester.services.llm import DataSensitivity
        from bouwmeester.services.llm.factory import get_llm_service_for

        llm = await get_llm_service_for(DataSensitivity.CONFIDENTIAL, self.session)
        if llm is None:
            return False
        return await llm.is_mattermost_noise(stripped)

    async def _maybe_summarize(self, message: str) -> str | None:
        """Vat lange berichten samen via VLAM. Returns None als niet
        gesummariseerd is."""
        if len(message) <= 600:
            return None
        from bouwmeester.services.llm import DataSensitivity
        from bouwmeester.services.llm.factory import get_llm_service_for

        llm = await get_llm_service_for(DataSensitivity.CONFIDENTIAL, self.session)
        if llm is None:
            return None
        summary = await llm.summarize_mattermost_message(message)
        return summary or None

    async def _create_auto_note(
        self,
        *,
        lead_id: UUID,
        post: dict,
        message: str,
        author_person_id: UUID | None,
        mm_user_id: str | None,
        post_id: str,
        channel_id: str,
    ) -> UUID:
        """Schrijf een LeadActivity en eventuele doc-link-attachments."""
        permalink = self._build_permalink(channel_id, post_id)
        summary = await self._maybe_summarize(message)
        body = summary or message
        prefix = ""
        if author_person_id is None and mm_user_id:
            prefix = f"_(via mm:@{mm_user_id})_  \n"
        plain_content = prefix + body

        # Probeer @username-vermeldingen om te zetten naar TipTap-mentions
        # zodat het frontend ze als klikbare badge rendert. Als geen enkele
        # username aan een Person gekoppeld is, vallen we terug op platte
        # tekst (bestaand gedrag).
        tiptap_json, mentioned_ids = await render_mattermost_message_to_tiptap(
            self.session, plain_content
        )
        content = tiptap_json or plain_content

        metadata = {
            "source": "mattermost",
            "mm_post_id": post_id,
            "mm_channel_id": channel_id,
            "mm_user_id": mm_user_id,
            "mm_root_id": post.get("root_id") or None,
            "mm_create_at": post.get("create_at"),
            "mm_permalink": permalink,
        }
        if summary:
            metadata["mm_original"] = message

        activity = LeadActivity(
            lead_id=lead_id,
            author_id=author_person_id,
            content=content,
            activity_type="note",
            metadata_=metadata,
        )
        self.session.add(activity)
        await self.session.flush()
        await self.session.refresh(activity)

        # Sync mentions + notify gementionde personen. Geen-op als content
        # geen TipTap-JSON is (sync_mentions parsed dan een lege lijst).
        if mentioned_ids:
            lead = await self.session.get(Lead, lead_id)
            lead_title = lead.title if lead is not None else "Mattermost-bericht"
            await sync_and_notify_mentions(
                self.session,
                "lead_activity",
                activity.id,
                content,
                lead_title,
                sender_id=author_person_id,
                source_lead_id=lead_id,
                exclude_person_id=author_person_id,
            )

        for link in extract_doc_links(message):
            url = link["url"]
            label = derive_attachment_label(url)
            attachment = LeadAttachment(
                lead_id=lead_id,
                soort="link",
                url=url,
                bestandsnaam=label,
                source="mattermost",
                source_ref=post_id,
            )
            # Naïef dedupe binnen één lead: niet twee keer dezelfde URL.
            existing = await self.session.execute(
                select(LeadAttachment.id).where(
                    LeadAttachment.lead_id == lead_id,
                    LeadAttachment.url == url,
                )
            )
            if existing.scalar_one_or_none() is None:
                self.session.add(attachment)

        await self._ingest_post_files(lead_id=lead_id, post=post, post_id=post_id)
        await self.session.flush()
        return activity.id

    async def _ingest_post_files(
        self,
        *,
        lead_id: UUID,
        post: dict,
        post_id: str,
    ) -> None:
        """Download native Mattermost file-uploads naar ``LeadAttachment``.

        Mattermost stuurt ``file_ids`` mee in ``posted``-events; de rijkere
        ``metadata.files`` is niet altijd aanwezig maar bevat naam + mime
        + size zodat we per-file één API-call kunnen besparen. Per file:

        - haal info op (uit ``metadata.files`` of via ``get_file_info``)
        - check tegen ``ALLOWED_CONTENT_TYPES``
        - download met ``MAX_UPLOAD_SIZE`` cap
        - magic-byte verificatie
        - schrijf naar disk via bestaand storage-pad
        - dedupe op ``(lead_id, source='mattermost', source_ref)`` waarbij
          ``source_ref = "{post_id}:{file_id}"``

        Per-file ``try/except`` zodat één rotte file de andere files en
        de note zelf niet sloopt.
        """
        file_ids = post.get("file_ids") or []
        if not file_ids:
            return

        # metadata.files (indien aanwezig) heeft naam/mime/size — dat
        # bespaart een get_file_info-call per bestand.
        meta_by_id: dict[str, dict] = {}
        for f in (post.get("metadata") or {}).get("files") or []:
            fid = f.get("id")
            if fid:
                meta_by_id[fid] = f

        from bouwmeester.services.mattermost_service import MattermostService

        service = MattermostService(self.session)
        try:
            for file_id in file_ids:
                try:
                    await self._ingest_one_file(
                        service=service,
                        lead_id=lead_id,
                        post_id=post_id,
                        file_id=file_id,
                        meta=meta_by_id.get(file_id),
                    )
                except ValueError:
                    # Mattermost niet (volledig) geconfigureerd, bv. geen
                    # bot-token. Niet zinvol om de loop af te maken; alle
                    # volgende files zouden dezelfde error geven.
                    logger.warning(
                        "Mattermost niet geconfigureerd, sla %d file(s) over",
                        len(file_ids),
                    )
                    return
                except Exception:
                    logger.exception(
                        "Kon Mattermost-file %s voor lead %s niet ingesten",
                        file_id,
                        lead_id,
                    )
        finally:
            await service.close()

    async def _ingest_one_file(
        self,
        *,
        service,
        lead_id: UUID,
        post_id: str,
        file_id: str,
        meta: dict | None,
    ) -> None:
        """Verwerk één file_id. Helper van ``_ingest_post_files`` zodat de
        try/except-loop daar leesbaar blijft."""
        source_ref = f"{post_id}:{file_id}"

        # Dedupe vooraf — voorkomt overbodige download bij replay.
        existing = await self.session.execute(
            select(LeadAttachment.id).where(
                LeadAttachment.lead_id == lead_id,
                LeadAttachment.source == "mattermost",
                LeadAttachment.source_ref == source_ref,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return

        info = meta or await service.get_file_info(file_id)
        if not info:
            logger.warning("Geen file-info voor %s, skip", file_id)
            return

        claimed_ct = (info.get("mime_type") or "application/octet-stream").lower()
        if claimed_ct not in ALLOWED_CONTENT_TYPES:
            logger.info(
                "Mattermost-file %s heeft niet-toegestaan type %s, skip",
                file_id,
                claimed_ct,
            )
            return

        content = await service.download_file(file_id, max_bytes=MAX_UPLOAD_SIZE)
        if content is None:
            return

        if not verify_content_type(content, claimed_ct):
            logger.info(
                "Mattermost-file %s magic bytes komen niet overeen met %s, skip",
                file_id,
                claimed_ct,
            )
            return

        leads_dir = ensure_bijlagen_dir() / "leads"
        original_name = info.get("name") or f"bijlage-{file_id}"
        filename, relative_path, _ = write_upload_to_disk(
            content, original_name, leads_dir, item_id=lead_id
        )
        # write_upload_to_disk geeft pad relatief tot leads_dir; DB slaat
        # op tov LEADS_BIJLAGEN_ROOT, dus pre-pend "leads/".
        relative_path = f"leads/{relative_path}"

        attachment = LeadAttachment(
            lead_id=lead_id,
            soort="file",
            bestandsnaam=filename,
            content_type=claimed_ct,
            bestandsgrootte=len(content),
            pad=relative_path,
            source="mattermost",
            source_ref=source_ref,
        )
        self.session.add(attachment)
        await self.session.flush()

    async def _create_suggested_lead(
        self,
        *,
        channel_link_initiatief_id: UUID,
        channel_display_name: str,
        channel_id: str,
        post: dict,
        message: str,
    ) -> tuple[UUID | None, str | None]:
        """Vraag VLAM of dit een lead is en maak — bij ja — een SuggestedLead
        plus een bot-reply met approval-knoppen in de thread.

        Returns ``(uuid_of_None, reason)`` met ``reason`` ∈
        ``"llm_unavailable" | "no_lead" | "stale_initiatief" | None``.
        ``reason`` wordt door de caller in ``MattermostPostLink.skipped_reason``
        bewaard, zodat we onderscheid kunnen maken tussen "VLAM was tijdelijk
        offline" (reprocessable) en "echt geen lead" (definitief)."""
        from bouwmeester.services.llm import DataSensitivity
        from bouwmeester.services.llm.factory import get_llm_service_for

        llm = await get_llm_service_for(DataSensitivity.CONFIDENTIAL, self.session)
        if llm is None:
            logger.warning(
                "Geen CONFIDENTIAL-LLM beschikbaar — sla suggested-lead over"
            )
            return None, "llm_unavailable"

        initiatief = await self.session.get(Initiatief, channel_link_initiatief_id)
        if initiatief is None:
            logger.warning(
                "Initiatief %s voor kanaal-koppeling bestaat niet (meer)",
                channel_link_initiatief_id,
            )
            return None, "stale_initiatief"

        rows = await self._collect_lead_candidates_for_llm(
            channel_link_initiatief_id, message
        )
        recent = [
            {
                "id": str(row.id),
                "title": row.title,
                "organization": row.organization,
                "stage": row.stage,
            }
            for row in rows
        ]

        result = await llm.classify_mattermost_lead_candidate(
            message=message,
            initiatief_naam=initiatief.naam,
            channel_display_name=channel_display_name,
            recent_leads=recent,
        )
        if not result.is_lead:
            return None, "no_lead"

        match_lead_uuid: UUID | None = None
        matched_lead: dict | None = None
        if result.match_existing_lead_id:
            try:
                candidate = UUID(result.match_existing_lead_id)
            except ValueError:
                candidate = None
            if candidate is not None:
                for row in rows:
                    if str(row.id) == str(candidate):
                        match_lead_uuid = candidate
                        stage_label = await self._resolve_stage_label(
                            channel_link_initiatief_id, row.stage
                        )
                        matched_lead = {
                            "title": row.title,
                            "stage": row.stage,
                            "stage_label": stage_label,
                        }
                        break

        suggested = SuggestedLead(
            source_type="mattermost",
            source_post_id=post["id"],
            source_channel_id=channel_id,
            source_root_id=post.get("root_id") or None,
            initiatief_id=channel_link_initiatief_id,
            proposed_title=(result.proposed_title or "Nieuwe lead vanuit Mattermost")[
                :500
            ],
            proposed_description=result.proposed_description or None,
            raw_text=message,
            confidence=result.confidence,
            reasoning=result.reasoning or None,
            match_existing_lead_id=match_lead_uuid,
            status=STATUS_PENDING,
        )
        self.session.add(suggested)
        await self.session.flush()
        await self.session.refresh(suggested)

        # Post de bot-reply met knoppen — fout daar is niet fataal voor het
        # SuggestedLead-record. Als er geen MattermostService is (test) doen
        # we niets.
        try:
            await self._post_suggestion_reply(
                channel_id=channel_id,
                root_post_id=post.get("root_id") or post["id"],
                suggested=suggested,
                initiatief=initiatief,
                matched_lead=matched_lead,
            )
        except Exception:
            logger.exception(
                "Kon bot-reply voor suggested lead %s niet plaatsen", suggested.id
            )

        return suggested.id, None

    async def _collect_lead_candidates_for_llm(
        self, initiatief_id: UUID, message: str
    ) -> list:
        """Selecteer bestaande leads die mogelijk relevant zijn voor de
        LLM-duplicate-check.

        Twee groepen, gededupliceerd op id en gecapped:

        1. ``RECENT_LEADS_FOR_LLM`` nieuwste leads voor dit initiatief
           (recency, vangt actieve kwesties zonder expliciete naam in
           het bericht).
        2. ``SIMILAR_LEADS_FOR_LLM`` leads die het meest lijken op het
           bericht via ``pg_trgm.word_similarity`` op titel of
           organisatie (vangt oude leads waarvan de naam expliciet
           genoemd wordt; bv. "HHNK" matcht een lead "HHNK
           (Hoogheemraadschap...)" ook al staat die niet in de top-25).

        Recente leads krijgen voorrang in de dedup zodat hun ``stage``
        consistent is. ``SIMILAR_LEAD_THRESHOLD`` is een ruime default;
        ``word_similarity`` retourneert 0..1 en 0.3 vangt afkortingen +
        kleine spelvariaties zonder te veel ruis.
        """
        recent_stmt = (
            select(Lead.id, Lead.title, Lead.organization, Lead.stage)
            .where(Lead.initiatief_id == initiatief_id)
            .order_by(Lead.created_at.desc())
            .limit(RECENT_LEADS_FOR_LLM)
        )
        recent_rows = (await self.session.execute(recent_stmt)).all()

        # Pre-filter ruwweg op een ondergrens om geen full-table-scan op te
        # eten in initiatieven met veel leads. word_similarity is symmetrisch:
        # we zoeken leads waar TITEL of ORG voorkomt als "woord" in MESSAGE.
        title_sim = func.word_similarity(Lead.title, message)
        org_sim = func.word_similarity(Lead.organization, message)
        max_sim = func.greatest(title_sim, func.coalesce(org_sim, 0.0))
        similar_stmt = (
            select(Lead.id, Lead.title, Lead.organization, Lead.stage)
            .where(
                Lead.initiatief_id == initiatief_id,
                or_(
                    title_sim > SIMILAR_LEAD_THRESHOLD,
                    org_sim > SIMILAR_LEAD_THRESHOLD,
                ),
            )
            .order_by(max_sim.desc())
            .limit(SIMILAR_LEADS_FOR_LLM)
        )
        similar_rows = (await self.session.execute(similar_stmt)).all()

        merged: dict = {}
        for row in recent_rows:
            merged[row.id] = row
        for row in similar_rows:
            merged.setdefault(row.id, row)
        return list(merged.values())[:MAX_LEADS_FOR_LLM]

    async def _resolve_stage_label(
        self, initiatief_id: UUID | None, stage: str | None
    ) -> str:
        """Vertaal een stage-slug naar de zichtbare kolomnaam.

        Sinds per-initiatief lead_columns kunnen eigenaren stages
        hernoemen; we lezen de naam direct uit ``lead_column``. Voor
        orphan-leads (geen initiatief) of slugs die niet langer als
        kolom bestaan vallen we terug op de 7-default-labels — anders
        krijgt de bot-reply de raw slug te zien.
        """
        if not stage:
            return ""
        if initiatief_id is not None:
            from sqlalchemy import select

            from bouwmeester.models.lead_column import LeadColumn

            stmt = select(LeadColumn.name).where(
                LeadColumn.initiatief_id == initiatief_id,
                LeadColumn.slug == stage,
            )
            name = (await self.session.execute(stmt)).scalar_one_or_none()
            if name:
                return name
        return _DEFAULT_STAGE_LABELS.get(stage, stage)

    async def _post_suggestion_reply(
        self,
        *,
        channel_id: str,
        root_post_id: str,
        suggested: SuggestedLead,
        initiatief: Initiatief,
        matched_lead: dict | None,
    ) -> None:
        """Plaats een bot-reply met emoji-reactions als trigger.

        We gebruiken bewust geen interactive message-attachment-buttons:
        Mattermost stuurt voor button-clicks geen authenticatie-token mee
        in de webhook, en de digilab-installatie levert sowieso geen POSTs
        naar onze publieke endpoint. Reactions komen via dezelfde
        websocket binnen die we al gebruiken voor het meelezen, en zijn
        daarmee robuust tegen die platformbeperkingen.

        Bij ``matched_lead`` (titel + stage van een door de LLM herkende
        bestaande lead) gebruiken we andere copy en zetten we :link: als
        eerste/aanbevolen actie boven :white_check_mark:.
        """
        from bouwmeester.services.mattermost_service import MattermostService

        service = MattermostService(self.session)
        try:
            if not await service.is_enabled():
                return

            pct = int((suggested.confidence or 0) * 100)

            if matched_lead is not None:
                stage_label = matched_lead.get("stage_label") or ""
                text = (
                    f":link: Dit lijkt te gaan over een bestaande lead voor "
                    f"**{initiatief.naam}**: **{matched_lead['title']}**"
                    f"{f' ({stage_label})' if stage_label else ''}.\n"
                    f"_Vertrouwen:_ {pct}%\n\n"
                    "_Reageer met:_\n"
                    ":link: om dit bericht aan die lead te koppelen "
                    "_(aanbevolen)_\n"
                    ":white_check_mark: om tóch een nieuwe lead aan te maken\n"
                    ":x: om de suggestie te negeren"
                )
                attachment = {
                    "color": "#3B82F6",
                    "title": matched_lead["title"],
                    "text": (
                        f"Bestaande lead in stage _{stage_label}_. "
                        if stage_label
                        else ""
                    )
                    + "Bij koppelen wordt dit Mattermost-bericht als notitie "
                    "aan de lead toegevoegd.",
                    "footer": "Bouwmeester · bestaande lead herkend",
                }
            else:
                text = (
                    f":dart: Nieuwe lead voor **{initiatief.naam}**?\n"
                    f"_Voorstel:_ {suggested.proposed_title}\n"
                    f"_Vertrouwen:_ {pct}%\n\n"
                    "_Reageer met:_\n"
                    ":white_check_mark: om de lead aan te maken\n"
                    ":x: om de suggestie te negeren"
                )
                attachment = {
                    "color": "#3B82F6",
                    "title": suggested.proposed_title,
                    "text": suggested.proposed_description or "",
                    "footer": "Bouwmeester · suggestie vanuit Mattermost",
                }

            data = await service.reply_to_post(
                channel_id,
                root_post_id,
                text,
                props={"attachments": [attachment]},
            )
            mm_thread_post_id = (data or {}).get("id")
            if not mm_thread_post_id:
                return
            suggested.mm_thread_post_id = mm_thread_post_id
            await self.session.flush()

            # Plaats bot-reactions als clickable affordance. Bij een match
            # komt :link: eerst (aanbevolen actie), anders alleen :check: + :x:.
            # Failures zijn niet fataal; de gebruiker kan zelf reacties plaatsen.
            if matched_lead is not None:
                await service.add_reaction(mm_thread_post_id, "link")
                await service.add_reaction(mm_thread_post_id, "white_check_mark")
            else:
                await service.add_reaction(mm_thread_post_id, "white_check_mark")
            await service.add_reaction(mm_thread_post_id, "x")
        finally:
            await service.close()

    def _build_permalink(self, channel_id: str, post_id: str) -> str | None:
        """Best-effort permalink: ``{mm_base}/_redirect/pl/{post_id}``.

        Mattermost ondersteunt een teamonafhankelijke redirect-URL voor
        post-permalinks. Dat scheelt ons het opzoeken van de team-naam.
        Zonder bekende base-URL geven we ``None`` terug.
        """
        if not self.mm_base_url:
            return None
        return f"{self.mm_base_url}/_redirect/pl/{post_id}"
