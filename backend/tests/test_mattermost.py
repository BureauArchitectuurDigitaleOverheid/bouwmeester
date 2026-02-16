"""Tests for Mattermost integration."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_slash_service import MattermostSlashService

# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_link_code(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    code = await repo.create_link_code(sample_person.id)

    assert code.code.startswith("BM-")
    assert len(code.code) == 11  # "BM-" + 8 chars (configurable)
    assert code.person_id == sample_person.id
    assert code.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_verify_valid_code(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    code = await repo.create_link_code(sample_person.id)

    verified = await repo.verify_code(code.code)
    assert verified is not None
    assert verified.person_id == sample_person.id


@pytest.mark.asyncio
async def test_verify_expired_code(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    code = await repo.create_link_code(sample_person.id)

    # Manually expire the code.
    code.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    verified = await repo.verify_code(code.code)
    assert verified is None


@pytest.mark.asyncio
async def test_create_mapping(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    mapping = await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_user_123",
        mattermost_username="testuser",
    )

    assert mapping.person_id == sample_person.id
    assert mapping.mattermost_user_id == "mm_user_123"
    assert mapping.mattermost_username == "testuser"


@pytest.mark.asyncio
async def test_get_mapping_by_person(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_user_456",
        mattermost_username="testuser2",
    )

    found = await repo.get_by_person_id(sample_person.id)
    assert found is not None
    assert found.mattermost_user_id == "mm_user_456"


@pytest.mark.asyncio
async def test_get_mapping_by_mm_user_id(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_user_789",
        mattermost_username="testuser3",
    )

    found = await repo.get_by_mattermost_user_id("mm_user_789")
    assert found is not None
    assert found.person_id == sample_person.id


@pytest.mark.asyncio
async def test_delete_mapping(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_delete_test",
        mattermost_username="deletetest",
    )

    deleted = await repo.delete_by_person_id(sample_person.id)
    assert deleted is True

    found = await repo.get_by_person_id(sample_person.id)
    assert found is None


@pytest.mark.asyncio
async def test_create_code_replaces_existing(db_session: AsyncSession, sample_person):
    repo = MattermostUserRepository(db_session)
    code1 = await repo.create_link_code(sample_person.id)
    code2 = await repo.create_link_code(sample_person.id)

    # Old code should be gone.
    assert await repo.verify_code(code1.code) is None
    # New code should work.
    assert await repo.verify_code(code2.code) is not None


@pytest.mark.asyncio
async def test_cleanup_expired_codes(
    db_session: AsyncSession, sample_person, second_person
):
    repo = MattermostUserRepository(db_session)

    # Create one valid and one expired code.
    valid_code = await repo.create_link_code(sample_person.id)

    expired_code = await repo.create_link_code(second_person.id)
    expired_code.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.flush()

    cleaned = await repo.cleanup_expired_codes()
    assert cleaned >= 1

    # Valid code still works.
    assert await repo.verify_code(valid_code.code) is not None


# ---------------------------------------------------------------------------
# Service tests (mock httpx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mattermost_service_disabled(db_session: AsyncSession):
    """When MATTERMOST_ENABLED is False, send_notification returns False."""
    from bouwmeester.services.mattermost_service import clear_mattermost_config_cache

    clear_mattermost_config_cache()
    with (
        patch("bouwmeester.services.mattermost_service.get_settings") as mock_settings,
        patch(
            "bouwmeester.services.mattermost_service._load_mattermost_config",
            return_value={},
        ),
    ):
        mock_settings.return_value.MATTERMOST_ENABLED = False
        mock_settings.return_value.MATTERMOST_BOT_TOKEN = ""
        service = MattermostService(db_session)
        assert await service.is_enabled() is False


@pytest.mark.asyncio
async def test_format_notification(db_session: AsyncSession, sample_person):
    """Test notification formatting produces valid attachment structure."""
    from bouwmeester.models.notification import Notification

    notif = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="task_assigned",
        title="Nieuwe taak: Test",
        message="De taak 'Test' is aan je toegewezen.",
        related_task_id=uuid.uuid4(),
    )

    with patch("bouwmeester.services.mattermost_service.get_settings") as mock_settings:
        mock_settings.return_value.MATTERMOST_ENABLED = True
        mock_settings.return_value.MATTERMOST_BOT_TOKEN = "test-token"
        mock_settings.return_value.MATTERMOST_URL = "http://localhost:8065"
        mock_settings.return_value.FRONTEND_URL = "http://localhost:5173"
        mock_settings.return_value.BACKEND_URL = "http://localhost:8000"
        mock_settings.return_value.MATTERMOST_NOTIFICATION_CHANNEL_ID = ""
        mock_settings.return_value.MATTERMOST_WEBHOOK_TOKEN = ""

        service = MattermostService(db_session)
        text, props = service.format_notification(notif)

        assert "attachments" in props
        attachment = props["attachments"][0]
        assert attachment["color"] == "#3B82F6"  # blue for task_assigned
        assert attachment["title"] == "Nieuwe taak: Test"
        assert len(attachment["actions"]) == 1  # Taak afronden
        assert attachment["actions"][0]["name"] == "Taak afronden"
        assert attachment["footer"] == "Bouwmeester"


# ---------------------------------------------------------------------------
# Slash command tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_help(db_session: AsyncSession):
    service = MattermostSlashService(db_session)
    result = await service.handle_command("unknown_user", "help")
    assert result["response_type"] == "ephemeral"
    assert "commando's" in result["text"].lower()


@pytest.mark.asyncio
async def test_slash_taken_unlinked(db_session: AsyncSession):
    service = MattermostSlashService(db_session)
    result = await service.handle_command("unlinked_user", "taken")
    assert "niet gekoppeld" in result["text"].lower()


@pytest.mark.asyncio
async def test_slash_taken_linked(db_session: AsyncSession, sample_person, sample_task):
    """Linked user can list their tasks."""
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_slash_test",
        mattermost_username="slashtest",
    )

    service = MattermostSlashService(db_session)
    result = await service.handle_command("mm_slash_test", "taken alles")
    assert result["response_type"] == "ephemeral"
    assert "Test taak" in result["text"]


@pytest.mark.asyncio
async def test_slash_zoek_no_term(db_session: AsyncSession):
    service = MattermostSlashService(db_session)
    result = await service.handle_command("some_user", "zoek")
    assert "zoekterm" in result["text"].lower()


@pytest.mark.asyncio
async def test_action_complete_task(
    db_session: AsyncSession, sample_person, sample_task
):
    """Linked user can complete a task via button action."""
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=sample_person.id,
        mattermost_user_id="mm_action_test",
        mattermost_username="actiontest",
    )

    service = MattermostSlashService(db_session)
    result = await service.handle_action(
        mattermost_user_id="mm_action_test",
        action="complete_task",
        context={"task_id": str(sample_task.id)},
    )

    assert "update" in result
    # Verify task is done.
    await db_session.refresh(sample_task)
    assert sample_task.status == "done"


@pytest.mark.asyncio
async def test_action_complete_task_wrong_assignee(
    db_session: AsyncSession, sample_person, second_person, sample_task
):
    """Non-assignee cannot complete a task."""
    repo = MattermostUserRepository(db_session)
    await repo.create_mapping(
        person_id=second_person.id,
        mattermost_user_id="mm_wrong_assignee",
        mattermost_username="wronguser",
    )

    service = MattermostSlashService(db_session)
    result = await service.handle_action(
        mattermost_user_id="mm_wrong_assignee",
        action="complete_task",
        context={"task_id": str(sample_task.id)},
    )

    assert "niet de toegewezene" in result["ephemeral_text"]
