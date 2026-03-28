"""API routes for leads (sales/intake funnel)."""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found, validate_list
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.core.storage import (
    ensure_bijlagen_dir,
    read_upload_content,
    safe_resolve_or_400,
    sanitize_download_filename,
    validate_upload,
    write_upload_to_disk,
)
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_contact import LeadContact
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.repositories.lead import LeadRepository
from bouwmeester.repositories.lead_activity import LeadActivityRepository
from bouwmeester.schema.lead import (
    LeadActivityCreate,
    LeadActivityResponse,
    LeadAttachmentResponse,
    LeadContactCreate,
    LeadContactResponse,
    LeadCreate,
    LeadDetailResponse,
    LeadMergeRequest,
    LeadMetricsResponse,
    LeadMove,
    LeadNodeCreate,
    LeadNodeResponse,
    LeadParseResult,
    LeadReorder,
    LeadResponse,
    LeadStage,
    LeadTimelineEvent,
    LeadTimelineResponse,
    LeadUpdate,
)
from bouwmeester.schema.notification import NotificationCreate
from bouwmeester.schema.tag import LeadTagCreate, LeadTagResponse, TagCreate
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/leads", tags=["leads"])

logger = logging.getLogger(__name__)

LEADS_BIJLAGEN_ROOT = ensure_bijlagen_dir()


def _robust_parse_json(text: str) -> dict:
    """Parse JSON from LLM response with aggressive cleanup."""
    import json
    import re

    # Strip markdown code blocks
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()

    # Fix trailing commas
    text = re.sub(r",\s*([}\]])", r"\1", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first { ... } block (handles preamble text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidate = match.group()
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Give up with clear error
    raise json.JSONDecodeError(
        f"Could not parse LLM response as JSON. Raw text: {text[:200]}", text, 0
    )


def _check_lead_access(lead: Lead, init_ctx: InitiatiefContext) -> None:
    """Raise 404 if the user cannot access this lead's initiatief."""
    if init_ctx.is_admin:
        return
    if not init_ctx.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead niet gevonden"
        )
    # Leads without initiatief are visible to all authenticated users
    # (migration period: allows assigning them to an initiatief)
    if (
        lead.initiatief_id is not None
        and lead.initiatief_id not in init_ctx.visible_initiatief_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead niet gevonden"
        )


def _check_initiatief_access(
    initiatief_id: UUID | None, init_ctx: InitiatiefContext
) -> None:
    """Raise 403 if user cannot create resources in this initiatief."""
    if init_ctx.is_admin:
        return
    if initiatief_id is None:
        return
    if initiatief_id not in init_ctx.visible_initiatief_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geen toegang tot dit initiatief",
        )


# ---------------------------------------------------------------------------
# Lead CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    current_user: OptionalUser,
    stage: LeadStage | None = Query(None),
    tag: str | None = Query(None),
    assignee_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    next_action_filter: str | None = Query(None),
    sort_by: str | None = Query(None),
    initiatief_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadResponse]:
    """List leads with optional filters."""
    repo = LeadRepository(db)
    leads = await repo.get_all(
        skip=skip,
        limit=limit,
        stage=stage,
        tag=tag,
        assignee_id=assignee_id,
        init_ctx=init_ctx,
        date_from=date_from,
        date_to=date_to,
        next_action_filter=next_action_filter,
        sort_by=sort_by,
        initiatief_id=initiatief_id,
    )
    return validate_list(LeadResponse, leads)


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadResponse:
    """Create a new lead."""
    _check_initiatief_access(data.initiatief_id, init_ctx)
    author_id = current_user.id if current_user else None
    repo = LeadRepository(db)
    lead = await repo.create(data, author_id=author_id)

    # Notify assignee (if any, and not self-assignment)
    if lead.assignee_id and lead.assignee_id != author_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=lead.assignee_id,
            type="lead_assigned",
            title=f"Je bent toegewezen aan lead: {lead.title}",
            message=f"Je bent toegewezen aan lead: {lead.title}",
        )
        await notif_svc.send(notification_data)

    await log_activity(
        db,
        current_user,
        None,
        "lead.created",
        details={"lead_id": str(lead.id), "title": lead.title},
    )

    return LeadResponse.model_validate(lead)


@router.get("/metrics", response_model=LeadMetricsResponse)
async def get_metrics(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadMetricsResponse:
    """Get funnel metrics (counts per stage, stale leads)."""
    repo = LeadRepository(db)
    metrics = await repo.get_metrics(init_ctx=init_ctx)
    return LeadMetricsResponse(**metrics)


@router.get("/timeline", response_model=LeadTimelineResponse)
async def get_timeline(
    current_user: OptionalUser,
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
    stage: str | None = Query(None),
    assignee_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    initiatief_id: UUID | None = Query(None),
    limit: int = Query(500, le=1000),
    db: AsyncSession = Depends(get_db),
) -> LeadTimelineResponse:
    """Get a chronological timeline of all lead events."""
    repo = LeadRepository(db)
    events_data = await repo.get_timeline(
        init_ctx=init_ctx,
        stage=stage,
        assignee_id=assignee_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        initiatief_id=initiatief_id,
    )

    events = [LeadTimelineEvent(**e) for e in events_data]

    timestamps = [e.timestamp for e in events]
    return LeadTimelineResponse(
        events=events,
        total=len(events),
        earliest=min(timestamps) if timestamps else None,
        latest=max(timestamps) if timestamps else None,
    )


@router.get("/check-duplicates", response_model=list[LeadResponse])
async def check_duplicates(
    title: str = Query(...),
    organization: str | None = Query(None),
    current_user: OptionalUser = None,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadResponse]:
    """Find leads with similar title or organization (trigram similarity)."""
    repo = LeadRepository(db)
    similar = await repo.find_similar(title, organization, init_ctx=init_ctx)
    return validate_list(LeadResponse, similar)


@router.post("/merge", response_model=LeadResponse)
async def merge_leads(
    data: LeadMergeRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadResponse:
    """Merge source lead into target lead."""
    source = await db.get(Lead, data.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Bronlead niet gevonden")
    _check_lead_access(source, init_ctx)
    target = await db.get(Lead, data.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Doellead niet gevonden")
    _check_lead_access(target, init_ctx)
    if source.initiatief_id != target.initiatief_id:
        raise HTTPException(
            status_code=400,
            detail="Leads van verschillende initiatieven kunnen niet"
            " worden samengevoegd",
        )
    repo = LeadRepository(db)
    result = require_found(await repo.merge(data.source_id, data.target_id), "Lead")

    await log_activity(
        db,
        current_user,
        None,
        "lead.merged",
        details={
            "source_id": str(data.source_id),
            "target_id": str(data.target_id),
            "title": result.title,
        },
    )

    return LeadResponse.model_validate(result)


@router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadDetailResponse:
    """Get lead detail including activities, contacts, and linked nodes."""
    repo = LeadRepository(db)
    lead = require_found(await repo.get_detail(lead_id, init_ctx=init_ctx), "Lead")
    return LeadDetailResponse.model_validate(lead)


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadResponse:
    """Update a lead."""
    actor_id = current_user.id if current_user else None

    # Capture old state before update
    old_lead = await db.get(Lead, lead_id)
    if old_lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(old_lead, init_ctx)
    old_assignee_id = old_lead.assignee_id
    old_stage = old_lead.stage

    repo = LeadRepository(db)
    lead = require_found(await repo.update(lead_id, data), "Lead")

    notif_svc = NotificationService(db)

    # Notify on assignee change
    new_assignee_id = lead.assignee_id
    if new_assignee_id and new_assignee_id != old_assignee_id:
        # Don't notify if actor is the new assignee (self-assignment)
        if new_assignee_id != actor_id:
            notification_data = NotificationCreate(
                person_id=new_assignee_id,
                type="lead_assigned",
                title=f"Je bent toegewezen aan lead: {lead.title}",
                message=f"Je bent toegewezen aan lead: {lead.title}",
            )
            await notif_svc.send(notification_data)

    # Notify on stage change
    if lead.stage != old_stage and lead.assignee_id:
        # Don't notify if actor is the assignee
        if lead.assignee_id != actor_id:
            notification_data = NotificationCreate(
                person_id=lead.assignee_id,
                type="lead_stage_changed",
                title=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
                message=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
            )
            await notif_svc.send(notification_data)

    await log_activity(
        db,
        current_user,
        None,
        "lead.updated",
        details={"lead_id": str(lead.id), "title": lead.title},
    )

    return LeadResponse.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    """Delete a lead permanently."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    lead_title = lead.title
    repo = LeadRepository(db)
    require_deleted(await repo.delete(lead_id), "Lead")

    await log_activity(
        db,
        current_user,
        None,
        "lead.deleted",
        details={"lead_id": str(lead_id), "title": lead_title},
    )


@router.post("/{lead_id}/move", response_model=LeadResponse)
async def move_lead(
    lead_id: UUID,
    data: LeadMove,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadResponse:
    """Move a lead to a new stage."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    author_id = current_user.id if current_user else None
    repo = LeadRepository(db)
    lead = require_found(
        await repo.move(lead_id, data.stage, author_id=author_id), "Lead"
    )

    # Notify assignee about stage change
    if lead.assignee_id and lead.assignee_id != author_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=lead.assignee_id,
            type="lead_stage_changed",
            title=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
            message=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
        )
        await notif_svc.send(notification_data)

    await log_activity(
        db,
        current_user,
        None,
        "lead.moved",
        details={"lead_id": str(lead.id), "title": lead.title, "stage": lead.stage},
    )

    return LeadResponse.model_validate(lead)


@router.post("/reorder", response_model=list[LeadResponse])
async def reorder_leads(
    data: LeadReorder,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadResponse]:
    """Reorder leads within a stage."""
    # Verify all leads are accessible to the user
    for lead_id in data.lead_ids:
        lead = await db.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead niet gevonden")
        _check_lead_access(lead, init_ctx)
    repo = LeadRepository(db)
    leads = await repo.reorder(data.lead_ids, data.stage)
    return validate_list(LeadResponse, leads)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


@router.post(
    "/{lead_id}/activities",
    response_model=LeadActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_activity(
    lead_id: UUID,
    data: LeadActivityCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadActivityResponse:
    """Add an activity (note, meeting, call, email) to a lead."""
    # Verify lead exists and get it for notification
    lead_repo = LeadRepository(db)
    lead = require_found(await lead_repo.get(lead_id), "Lead")
    _check_lead_access(lead, init_ctx)

    author_id = current_user.id if current_user else None
    repo = LeadActivityRepository(db)
    activity = await repo.create(lead_id, data, author_id=author_id)

    # Notify assignee about new activity (if author is not the assignee)
    if lead.assignee_id and lead.assignee_id != author_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=lead.assignee_id,
            type="lead_activity_added",
            title=f"Nieuwe notitie op lead '{lead.title}'",
            message=f"Nieuwe notitie op lead '{lead.title}'",
        )
        await notif_svc.send(notification_data)

    await log_activity(
        db,
        current_user,
        None,
        "lead_activity.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "activity_type": data.type,
        },
    )

    return LeadActivityResponse.model_validate(activity)


@router.get("/{lead_id}/activities", response_model=list[LeadActivityResponse])
async def list_activities(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadActivityResponse]:
    """List activities for a lead, newest first."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    repo = LeadActivityRepository(db)
    activities = await repo.get_by_lead(lead_id)
    return validate_list(LeadActivityResponse, activities)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


@router.post(
    "/{lead_id}/contacts",
    response_model=LeadContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact(
    lead_id: UUID,
    data: LeadContactCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadContactResponse:
    """Link a person as contact to a lead."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    contact = LeadContact(
        lead_id=lead_id,
        person_id=data.person_id,
        rol=data.rol,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact, attribute_names=["person"])

    # Notify the contact person (unless they added themselves)
    actor_id = current_user.id if current_user else None
    if data.person_id != actor_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=data.person_id,
            type="lead_contact_added",
            title=f"Je bent toegevoegd als contactpersoon aan lead: {lead.title}",
            message=f"Je bent toegevoegd als contactpersoon aan lead: {lead.title}",
        )
        await notif_svc.send(notification_data)

    await log_activity(
        db,
        current_user,
        None,
        "lead_contact.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "person_id": str(data.person_id),
        },
    )

    return LeadContactResponse.model_validate(contact)


@router.delete(
    "/{lead_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_contact(
    lead_id: UUID,
    contact_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    """Remove a contact link from a lead."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    result = await db.execute(
        select(LeadContact).where(
            LeadContact.id == contact_id,
            LeadContact.lead_id == lead_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.flush()

    await log_activity(
        db,
        current_user,
        None,
        "lead_contact.removed",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "contact_id": str(contact_id),
        },
    )


# ---------------------------------------------------------------------------
# Linked corpus nodes
# ---------------------------------------------------------------------------


@router.post(
    "/{lead_id}/nodes",
    response_model=LeadNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_node(
    lead_id: UUID,
    data: LeadNodeCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadNodeResponse:
    """Link a corpus node to a lead."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    link = LeadNode(
        lead_id=lead_id,
        node_id=data.node_id,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link, attribute_names=["node"])

    await log_activity(
        db,
        current_user,
        None,
        "lead_node.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "node_id": str(data.node_id),
        },
    )

    return LeadNodeResponse.model_validate(link)


@router.delete(
    "/{lead_id}/nodes/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_node(
    lead_id: UUID,
    link_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    """Remove a corpus node link from a lead."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    result = await db.execute(
        select(LeadNode).where(
            LeadNode.id == link_id,
            LeadNode.lead_id == lead_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Node link not found")
    await db.delete(link)
    await db.flush()

    await log_activity(
        db,
        current_user,
        None,
        "lead_node.removed",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "link_id": str(link_id),
        },
    )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.get("/{lead_id}/tags", response_model=list[LeadTagResponse])
async def get_lead_tags(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[LeadTagResponse]:
    """List all tags applied to a lead."""
    from bouwmeester.repositories.tag import TagRepository

    repo = LeadRepository(db)
    lead = require_found(await repo.get(lead_id), "Lead")
    _check_lead_access(lead, init_ctx)

    tag_repo = TagRepository(db)
    lead_tags = await tag_repo.get_by_lead(lead_id)
    return [LeadTagResponse.model_validate(lt) for lt in lead_tags]


@router.post(
    "/{lead_id}/tags",
    response_model=LeadTagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_tag_to_lead(
    lead_id: UUID,
    data: LeadTagCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadTagResponse:
    """Add a tag to a lead.

    Creates the tag if tag_name is given and it doesn't exist.
    """
    from bouwmeester.repositories.tag import TagRepository

    repo = LeadRepository(db)
    lead = require_found(await repo.get(lead_id), "Lead")
    _check_lead_access(lead, init_ctx)

    tag_repo = TagRepository(db)

    if data.tag_name and not data.tag_id:
        existing = await tag_repo.get_by_name(data.tag_name)
        if existing:
            tag_id = existing.id
        else:
            new_tag = await tag_repo.create(TagCreate(name=data.tag_name))
            tag_id = new_tag.id
    elif data.tag_id:
        tag_id = data.tag_id
    else:
        raise HTTPException(status_code=400, detail="Provide tag_id or tag_name")

    lead_tag = await tag_repo.add_tag_to_lead(lead_id, tag_id)

    await log_activity(
        db,
        current_user,
        None,
        "lead_tag.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "tag_id": str(tag_id),
        },
    )

    return LeadTagResponse.model_validate(lead_tag)


@router.delete(
    "/{lead_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_tag_from_lead(
    lead_id: UUID,
    tag_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    """Remove a tag from a lead."""
    from bouwmeester.repositories.tag import TagRepository

    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    tag_repo = TagRepository(db)
    require_deleted(await tag_repo.remove_tag_from_lead(lead_id, tag_id), "Tag link")

    await log_activity(
        db,
        current_user,
        None,
        "lead_tag.removed",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "tag_id": str(tag_id),
        },
    )


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


@router.post(
    "/{lead_id}/attachments",
    response_model=LeadAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    lead_id: UUID,
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> LeadAttachmentResponse:
    """Upload a file attachment to a lead."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)

    content_type = file.content_type or "application/octet-stream"
    content = await read_upload_content(file)
    validate_upload(content, content_type)

    leads_dir = LEADS_BIJLAGEN_ROOT / "leads"
    filename, relative_path, _ = write_upload_to_disk(
        content, file.filename or "bijlage", leads_dir, item_id=lead_id
    )
    # Prefix with "leads/" since write_upload_to_disk returns path relative
    # to leads_dir, but DB stores path relative to LEADS_BIJLAGEN_ROOT.
    relative_path = f"leads/{relative_path}"

    attachment = LeadAttachment(
        lead_id=lead_id,
        bestandsnaam=filename,
        content_type=content_type,
        bestandsgrootte=len(content),
        pad=relative_path,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)

    await log_activity(
        db,
        current_user,
        None,
        "lead_attachment.uploaded",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "filename": filename,
        },
    )

    return LeadAttachmentResponse.model_validate(attachment)


@router.get("/{lead_id}/attachments/{attachment_id}/download")
async def download_attachment(
    lead_id: UUID,
    attachment_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> FileResponse:
    """Download a lead attachment."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    result = await db.execute(
        select(LeadAttachment).where(
            LeadAttachment.id == attachment_id,
            LeadAttachment.lead_id == lead_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Bijlage niet gevonden")

    file_path = safe_resolve_or_400(LEADS_BIJLAGEN_ROOT, attachment.pad)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Bestand niet gevonden op disk")

    return FileResponse(
        path=str(file_path),
        filename=sanitize_download_filename(attachment.bestandsnaam),
        media_type="application/octet-stream",
    )


@router.delete(
    "/{lead_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(
    lead_id: UUID,
    attachment_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> None:
    """Delete a lead attachment (DB record and file on disk)."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    _check_lead_access(lead, init_ctx)
    result = await db.execute(
        select(LeadAttachment).where(
            LeadAttachment.id == attachment_id,
            LeadAttachment.lead_id == lead_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Bijlage niet gevonden")

    file_path = safe_resolve_or_400(LEADS_BIJLAGEN_ROOT, attachment.pad)
    attachment_naam = attachment.bestandsnaam
    await db.delete(attachment)

    await log_activity(
        db,
        current_user,
        None,
        "lead_attachment.deleted",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "filename": attachment_naam,
        },
    )

    if file_path.exists():
        file_path.unlink()


# ---------------------------------------------------------------------------
# AI parse intake
# ---------------------------------------------------------------------------


@router.post("/parse-intake", response_model=LeadParseResult)
async def parse_intake(
    current_user: OptionalUser,
    raw_text: str | None = Form(None),
    files: list[UploadFile] | None = None,
    db: AsyncSession = Depends(get_db),
) -> LeadParseResult:
    """Parse raw intake text/images using AI to extract lead data."""
    import base64

    from bouwmeester.services.llm.factory import get_llm_service
    from bouwmeester.services.llm.prompts import build_lead_intake_prompt

    # Collect text and images separately
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
            else:
                # Try to decode as text
                try:
                    text_parts.append(content_bytes.decode("utf-8", errors="replace"))
                except Exception:
                    pass

    if not text_parts and not image_parts:
        raise HTTPException(
            status_code=400,
            detail="Geen tekst of afbeelding opgegeven.",
        )

    llm = await get_llm_service(db)
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="Geen LLM-service beschikbaar.",
        )

    # Fetch existing tag names so VLAM can prefer them
    from bouwmeester.models.tag import Tag

    tag_result = await db.execute(select(Tag.name).order_by(Tag.name))
    existing_tag_names = [row[0] for row in tag_result.all()]

    combined_text = "\n\n".join(text_parts).strip()
    prompt = build_lead_intake_prompt(
        combined_text or "(zie afbeelding)",
        existing_tags=existing_tag_names,
    )

    try:
        if image_parts:
            # Use vision-style multimodal message with text + images
            # Use shorter tag list for vision to stay within token limits
            shorter_prompt = build_lead_intake_prompt(
                combined_text or "(zie afbeelding)",
                existing_tags=existing_tag_names[:50],
            )
            content: list[dict] = [{"type": "text", "text": shorter_prompt}]
            content.extend(image_parts)
            response = await llm._client.chat.completions.create(
                model=llm._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            response_text = response.choices[0].message.content or ""
        else:
            response_text = await llm._complete(prompt)

        logger.warning(
            "LLM raw response (%d chars): %s", len(response_text), response_text[:1500]
        )
        parsed = _robust_parse_json(response_text)
        return LeadParseResult(
            title=parsed.get("title"),
            organization=parsed.get("organization"),
            description=parsed.get("description"),
            contact_name=parsed.get("contact_name"),
            contact_email=parsed.get("contact_email"),
            contact_phone=parsed.get("contact_phone"),
            original_date=parsed.get("original_date"),
            suggested_tags=parsed.get("suggested_tags", []),
            addressed_to=parsed.get("addressed_to"),
        )
    except Exception:
        logger.exception("Failed to parse intake text with LLM")
        raise HTTPException(
            status_code=500,
            detail="Fout bij het verwerken van de intake-tekst.",
        )
