"""API routes for AI chat feature."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.schema.chat import (
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
)
from bouwmeester.services.chat_service import ChatService
from bouwmeester.services.llm import get_llm_service_for
from bouwmeester.services.llm.base import DataSensitivity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


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
