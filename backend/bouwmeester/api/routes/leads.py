"""API routes for leads (sales/intake funnel)."""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import (
    require_deleted,
    require_found,
    resolve_tag_to_link,
    validate_list,
)
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authority import (
    require_can_change_resource_role,
    require_can_grant_resource_role,
)
from bouwmeester.core.authz import require, requires
from bouwmeester.core.database import get_db
from bouwmeester.core.github_url import parse_github_url
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
    require_lead_read,
)
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.core.storage import (
    blob_available,
    blob_download,
    delete_blob,
    read_upload_content,
    store_upload,
    validate_upload,
)
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.github_link import GitHubLinkRepository
from bouwmeester.repositories.lead import LeadRepository, StageNotInColumnsError
from bouwmeester.repositories.lead_activity import LeadActivityRepository
from bouwmeester.schema.github_link import (
    GitHubLinkCreate,
    GitHubLinkResponse,
    GitHubLinkUpdate,
)
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
    LeadTimelineEvent,
    LeadTimelineResponse,
    LeadUpdate,
)
from bouwmeester.schema.notification import NotificationCreate
from bouwmeester.schema.tag import LeadTagCreate, LeadTagResponse
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/leads", tags=["leads"])

logger = logging.getLogger(__name__)


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


# Writes are decided by core.authz on the lead in the path.  Sub-records ask
# with their own permission ("lead_attachment:create") so the delegation
# table in core.authz applies; today that is write access on the lead.
_WRITE_LEAD = requires("lead:update", "lead", path_param="lead_id")


async def get_visible_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    init_ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> Lead:
    """Dependency for reads: the lead, or 404 when the caller does not see it.

    Same rule as the lists (``core.initiatief_context``).  Visibility never
    grants writing: writes go through ``core.authz``.
    """
    return await require_lead_read(db, perm_ctx, lead_id, init_ctx)


async def get_lead_or_404(db: AsyncSession, lead_id: UUID) -> Lead:
    """The lead after an authz decision (already in the identity map)."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead niet gevonden"
        )
    return lead


async def _require_can_place_lead(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    initiatief_id: UUID | None,
    eenheid_id: UUID | None,
) -> None:
    """Placing a lead (create, or move) needs rights where it will live.

    In an initiatief that is write access on the initiatief; a lead without
    one follows its eenheid, or the tenant-wide rule when it has neither.
    """
    if initiatief_id is not None:
        await require(db, perm_ctx, "lead:create", "initiatief", initiatief_id)
    else:
        await require(db, perm_ctx, "lead:create", "lead", eenheid_id=eenheid_id)


# ---------------------------------------------------------------------------
# Lead CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    current_user: OptionalUser,
    stage: str | None = Query(None, max_length=120),
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
    responses = validate_list(LeadResponse, leads)

    # Batch-load contact names for all leads
    if responses:
        lead_ids = [r.id for r in responses]
        contact_map = await repo.get_contact_names_batch(lead_ids)
        for r in responses:
            r.contact_names = contact_map.get(r.id, [])

    return responses


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> LeadResponse:
    """Create a new lead."""
    await _require_can_place_lead(
        db, perm_ctx, data.initiatief_id, data.organisatie_eenheid_id
    )
    author_id = current_user.id if current_user else None
    repo = LeadRepository(db)
    try:
        lead = await repo.create(data, author_id=author_id)
    except StageNotInColumnsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Onbekende stage '{exc.args[0]}' voor dit initiatief",
        )

    # Notify assignee (if any, and not self-assignment)
    if lead.assignee_id and lead.assignee_id != author_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=lead.assignee_id,
            type="lead_assigned",
            title=f"Je bent toegewezen aan lead: {lead.title}",
            message=f"Je bent toegewezen aan lead: {lead.title}",
            related_lead_id=lead.id,
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
    initiatief_id: UUID | None = Query(None),
) -> LeadMetricsResponse:
    """Get funnel metrics (counts per stage, stale leads).

    With `initiatief_id` the counts cover that initiatief only; the
    visibility filter still applies, so naming one you cannot see yields
    zeroes rather than its figures.
    """
    repo = LeadRepository(db)
    metrics = await repo.get_metrics(init_ctx=init_ctx, initiatief_id=initiatief_id)
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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> LeadResponse:
    """Merge source lead into target lead.

    Needs write access on both: the source's records all move to the target,
    so nothing is lost that a write on the source could not change anyway.
    """
    await require(db, perm_ctx, "lead:update", "lead", data.source_id)
    await require(db, perm_ctx, "lead:update", "lead", data.target_id)
    # The merge moves the source's contacts (opdrachtgever included) to the
    # target without the grant guard on purpose: every moved grant already
    # held on the source, and the caller holds lead:update on the target, so
    # nobody, the caller included, gets a right the caller could not use
    # already.  The guard would wrongly refuse moving the caller's own grant.
    source = await get_lead_or_404(db, data.source_id)
    target = await get_lead_or_404(db, data.target_id)
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

    # Build contacts from resource_permission
    from bouwmeester.repositories.resource_permission import (
        ResourcePermissionRepository,
    )

    rp_repo = ResourcePermissionRepository(db)
    rp_contacts = await rp_repo.list_for_resource("lead", lead_id)
    contacts = [
        LeadContactResponse(
            id=rp.id,
            person_id=rp.person_id,
            person_naam=rp.person.naam if rp.person else "",
            person_functie=rp.person.functie if rp.person else None,
            person_expertise=rp.person.expertise if rp.person else None,
            rol=rp.rol,
            created_at=rp.created_at,
        )
        for rp in rp_contacts
    ]

    response = LeadDetailResponse.model_validate(lead)
    response.contacts = contacts

    gh_repo = GitHubLinkRepository(db)
    gh_links = await gh_repo.list_for_scope(SCOPE_LEAD, lead_id)
    response.github_links = [
        GitHubLinkResponse.model_validate(link) for link in gh_links
    ]

    # Mark file-attachments whose files no longer exist in the store.
    # URL-attachments (soort='link') hebben geen pad — die blijven beschikbaar.
    pad_by_id = {a.id: a.pad for a in lead.attachments}
    for att in response.attachments:
        pad = pad_by_id.get(att.id)
        if att.soort == "file" and pad:
            att.bestand_beschikbaar = await blob_available(pad)
        else:
            att.bestand_beschikbaar = True

    return response


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(_WRITE_LEAD),
) -> LeadResponse:
    """Update a lead."""
    actor_id = current_user.id if current_user else None

    # Capture old state before update
    old_lead = await get_lead_or_404(db, lead_id)
    # Moving the lead to another initiatief or eenheid needs rights there too.
    fields = data.model_fields_set
    new_place = (
        data.initiatief_id if "initiatief_id" in fields else old_lead.initiatief_id,
        data.organisatie_eenheid_id
        if "organisatie_eenheid_id" in fields
        else old_lead.organisatie_eenheid_id,
    )
    if new_place != (old_lead.initiatief_id, old_lead.organisatie_eenheid_id):
        await _require_can_place_lead(db, perm_ctx, *new_place)
    old_assignee_id = old_lead.assignee_id
    old_stage = old_lead.stage

    repo = LeadRepository(db)
    try:
        lead = require_found(await repo.update(lead_id, data), "Lead")
    except StageNotInColumnsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Onbekende stage '{exc.args[0]}' voor dit initiatief",
        )

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
                related_lead_id=lead.id,
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
                related_lead_id=lead.id,
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
    _authz=Depends(requires("lead:delete", "lead", path_param="lead_id")),
) -> None:
    """Delete a lead permanently."""
    lead = await get_lead_or_404(db, lead_id)
    lead_title = lead.title

    # Clean up resource_permission rows (no FK cascade on polymorphic)
    from sqlalchemy import delete as sa_delete

    await db.execute(
        sa_delete(ResourcePermission).where(
            ResourcePermission.resource_type == "lead",
            ResourcePermission.resource_id == lead_id,
        )
    )
    await db.execute(
        sa_delete(GitHubLink).where(
            GitHubLink.scope_type == SCOPE_LEAD,
            GitHubLink.scope_id == lead_id,
        )
    )

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
    _authz=Depends(_WRITE_LEAD),
) -> LeadResponse:
    """Move a lead to a new stage."""
    author_id = current_user.id if current_user else None
    repo = LeadRepository(db)
    try:
        lead = require_found(
            await repo.move(lead_id, data.stage, author_id=author_id), "Lead"
        )
    except StageNotInColumnsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Onbekende stage '{exc.args[0]}' voor dit initiatief",
        )

    # Notify assignee about stage change
    if lead.assignee_id and lead.assignee_id != author_id:
        notif_svc = NotificationService(db)
        notification_data = NotificationCreate(
            person_id=lead.assignee_id,
            type="lead_stage_changed",
            title=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
            message=f"Lead '{lead.title}' is verplaatst naar {lead.stage}",
            related_lead_id=lead.id,
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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[LeadResponse]:
    """Reorder leads within a stage; needs write access on every lead."""
    lead_ids = list(dict.fromkeys(data.lead_ids))
    # Load all leads in one query so authz finds them in the identity map;
    # its per-request cache decides each initiatief only once.
    found = (await db.scalars(select(Lead).where(Lead.id.in_(lead_ids)))).all()
    if len(found) != len(lead_ids):
        raise HTTPException(status_code=404, detail="Lead niet gevonden")
    for lead_id in lead_ids:
        await require(db, perm_ctx, "lead:update", "lead", lead_id)
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
    _authz=Depends(requires("lead_activity:create", "lead", path_param="lead_id")),
) -> LeadActivityResponse:
    """Add an activity (note, meeting, call, email) to a lead."""
    # Verify lead exists and get it for notification
    lead = await get_lead_or_404(db, lead_id)

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
            related_lead_id=lead.id,
        )
        await notif_svc.send(notification_data)

    await sync_and_notify_mentions(
        db,
        "lead_activity",
        activity.id,
        data.content,
        f"lead '{lead.title}'",
        sender_id=author_id,
        source_lead_id=lead_id,
        exclude_person_id=lead.assignee_id,
    )

    await log_activity(
        db,
        current_user,
        None,
        "lead_activity.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "activity_type": data.activity_type.value,
        },
    )

    return LeadActivityResponse.model_validate(activity)


@router.get("/{lead_id}/activities", response_model=list[LeadActivityResponse])
async def list_activities(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _visible: Lead = Depends(get_visible_lead),
) -> list[LeadActivityResponse]:
    """List activities for a lead, newest first."""
    repo = LeadActivityRepository(db)
    activities = await repo.get_by_lead(lead_id)
    return validate_list(LeadActivityResponse, activities)


@router.delete(
    "/{lead_id}/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_activity(
    lead_id: UUID,
    activity_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(
        requires("lead_activity:delete", "lead", path_param="lead_id")
    ),
) -> None:
    """Delete a lead activity.

    The author may, while they can still write the lead.  Someone else's
    activity needs the right to delete the lead itself.
    """
    lead = await get_lead_or_404(db, lead_id)

    activity = await db.get(LeadActivity, activity_id)
    if activity is None or activity.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Activiteit niet gevonden")

    if activity.author_id is None or activity.author_id != perm_ctx.person_id:
        await require(db, perm_ctx, "lead:delete", "lead", lead_id)

    activity_type = activity.activity_type
    await db.delete(activity)

    await log_activity(
        db,
        current_user,
        None,
        "lead_activity.deleted",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "activity_id": str(activity_id),
            "activity_type": activity_type,
        },
    )


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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> LeadContactResponse:
    """Link a person as contact to a lead.

    A contact is a grant (``opdrachtgever`` gives ``lead:update``), so it
    goes through the grant guard rather than plain write access.
    """
    lead = await get_lead_or_404(db, lead_id)
    await require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type="lead",
        resource_id=lead_id,
        rol=data.rol,
        target_person_id=data.person_id,
    )

    contact = ResourcePermission(
        person_id=data.person_id,
        resource_type="lead",
        resource_id=lead_id,
        rol=data.rol,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact, attribute_names=["person"])

    # Notify the contact person (unless they added themselves)
    actor_id = current_user.id if current_user else None
    if data.person_id != actor_id:
        notif_svc = NotificationService(db)
        msg = f"Je bent toegevoegd als externe contactpersoon aan lead: {lead.title}"
        notification_data = NotificationCreate(
            person_id=data.person_id,
            type="lead_contact_added",
            title=msg,
            message=msg,
            related_lead_id=lead_id,
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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    """Remove a contact link from a lead (leaving it yourself is always allowed)."""
    lead = await get_lead_or_404(db, lead_id)

    result = await db.execute(
        select(ResourcePermission).where(
            ResourcePermission.id == contact_id,
            ResourcePermission.resource_type == "lead",
            ResourcePermission.resource_id == lead_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await require_can_change_resource_role(db, perm_ctx, contact, new_rol=None)
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
    _authz=Depends(_WRITE_LEAD),
) -> LeadNodeResponse:
    """Link a corpus node to a lead."""
    lead = await get_lead_or_404(db, lead_id)
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
    _authz=Depends(_WRITE_LEAD),
) -> None:
    """Remove a corpus node link from a lead."""
    lead = await get_lead_or_404(db, lead_id)
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
    _visible: Lead = Depends(get_visible_lead),
) -> list[LeadTagResponse]:
    """List all tags applied to a lead."""
    from bouwmeester.repositories.tag import TagRepository

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
    perm_ctx: PermissionContext = Depends(_WRITE_LEAD),
) -> LeadTagResponse:
    """Add a tag to a lead; a new tag_name also needs ``tag:create``."""
    from bouwmeester.repositories.tag import TagRepository

    lead = await get_lead_or_404(db, lead_id)
    tag_id = await resolve_tag_to_link(
        db, perm_ctx, tag_id=data.tag_id, tag_name=data.tag_name
    )
    tag_repo = TagRepository(db)
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
    _authz=Depends(_WRITE_LEAD),
) -> None:
    """Remove a tag from a lead."""
    from bouwmeester.repositories.tag import TagRepository

    lead = await get_lead_or_404(db, lead_id)
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
    _authz=Depends(requires("lead_attachment:create", "lead", path_param="lead_id")),
) -> LeadAttachmentResponse:
    """Upload a file attachment to a lead."""
    lead = await get_lead_or_404(db, lead_id)

    content_type = file.content_type or "application/octet-stream"
    content = await read_upload_content(file)
    validate_upload(content, content_type)

    filename, relative_path = await store_upload(
        content,
        file.filename or "bijlage",
        prefix="leads",
        item_id=lead_id,
        content_type=content_type,
    )
    # store_upload returns the path without its prefix; lead_attachment.pad
    # has always kept the "leads/" in it.
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
    _visible: Lead = Depends(get_visible_lead),
) -> Response:
    """Download a lead attachment."""
    result = await db.execute(
        select(LeadAttachment).where(
            LeadAttachment.id == attachment_id,
            LeadAttachment.lead_id == lead_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Bijlage niet gevonden")

    if not attachment.pad:
        raise HTTPException(status_code=404, detail="Bestand niet gevonden")
    return await blob_download(
        attachment.pad,
        attachment.bestandsnaam,
        attachment.content_type or "application/octet-stream",
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
    _authz=Depends(requires("lead_attachment:delete", "lead", path_param="lead_id")),
) -> None:
    """Delete a lead attachment (DB record and stored file)."""
    lead = await get_lead_or_404(db, lead_id)
    result = await db.execute(
        select(LeadAttachment).where(
            LeadAttachment.id == attachment_id,
            LeadAttachment.lead_id == lead_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Bijlage niet gevonden")

    attachment_pad = attachment.pad
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

    if attachment_pad:
        await delete_blob(attachment_pad)


# ---------------------------------------------------------------------------
# GitHub links
# ---------------------------------------------------------------------------


@router.get(
    "/{lead_id}/github-links",
    response_model=list[GitHubLinkResponse],
)
async def list_github_links(
    lead_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _visible: Lead = Depends(get_visible_lead),
) -> list[GitHubLinkResponse]:
    repo = GitHubLinkRepository(db)
    links = await repo.list_for_scope(SCOPE_LEAD, lead_id)
    return [GitHubLinkResponse.model_validate(link) for link in links]


@router.post(
    "/{lead_id}/github-links",
    response_model=GitHubLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_github_link(
    lead_id: UUID,
    payload: GitHubLinkCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("github_link:create", "lead", path_param="lead_id")),
) -> GitHubLinkResponse:
    lead = await get_lead_or_404(db, lead_id)

    parsed = parse_github_url(payload.url)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail="Ongeldige GitHub-URL",
        )

    normalized_url = payload.url.strip()
    repo = GitHubLinkRepository(db)
    existing = await repo.get_by_scope_url(SCOPE_LEAD, lead_id, normalized_url)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Deze GitHub-link is al gekoppeld aan deze lead",
        )

    created_by_id = current_user.id if current_user else None

    link = await repo.create(
        scope_type=SCOPE_LEAD,
        scope_id=lead_id,
        url=normalized_url,
        link_type=parsed.link_type.value,
        owner=parsed.owner,
        repo=parsed.repo,
        ref=parsed.ref,
        title=payload.title,
        created_by_id=created_by_id,
    )

    await log_activity(
        db,
        current_user,
        None,
        "lead_github_link.added",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "url": normalized_url,
            "link_type": parsed.link_type.value,
            "owner_repo": f"{parsed.owner}/{parsed.repo}",
        },
    )

    return GitHubLinkResponse.model_validate(link)


@router.patch(
    "/{lead_id}/github-links/{link_id}",
    response_model=GitHubLinkResponse,
)
async def update_github_link(
    lead_id: UUID,
    link_id: UUID,
    payload: GitHubLinkUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("github_link:update", "lead", path_param="lead_id")),
) -> GitHubLinkResponse:
    repo = GitHubLinkRepository(db)
    link = await repo.get(link_id)
    if link is None or link.scope_type != SCOPE_LEAD or link.scope_id != lead_id:
        raise HTTPException(status_code=404, detail="GitHub-link niet gevonden")

    updated = await repo.update_title(link, payload.title)
    return GitHubLinkResponse.model_validate(updated)


@router.delete(
    "/{lead_id}/github-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_github_link(
    lead_id: UUID,
    link_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(requires("github_link:delete", "lead", path_param="lead_id")),
) -> None:
    lead = await get_lead_or_404(db, lead_id)

    repo = GitHubLinkRepository(db)
    link = await repo.get(link_id)
    if link is None or link.scope_type != SCOPE_LEAD or link.scope_id != lead_id:
        raise HTTPException(status_code=404, detail="GitHub-link niet gevonden")

    url = link.url
    owner_repo = f"{link.owner}/{link.repo}"
    await repo.delete(link)

    await log_activity(
        db,
        current_user,
        None,
        "lead_github_link.deleted",
        details={
            "lead_id": str(lead_id),
            "lead_title": lead.title,
            "url": url,
            "owner_repo": owner_repo,
        },
    )


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
