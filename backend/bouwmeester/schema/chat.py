"""Pydantic schemas for AI chat feature."""

from pydantic import BaseModel, ConfigDict, Field


class ChatMention(BaseModel):
    """An entity referenced via @ or # in the chat message."""

    id: str
    label: str
    type: str  # "person" | "organisatie" | "node" | "task" | "tag"


class ChatContext(BaseModel):
    """Current UI context sent with each chat message."""

    page: str = ""
    node_id: str | None = None
    node_title: str | None = None
    node_type: str | None = None
    node_description: str | None = None
    task_id: str | None = None
    task_title: str | None = None
    mentions: list[ChatMention] = []


class ChatAttachmentResponse(BaseModel):
    """Metadata for an uploaded chat attachment."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    bestandsnaam: str
    content_type: str
    bestandsgrootte: int


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""

    message: str = Field(max_length=2000)
    conversation_id: str | None = None
    context: ChatContext | None = None
    attachment_ids: list[str] = []


class ChatAction(BaseModel):
    """A completed tool action taken by the assistant."""

    tool_name: str
    description: str
    result_summary: str = ""
    entity_id: str | None = None
    entity_type: str | None = None


class PendingAction(BaseModel):
    """A write action awaiting user confirmation."""

    action_id: str
    tool_name: str
    arguments: dict
    description: str


class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: str  # "user" | "assistant"
    content: str
    actions: list[ChatAction] = []
    pending_actions: list[PendingAction] = []
    attachments: list[ChatAttachmentResponse] = []


class ChatResponse(BaseModel):
    """Response to a chat message."""

    conversation_id: str
    message: ChatMessage
    available: bool = True


class ChatConfirmRequest(BaseModel):
    """Confirm or reject a pending write action."""

    conversation_id: str
    action_id: str
    approved: bool


class ChatConfirmResponse(BaseModel):
    """Result of confirming/rejecting a pending action."""

    message: ChatMessage
    success: bool
