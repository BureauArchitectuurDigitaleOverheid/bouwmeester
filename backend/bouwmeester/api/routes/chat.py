"""API routes for AI chat feature."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.storage import (
    bijlagen_root,
    safe_resolve_or_400,
    verify_content_type,
)
from bouwmeester.models.chat_attachment import ChatAttachment
from bouwmeester.schema.chat import (
    ChatAttachmentResponse,
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatConversationHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
)
from bouwmeester.services.chat_service import ChatService
from bouwmeester.services.llm import get_llm_service_for
from bouwmeester.services.llm.base import DataSensitivity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


CHAT_BIJLAGEN_ROOT = bijlagen_root() / "chat"
try:
    CHAT_BIJLAGEN_ROOT.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # May fail in CI/test

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}


def _safe_path(relative: str) -> Path:
    """Resolve a relative path under CHAT_BIJLAGEN_ROOT, guarding against traversal."""
    return safe_resolve_or_400(CHAT_BIJLAGEN_ROOT, relative)


@router.post(
    "/upload",
    response_model=ChatAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_chat_attachment(
    file: UploadFile,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ChatAttachmentResponse:
    """Upload a file for use in chat messages."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ongeldig bestandstype: {content_type}. "
                "Toegestaan: PDF, Word, ODT, TXT, PNG, JPEG, GIF, WebP."
            ),
        )

    # Read in chunks to enforce size limit
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(8192):
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Bestand te groot. Maximum is {max_mb} MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Verify that file magic bytes match the claimed content type
    if not verify_content_type(content, content_type):
        raise HTTPException(
            status_code=400,
            detail="Bestandsinhoud komt niet overeen met het opgegeven bestandstype.",
        )

    # Sanitize filename
    raw_name = file.filename or "bijlage"
    filename = Path(raw_name).name or "bijlage"

    attachment_id = uuid.uuid4()
    safe_name = f"{attachment_id.hex}_{filename}"

    # Write to disk
    dir_path = CHAT_BIJLAGEN_ROOT / str(attachment_id)
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / safe_name
        file_path.write_bytes(content)
    except OSError:
        logger.exception("Failed to write chat attachment to %s", dir_path)
        raise HTTPException(
            status_code=500,
            detail="Kan bestand niet opslaan.",
        )

    relative_path = f"{attachment_id}/{safe_name}"
    person_id = current_user.id if current_user else None

    attachment = ChatAttachment(
        id=attachment_id,
        person_id=person_id,
        bestandsnaam=filename,
        content_type=content_type,
        bestandsgrootte=len(content),
        pad=relative_path,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)

    return ChatAttachmentResponse(
        id=str(attachment.id),
        bestandsnaam=attachment.bestandsnaam,
        content_type=attachment.content_type,
        bestandsgrootte=attachment.bestandsgrootte,
    )


@router.get("/attachments/{attachment_id}/preview")
async def preview_chat_attachment(
    attachment_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve a chat attachment for preview/thumbnail."""
    stmt = select(ChatAttachment).where(ChatAttachment.id == attachment_id)
    # Scope access: authenticated users see own + unowned attachments;
    # unauthenticated users see only unowned attachments.
    if current_user:
        stmt = stmt.where(
            ChatAttachment.person_id.in_([current_user.id])
            | ChatAttachment.person_id.is_(None)
        )
    else:
        stmt = stmt.where(ChatAttachment.person_id.is_(None))
    result = await db.execute(stmt)
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(status_code=404, detail="Bijlage niet gevonden")

    file_path = _safe_path(attachment.pad)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Bestand niet gevonden op disk")

    return FileResponse(
        path=str(file_path),
        media_type=attachment.content_type,
        filename=attachment.bestandsnaam,
    )


@router.get("/{conversation_id}", response_model=ChatConversationHistoryResponse)
async def get_chat_history(
    conversation_id: str,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ChatConversationHistoryResponse:
    """Return the full message history for a conversation."""
    person_id = current_user.id if current_user else None
    chat = ChatService(llm=None, db=db, person_id=person_id)  # type: ignore[arg-type]
    try:
        cid, messages = await chat.get_history(conversation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversatie niet gevonden")
    return ChatConversationHistoryResponse(
        conversation_id=cid,
        messages=messages,
    )


@router.post("", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Send a chat message and receive a response with optional tool actions."""
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        return ChatResponse(
            conversation_id=request.conversation_id or "",
            message=ChatMessage(
                role="assistant",
                content=(
                    "De AI-assistent is momenteel niet"
                    " beschikbaar. Configureer een"
                    " LLM-provider in de beheerinstellingen."
                ),
            ),
            available=False,
        )

    person_id = current_user.id if current_user else None
    chat = ChatService(service, db, person_id=person_id)
    context = request.context.model_dump() if request.context else None
    conversation_id, message = await chat.send_message(
        message=request.message,
        conversation_id=request.conversation_id,
        context=context,
        attachment_ids=request.attachment_ids,
    )
    return ChatResponse(conversation_id=conversation_id, message=message)


@router.post("/confirm", response_model=ChatConfirmResponse)
async def confirm_chat_action(
    request: ChatConfirmRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> ChatConfirmResponse:
    """Confirm or reject a pending write action from the chat."""
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        return ChatConfirmResponse(
            message=ChatMessage(
                role="assistant",
                content="De AI-assistent is niet beschikbaar.",
            ),
            success=False,
        )

    person_id = current_user.id if current_user else None
    chat = ChatService(service, db, person_id=person_id)
    message = await chat.confirm_action(
        conversation_id=request.conversation_id,
        action_id=request.action_id,
        approved=request.approved,
    )
    return ChatConfirmResponse(message=message, success=True)
