"""Verwerking van Mattermost-posts in gekoppelde kanalen.

Per binnenkomend ``posted``-event:
- skip bot-eigen berichten en niet-gekoppelde kanalen
- match auteur via bestaande ``mattermost_user``-link
- voor lead-scope met ``auto_note_enabled``: maak ``LeadActivity`` (note)
  en haal doc-links op naar ``LeadAttachment(soort=link)``
- voor initiatief-scope met ``suggest_leads_enabled``: nog niet — komt in
  PR3 (hier alleen ``mattermost_post_link``-record)
- altijd: schrijf ``mattermost_post_link`` zodat de post niet opnieuw
  wordt verwerkt
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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

logger = logging.getLogger(__name__)


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

    async def ingest_post(self, post: dict) -> None:
        """Verwerk één Mattermost-post.

        De caller is verantwoordelijk voor commit/rollback van de session.
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
            suggested_lead_id = await self._create_suggested_lead(
                channel_link_initiatief_id=channel_link.scope_id,
                channel_display_name=channel_link.channel_display_name,
                channel_id=channel_id,
                post=post,
                message=message,
            )
            if suggested_lead_id is None:
                skipped_reason = "noise"
        elif channel_link.scope_type == SCOPE_LEAD and not message.strip():
            # Joins, leaves, system-events — nuttig om vast te leggen
            # zodat we de post niet opnieuw zien, maar geen note van maken.
            skipped_reason = "no_link"

        record = MattermostPostLink(
            post_id=post_id,
            channel_id=channel_id,
            root_id=root_id,
            scope_type=channel_link.scope_type,
            scope_id=channel_link.scope_id,
            mm_user_id=mm_user_id,
            person_id=person_id,
            lead_activity_id=lead_activity_id,
            suggested_lead_id=suggested_lead_id,
            skipped_reason=skipped_reason,
        )
        self.session.add(record)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            # Race-condition op unique post_id — andere worker was sneller.
            return

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
        content = prefix + body

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
        await self.session.flush()
        return activity.id

    async def _create_suggested_lead(
        self,
        *,
        channel_link_initiatief_id: UUID,
        channel_display_name: str,
        channel_id: str,
        post: dict,
        message: str,
    ) -> UUID | None:
        """Vraag VLAM of dit een lead is en maak — bij ja — een SuggestedLead
        plus een bot-reply met approval-knoppen in de thread.

        Returns ``None`` als het bericht volgens de LLM geen lead is."""
        from bouwmeester.services.llm import DataSensitivity
        from bouwmeester.services.llm.factory import get_llm_service_for

        llm = await get_llm_service_for(DataSensitivity.CONFIDENTIAL, self.session)
        if llm is None:
            logger.debug("Geen CONFIDENTIAL-LLM beschikbaar — sla suggested-lead over")
            return None

        initiatief = await self.session.get(Initiatief, channel_link_initiatief_id)
        if initiatief is None:
            logger.warning(
                "Initiatief %s voor kanaal-koppeling bestaat niet (meer)",
                channel_link_initiatief_id,
            )
            return None

        recent_leads_stmt = (
            select(Lead.id, Lead.title, Lead.stage)
            .where(Lead.initiatief_id == channel_link_initiatief_id)
            .order_by(Lead.created_at.desc())
            .limit(20)
        )
        rows = (await self.session.execute(recent_leads_stmt)).all()
        recent = [
            {"id": str(row.id), "title": row.title, "stage": row.stage} for row in rows
        ]

        result = await llm.classify_mattermost_lead_candidate(
            message=message,
            initiatief_naam=initiatief.naam,
            channel_display_name=channel_display_name,
            recent_leads=recent,
        )
        if not result.is_lead:
            return None

        match_lead_uuid: UUID | None = None
        if result.match_existing_lead_id:
            try:
                candidate = UUID(result.match_existing_lead_id)
            except ValueError:
                candidate = None
            if candidate is not None and any(
                str(row.id) == str(candidate) for row in rows
            ):
                match_lead_uuid = candidate

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
                match_lead=match_lead_uuid is not None,
            )
        except Exception:
            logger.exception(
                "Kon bot-reply voor suggested lead %s niet plaatsen", suggested.id
            )

        return suggested.id

    async def _post_suggestion_reply(
        self,
        *,
        channel_id: str,
        root_post_id: str,
        suggested: SuggestedLead,
        initiatief: Initiatief,
        match_lead: bool,
    ) -> None:
        """Plaats een bot-reply met interactive attachment in de thread."""
        from bouwmeester.services.mattermost_service import MattermostService

        service = MattermostService(self.session)
        try:
            if not await service.is_enabled():
                return
            text = (
                f":dart: Ik denk dat dit een lead is voor "
                f"**{initiatief.naam}**.\n"
                f"_Voorstel:_ {suggested.proposed_title}\n"
                f"_Vertrouwen:_ {int((suggested.confidence or 0) * 100)}%"
            )
            actions = [
                {
                    "id": "create_lead",
                    "name": "Maak lead aan",
                    "integration": {
                        "url": (
                            f"{service.settings.BACKEND_URL.rstrip('/')}"
                            "/api/mattermost/action"
                        ),
                        "context": {
                            "action": "create_lead_from_suggestion",
                            "suggested_lead_id": str(suggested.id),
                        },
                    },
                },
                {
                    "id": "reject_lead",
                    "name": "Negeer",
                    "integration": {
                        "url": (
                            f"{service.settings.BACKEND_URL.rstrip('/')}"
                            "/api/mattermost/action"
                        ),
                        "context": {
                            "action": "reject_suggestion",
                            "suggested_lead_id": str(suggested.id),
                        },
                    },
                },
            ]
            if match_lead:
                actions.insert(
                    1,
                    {
                        "id": "link_lead",
                        "name": "Koppel aan bestaande lead",
                        "integration": {
                            "url": (
                                f"{service.settings.BACKEND_URL.rstrip('/')}"
                                "/api/mattermost/action"
                            ),
                            "context": {
                                "action": "link_lead_to_suggestion",
                                "suggested_lead_id": str(suggested.id),
                            },
                        },
                    },
                )
            attachment = {
                "color": "#3B82F6",
                "title": suggested.proposed_title,
                "text": suggested.proposed_description or "",
                "footer": "Bouwmeester · suggestie vanuit Mattermost",
                "actions": actions,
            }
            client = await service._get_client()
            payload = {
                "channel_id": channel_id,
                "root_id": root_post_id,
                "message": text,
                "props": {"attachments": [attachment]},
            }
            resp = await client.post("/api/v4/posts", json=payload)
            resp.raise_for_status()
            data = resp.json()
            mm_thread_post_id = data.get("id")
            if mm_thread_post_id:
                suggested.mm_thread_post_id = mm_thread_post_id
                await self.session.flush()
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
