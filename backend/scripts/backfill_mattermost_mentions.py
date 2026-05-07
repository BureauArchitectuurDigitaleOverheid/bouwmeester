"""Backfill ``@username``-mentions in bestaande Mattermost-LeadActivities.

Loop alle ``LeadActivity``-records langs waar ``metadata_->>'source' =
'mattermost'`` én ``content`` géén TipTap-JSON is. Render opnieuw met de
ingest-helper; als er nu wel een gekoppelde mention te vinden is, schrijf
de TipTap-JSON terug en sync ``Mention``-records (geen notificaties — die
zouden retroactief storen).

Run:

    uv run --project backend python -m scripts.backfill_mattermost_mentions
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from bouwmeester.core.database import async_session
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.services.mattermost_mention_renderer import (
    render_mattermost_message_to_tiptap,
)
from bouwmeester.services.mention_service import MentionService

logger = logging.getLogger(__name__)


def _looks_like_tiptap(content: str) -> bool:
    s = content.lstrip()
    return s.startswith('{"type"') or s.startswith("{'type'")


async def backfill() -> tuple[int, int]:
    """Returns ``(geïnspecteerd, herschreven)``."""
    inspected = 0
    rewritten = 0
    async with async_session() as session:
        stmt = select(LeadActivity).where(
            LeadActivity.metadata_["source"].as_string() == "mattermost"
        )
        rows = (await session.execute(stmt)).scalars().all()
        for activity in rows:
            inspected += 1
            if not activity.content or _looks_like_tiptap(activity.content):
                continue
            tiptap_json, mentioned_ids = await render_mattermost_message_to_tiptap(
                session, activity.content
            )
            if not tiptap_json or not mentioned_ids:
                continue
            activity.content = tiptap_json
            await MentionService(session).sync_mentions(
                "lead_activity",
                activity.id,
                tiptap_json,
                created_by=activity.author_id,
            )
            rewritten += 1
            logger.info(
                "Herschreven LeadActivity %s met %d mention(s)",
                activity.id,
                len(mentioned_ids),
            )
        await session.commit()
    return inspected, rewritten


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    inspected, rewritten = await backfill()
    print(f"Geïnspecteerd: {inspected}, herschreven: {rewritten}")


if __name__ == "__main__":
    asyncio.run(main())
