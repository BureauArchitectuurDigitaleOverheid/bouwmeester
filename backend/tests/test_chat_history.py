"""Tests for the GET /chat/{conversation_id} history endpoint."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.chat_attachment import ChatAttachment
from bouwmeester.models.chat_conversation import ChatConversation
from bouwmeester.services.llm.prompts import CHAT_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conversation(db_session: AsyncSession):
    """Create a conversation with a mix of message types."""
    conv = ChatConversation(
        id=uuid.uuid4(),
        person_id=None,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": "Hallo"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "search_nodes",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": '{"results": [], "count": 0}',
            },
            {"role": "assistant", "content": "Ik kon niets vinden."},
        ],
        pending_actions={},
    )
    db_session.add(conv)
    await db_session.flush()
    return conv


@pytest.fixture
async def conversation_with_pending(db_session: AsyncSession):
    """Create a conversation that has a pending write action."""
    action_id = str(uuid.uuid4())
    conv = ChatConversation(
        id=uuid.uuid4(),
        person_id=None,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": "Maak een node"},
            {"role": "assistant", "content": "Ik wil een node aanmaken."},
        ],
        pending_actions={
            action_id: {
                "tool_name": "create_node",
                "arguments": {"title": "Test node", "node_type": "dossier"},
                "tool_call_id": "tc_2",
            },
        },
    )
    db_session.add(conv)
    await db_session.flush()
    return conv, action_id


@pytest.fixture
async def conversation_with_attachment(db_session: AsyncSession):
    """Create a conversation with an attachment reference on a user message."""
    att_id = uuid.uuid4()

    att = ChatAttachment(
        id=att_id,
        person_id=None,
        bestandsnaam="document.pdf",
        content_type="application/pdf",
        bestandsgrootte=1024,
        pad=f"{att_id}/doc.pdf",
    )
    db_session.add(att)
    await db_session.flush()

    conv = ChatConversation(
        id=uuid.uuid4(),
        person_id=None,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Bekijk dit bestand",
                "attachment_refs": [
                    {
                        "type": "document_ref",
                        "attachment_id": str(att_id),
                        "bestandsnaam": "document.pdf",
                        "extracted_text": "inhoud",
                    }
                ],
            },
            {"role": "assistant", "content": "Ik heb het bestand bekeken."},
        ],
        pending_actions={},
    )
    db_session.add(conv)
    await db_session.flush()
    return conv, att


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_history_returns_messages(client, conversation):
    """GET /api/chat/{id} returns user + assistant messages, filters system/tool."""
    resp = await client.get(f"/api/chat/{conversation.id}")
    assert resp.status_code == 200

    data = resp.json()
    assert data["conversation_id"] == str(conversation.id)

    messages = data["messages"]
    roles = [m["role"] for m in messages]
    assert "system" not in roles
    assert "tool" not in roles
    assert roles == ["user", "assistant"]
    assert messages[0]["content"] == "Hallo"
    assert messages[1]["content"] == "Ik kon niets vinden."


async def test_get_history_skips_empty_tool_call_assistants(client, conversation):
    """Empty assistant messages that only hold tool_calls are filtered out."""
    resp = await client.get(f"/api/chat/{conversation.id}")
    data = resp.json()
    # The assistant message with empty content + tool_calls should not appear
    assistant_msgs = [m for m in data["messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["content"] == "Ik kon niets vinden."


async def test_get_history_pending_actions(client, conversation_with_pending):
    """Pending actions are attached to the last assistant message."""
    conv, action_id = conversation_with_pending
    resp = await client.get(f"/api/chat/{conv.id}")
    assert resp.status_code == 200

    data = resp.json()
    messages = data["messages"]
    last_assistant = [m for m in messages if m["role"] == "assistant"][-1]
    assert len(last_assistant["pending_actions"]) == 1
    pa = last_assistant["pending_actions"][0]
    assert pa["action_id"] == action_id
    assert pa["tool_name"] == "create_node"
    assert "aanmaken" in pa["description"].lower()


async def test_get_history_resolves_attachments(client, conversation_with_attachment):
    """Attachment refs on user messages are resolved to attachment metadata."""
    conv, att = conversation_with_attachment
    resp = await client.get(f"/api/chat/{conv.id}")
    assert resp.status_code == 200

    data = resp.json()
    user_msg = [m for m in data["messages"] if m["role"] == "user"][0]
    assert len(user_msg["attachments"]) == 1
    assert user_msg["attachments"][0]["id"] == str(att.id)
    assert user_msg["attachments"][0]["bestandsnaam"] == "document.pdf"


async def test_get_history_nonexistent_returns_404(client):
    """GET /api/chat/{id} returns 404 for a nonexistent conversation."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/chat/{fake_id}")
    assert resp.status_code == 404


async def test_get_history_invalid_uuid_returns_404(client):
    """GET /api/chat/{id} returns 404 for an invalid UUID string."""
    resp = await client.get("/api/chat/not-a-uuid")
    assert resp.status_code == 404
