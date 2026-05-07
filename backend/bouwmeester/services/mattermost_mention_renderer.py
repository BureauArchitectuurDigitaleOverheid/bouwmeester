"""Bouw TipTap-JSON uit een Mattermost-bericht met @username-vermeldingen.

Mattermost levert een mention als platte tekst ``@username``. Wij willen die
als klikbare TipTap-mention tonen — mits de username gekoppeld is aan een
``Person``. Onbekende mentions blijven gewoon tekst staan.
"""

from __future__ import annotations

import json
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.models.person import Person

# Mattermost-usernames: 3-22 tekens, ``a-z0-9._-``. We accepteren ook iets
# langere strings (sommige instances staan tot 64 toe) en filteren bekende
# kanaalnamen later op DB-lookup.
_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9._-]{1,63})")


async def _resolve_usernames(
    session: AsyncSession, usernames: set[str]
) -> dict[str, tuple[UUID, str]]:
    """Map Mattermost-username → (person_id, person_naam) via DB-lookup."""
    if not usernames:
        return {}
    stmt = (
        select(
            MattermostUser.mattermost_username,
            MattermostUser.person_id,
            Person.naam,
        )
        .join(Person, Person.id == MattermostUser.person_id)
        .where(MattermostUser.mattermost_username.in_(usernames))
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _build_paragraph(line: str, resolved: dict[str, tuple[UUID, str]]) -> dict:
    """Bouw één TipTap-paragraph; vervang bekende ``@username`` door mention-nodes."""
    children: list[dict] = []
    cursor = 0
    for match in _MENTION_RE.finditer(line):
        username = match.group(1)
        hit = resolved.get(username)
        if hit is None:
            continue
        person_id, naam = hit
        # Tekst voor de mention.
        if match.start() > cursor:
            children.append({"type": "text", "text": line[cursor : match.start()]})
        children.append(
            {
                "type": "mention",
                "attrs": {
                    "id": str(person_id),
                    "label": naam,
                    "mentionType": "person",
                },
            }
        )
        cursor = match.end()
    # Restant.
    if cursor < len(line):
        children.append({"type": "text", "text": line[cursor:]})
    elif not children:
        # Volledig lege regel — TipTap accepteert een paragraph zonder content.
        return {"type": "paragraph"}
    return {"type": "paragraph", "content": children}


async def render_mattermost_message_to_tiptap(
    session: AsyncSession, message: str
) -> tuple[str | None, list[UUID]]:
    """Zet ``message`` om naar een TipTap-JSON-string als er gekoppelde
    ``@username``-vermeldingen in zitten.

    Returns ``(tiptap_json, mentioned_person_ids)``. Wanneer geen enkele
    username gekoppeld is, geven we ``(None, [])`` terug zodat de caller op
    de oorspronkelijke platte-tekst-flow kan terugvallen.
    """
    if not message:
        return None, []

    candidates = {m.group(1) for m in _MENTION_RE.finditer(message)}
    resolved = await _resolve_usernames(session, candidates)
    if not resolved:
        return None, []

    # Splits op newlines zodat regelopmaak intact blijft.
    paragraphs = [_build_paragraph(line, resolved) for line in message.split("\n")]
    doc = {"type": "doc", "content": paragraphs}
    person_ids = [pid for pid, _ in resolved.values()]
    return json.dumps(doc, ensure_ascii=False), person_ids
