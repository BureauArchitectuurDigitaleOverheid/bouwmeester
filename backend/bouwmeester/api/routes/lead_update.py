"""API routes for LeadUpdatePost — per-lead update posts (mail + community)."""

import base64
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_found
from bouwmeester.api.routes.leads import _check_lead_access, _robust_parse_json
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.lead import LeadRepository
from bouwmeester.schema.lead_update import (
    LeadUpdateExtractResult,
    LeadUpdatePostCreate,
    LeadUpdatePostEdit,
    LeadUpdatePostResponse,
)
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.document_extract import extract_text
from bouwmeester.services.eml_builder import build_outlook_draft_eml
from bouwmeester.services.markdown_min import markdown_to_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["lead-updates"])


def _to_response(post: LeadUpdatePost) -> LeadUpdatePostResponse:
    return LeadUpdatePostResponse(
        id=post.id,
        lead_id=post.lead_id,
        titel=post.titel,
        body_internal=post.body_internal,
        body_public=post.body_public,
        mail_subject=post.mail_subject,
        mail_to=post.mail_to,
        mail_cc=post.mail_cc,
        published_at=post.published_at,
        published_by_id=post.published_by_id,
        published_by_naam=(post.published_by.naam if post.published_by else None),
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


async def _load_post(
    db: AsyncSession, lead_id: UUID, post_id: UUID
) -> LeadUpdatePost | None:
    stmt = (
        select(LeadUpdatePost)
        .where(
            LeadUpdatePost.id == post_id,
            LeadUpdatePost.lead_id == lead_id,
        )
        .options(selectinload(LeadUpdatePost.published_by))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _build_lead_context(db: AsyncSession, lead: Lead) -> str:
    """Compose a short paragraph the LLM uses to ground the update.

    Pulls in initiatief metadata, lead title/organisatie/description, recent
    activity bodies and the contact name list so the model has enough to
    write a coherent update even when the user pastes only a one-liner.
    """
    parts: list[str] = []
    if lead.initiatief is not None:
        init = lead.initiatief
        parts.append(f"Initiatief: {init.naam}")
        if init.beschrijving:
            parts.append(f"Initiatief-beschrijving: {init.beschrijving[:800]}")
    parts.append(f"Lead: {lead.title}")
    if lead.organization:
        parts.append(f"Organisatie: {lead.organization}")
    if lead.description:
        parts.append(f"Beschrijving: {lead.description[:600]}")
    parts.append(f"Stage: {lead.stage}")

    activities_stmt = (
        select(LeadActivity)
        .where(LeadActivity.lead_id == lead.id)
        .order_by(LeadActivity.created_at.desc())
        .limit(8)
    )
    activities = (await db.execute(activities_stmt)).scalars().all()
    if activities:
        parts.append("\nRecente activity (nieuwste eerst):")
        for a in activities:
            stamp = a.created_at.strftime("%Y-%m-%d") if a.created_at else "?"
            content = (a.content or "").strip()
            if not content:
                continue
            parts.append(f"- [{stamp} · {a.activity_type}] {content[:600]}")
            if a.uitkomst:
                parts.append(f"  uitkomst: {a.uitkomst[:300]}")
            if a.vervolgacties:
                parts.append(f"  vervolg: {a.vervolgacties[:300]}")

    contacts = await _list_contacts_with_email(db, lead.id)
    if contacts:
        names = ", ".join(
            f"{c['naam']}" + (f" <{c['email']}>" if c["email"] else "")
            for c in contacts
        )
        parts.append(f"\nContacten: {names}")

    return "\n".join(parts)


async def _list_contacts_with_email(
    db: AsyncSession, lead_id: UUID
) -> list[dict[str, str | None]]:
    """Return contact persons attached to the lead with their default email."""
    from bouwmeester.models.person import Person

    stmt = (
        select(ResourcePermission)
        .where(
            ResourcePermission.resource_type == "lead",
            ResourcePermission.resource_id == lead_id,
            ResourcePermission.person_id.isnot(None),
        )
        .options(selectinload(ResourcePermission.person).selectinload(Person.emails))
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: list[dict[str, str | None]] = []
    for rp in rows:
        person = rp.person
        if person is None:
            continue
        email: str | None = None
        emails = getattr(person, "emails", None) or []
        if emails:
            default = next((e for e in emails if e.is_default), None)
            email = (default or emails[0]).email
        if email is None:
            email = getattr(person, "email", None)
        out.append({"naam": person.naam, "email": email})
    return out


async def _suggested_recipients(db: AsyncSession, lead_id: UUID) -> list[str]:
    """Default To: list — emails of every contact linked to the lead."""
    contacts = await _list_contacts_with_email(db, lead_id)
    return sorted({c["email"] for c in contacts if c["email"]})


# ---------------------------------------------------------------------------
# AI parse — produce a draft from raw input + lead context
# ---------------------------------------------------------------------------


@router.post(
    "/{lead_id}/updates/parse",
    response_model=LeadUpdateExtractResult,
)
async def parse_lead_update(
    lead_id: UUID,
    current_user: OptionalUser,
    raw_text: str | None = Form(None),
    use_lead_history: bool = Form(False),
    files: list[UploadFile] | None = None,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadUpdateExtractResult:
    """Parse raw text/uploaded docs (or just the lead history) into an update draft."""
    from bouwmeester.services.llm.factory import get_llm_service
    from bouwmeester.services.llm.prompts import build_lead_update_prompt

    repo = LeadRepository(db)
    lead = require_found(await repo.get_detail(lead_id, init_ctx=init_ctx), "Lead")
    _check_lead_access(lead, init_ctx)

    text_parts: list[str] = []
    image_parts: list[dict] = []

    if raw_text:
        text_parts.append(raw_text)

    if files:
        for f in files:
            content_bytes = await f.read()
            ct = f.content_type or ""
            if ct.startswith("image/"):
                b64 = base64.b64encode(content_bytes).decode("ascii")
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{ct};base64,{b64}"},
                    }
                )
                continue
            # Persist to a tempfile so we can reuse the existing extractor.
            from pathlib import Path
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content_bytes)
                tmp_path = Path(tmp.name)
            try:
                extracted = extract_text(tmp_path, ct)
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if extracted:
                text_parts.append(extracted)

    if not text_parts and not image_parts and not use_lead_history:
        raise HTTPException(
            status_code=400,
            detail=(
                "Geen invoer: geef ruwe tekst, een bestand, of zet"
                " use_lead_history=true om uit lead-historie te genereren."
            ),
        )

    lead_context = await _build_lead_context(db, lead)
    combined_text = "\n\n".join(text_parts).strip()
    if not combined_text and not image_parts:
        # Fallback: only history. Tell the LLM that's intentional.
        combined_text = (
            "(Er is geen nieuwe ruwe invoer. Schrijf de update op basis van de"
            " context van de lead hieronder — vat samen wat er recent gebeurd"
            " is en wat de huidige stand is.)"
        )

    llm = await get_llm_service(db)
    if llm is None:
        raise HTTPException(status_code=503, detail="Geen LLM-service beschikbaar.")

    prompt = build_lead_update_prompt(
        raw_text=combined_text or "(zie afbeelding)",
        lead_context=lead_context,
        initiatief_naam=lead.initiatief.naam if lead.initiatief else None,
    )

    try:
        if image_parts:
            content: list[dict] = [{"type": "text", "text": prompt}]
            content.extend(image_parts)
            response = await llm._client.chat.completions.create(
                model=llm._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": content}],
            )
            response_text = response.choices[0].message.content or ""
        else:
            response_text = await llm._complete(prompt)
        parsed = _robust_parse_json(response_text)
    except Exception:
        logger.exception("Failed to parse lead-update with LLM")
        raise HTTPException(
            status_code=500,
            detail="Fout bij het verwerken van de update.",
        )

    suggested_to = await _suggested_recipients(db, lead_id)
    return LeadUpdateExtractResult(
        titel=parsed.get("titel"),
        body_internal=parsed.get("body_internal"),
        body_public=parsed.get("body_public"),
        mail_subject=parsed.get("mail_subject"),
        suggested_to=suggested_to,
        suggested_cc=[],
    )


# ---------------------------------------------------------------------------
# CRUD + publish
# ---------------------------------------------------------------------------


@router.get(
    "/{lead_id}/updates",
    response_model=list[LeadUpdatePostResponse],
)
async def list_updates(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadUpdatePostResponse]:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    stmt = (
        select(LeadUpdatePost)
        .where(LeadUpdatePost.lead_id == lead_id)
        .options(selectinload(LeadUpdatePost.published_by))
        .order_by(LeadUpdatePost.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_to_response(p) for p in result.scalars().all()]


@router.post(
    "/{lead_id}/updates",
    response_model=LeadUpdatePostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_update(
    lead_id: UUID,
    data: LeadUpdatePostCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadUpdatePostResponse:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    actor_id = current_user.id if current_user else None
    post = LeadUpdatePost(
        lead_id=lead_id,
        titel=data.titel,
        body_internal=data.body_internal,
        body_public=data.body_public,
        mail_subject=data.mail_subject,
        mail_to=list(data.mail_to) if data.mail_to else None,
        mail_cc=list(data.mail_cc) if data.mail_cc else None,
        source_raw_text=data.source_raw_text,
        created_by_id=actor_id,
    )
    if data.publish:
        post.published_at = datetime.now(UTC)
        post.published_by_id = actor_id

    db.add(post)
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])

    await log_activity(
        db,
        current_user,
        None,
        "lead_update.created",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "post_id": str(post.id),
            "published": data.publish,
        },
    )
    return _to_response(post)


@router.put(
    "/{lead_id}/updates/{post_id}",
    response_model=LeadUpdatePostResponse,
)
async def edit_update(
    lead_id: UUID,
    post_id: UUID,
    data: LeadUpdatePostEdit,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadUpdatePostResponse:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    post = require_found(await _load_post(db, lead_id, post_id), "Update")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if key in {"mail_to", "mail_cc"} and value is not None:
            value = list(value)
        setattr(post, key, value)
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.post(
    "/{lead_id}/updates/{post_id}/publish",
    response_model=LeadUpdatePostResponse,
)
async def publish_update(
    lead_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadUpdatePostResponse:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    post = require_found(await _load_post(db, lead_id, post_id), "Update")
    post.published_at = datetime.now(UTC)
    post.published_by_id = current_user.id if current_user else None
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.post(
    "/{lead_id}/updates/{post_id}/unpublish",
    response_model=LeadUpdatePostResponse,
)
async def unpublish_update(
    lead_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadUpdatePostResponse:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    post = require_found(await _load_post(db, lead_id, post_id), "Update")
    post.published_at = None
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.delete(
    "/{lead_id}/updates/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_update(
    lead_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    post = await _load_post(db, lead_id, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Update niet gevonden")
    await db.delete(post)
    await db.flush()


# ---------------------------------------------------------------------------
# .eml download — Outlook-friendly editable draft
# ---------------------------------------------------------------------------


@router.get("/{lead_id}/updates/{post_id}/eml")
async def download_update_eml(
    lead_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> Response:
    """Stream a .eml that opens as an editable draft in Outlook (Windows)."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    post = require_found(await _load_post(db, lead_id, post_id), "Update")

    body_html = markdown_to_html(post.body_internal or "")
    eml_bytes = build_outlook_draft_eml(
        subject=post.mail_subject or post.titel or "",
        to=list(post.mail_to or []),
        cc=list(post.mail_cc or []),
        body_html=body_html,
    )
    safe_title = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in (post.titel or "update")
    )[:60]
    filename = f"update-{safe_title}.eml"
    return Response(
        content=eml_bytes,
        media_type="message/rfc822",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
