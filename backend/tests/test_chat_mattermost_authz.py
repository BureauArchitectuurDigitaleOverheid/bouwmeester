"""Chat tools, slash commands and suggestion buttons refuse what REST refuses.

Uses ``world`` from ``tests/authz_world.py``.  A chat write tool asks the
decision point before it asks for confirmation; a slash command or button
acts as the linked person, and only while that person may log in.
"""

import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can
from bouwmeester.models.chat_conversation import ChatConversation
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.models.tag import Tag
from bouwmeester.repositories.mattermost_channel_link import (
    MattermostChannelLinkRepository,
)
from bouwmeester.services.caller import caller_for
from bouwmeester.services.chat_service import (
    ChatService,
    _describe_pending,
    _execute_write_tool,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    MattermostUnavailableError,
)
from bouwmeester.services.mattermost_slash_service import (
    _NO_WRITE,
    MattermostSlashService,
)
from tests.authz_world import (
    add,
    chat_refusal,
    mm_account,
    mm_id,
    perm_ctx,
    request,
    rp,
    task,
)
from tests.factories import grant_role, make_person, place

# ---------------------------------------------------------------------------
# Chat write tools refuse what their REST routes refuse
# ---------------------------------------------------------------------------

WHO = ("team_editor", "afd_editor", "viewer")
AE = {"team_editor", "afd_editor"}
NT, ND = "{node_team}", "{node_directie}"


def _put(path: str, body: dict) -> tuple:
    return ("PUT", path, body)


def _new_task(**extra) -> tuple:
    return ("POST", "/api/tasks", {"title": "x", **extra})


# (tool, chat args, REST twin, who of WHO may).  ``{tag}`` is a fresh tag,
# ``{dir_task}`` a directie task: visible to the team, not writable there.
PARITY = [
    ("update_node", {"node_id": ND, "title": "x"},
     _put("/api/nodes/{node_directie}", {"title": "x"}), set()),
    ("update_node", {"node_id": NT, "title": "x"},
     _put("/api/nodes/{node_team}", {"title": "x"}), AE),
    ("update_task", {"task_id": "{task_team}", "title": "x"},
     _put("/api/tasks/{task_team}", {"title": "x"}), AE),
    ("create_task", {"node_id": ND}, _new_task(node_id=ND), set()),
    ("create_task", {"node_id": NT}, _new_task(node_id=NT), AE),
    ("create_task", {"node_id": NT, "organisatie_eenheid_id": "{eenheid_team}"},
     _new_task(node_id=NT, organisatie_eenheid_id="{eenheid_team}"), AE),
    ("create_task", {"node_id": NT, "organisatie_eenheid_id": "{eenheid_elders}"},
     _new_task(node_id=NT, organisatie_eenheid_id="{eenheid_elders}"), set()),
    # an invisible node, placed in an eenheid the caller may create in
    ("create_task",
     {"node_id": "{node_elders}", "organisatie_eenheid_id": "{eenheid_team}"},
     _new_task(node_id="{node_elders}", organisatie_eenheid_id="{eenheid_team}"),
     set()),
    ("create_task", {"node_id": NT, "parent_task_id": "{dir_task}"},
     _new_task(node_id=NT, parent_id="{dir_task}"), set()),
    ("create_task", {"node_id": NT, "parent_task_id": "{task_team}"},
     _new_task(node_id=NT, parent_id="{task_team}"), AE),
    ("add_tag_to_node", {"node_id": ND, "tag_name": "{tag}"},
     ("POST", "/api/nodes/{node_directie}/tags", {"tag_name": "{tag}"}), set()),
    ("add_tag_to_node", {"node_id": "{node_afdeling}", "tag_name": "{tag}"},
     ("POST", "/api/nodes/{node_afdeling}/tags", {"tag_name": "{tag}"}),
     {"afd_editor"}),
]  # fmt: skip


@pytest.mark.parametrize("who", WHO)
@pytest.mark.parametrize(
    ("tool", "args", "rest", "allowed"),
    PARITY,
    ids=[f"{p[0]}-{'-'.join(v.strip('{}') for v in p[1].values())}" for p in PARITY],
)
async def test_chat_tool_refuses_what_rest_refuses(
    world, who, tool, args, rest, allowed
):
    tag = Tag(name=f"tag-{uuid.uuid4().hex[:6]}")
    dir_task = task(world, "Directietaak", "node_directie", "directie")
    await add(world, tag, dir_task)
    world.res.update(tag=tag.name, dir_task=dir_task.id)
    refusal = await chat_refusal(world, who, tool, {"title": "x", **args})
    resp = await request(world, who, *rest)
    assert resp.status_code in (200, 201, 403, 404), resp.text
    assert (refusal is None) is (resp.status_code < 400), (refusal, resp.text)
    assert (refusal is None) is (who in allowed)


# (tool, argument, resource keys, permission it asks, resource type)
DECISION_TWINS = [
    ("add_tag_to_node", "node_id", ("node_team", "node_directie", "node_elders"),
     "node:update", "corpus_node"),
    ("update_lead", "lead_id", ("lead", "lead_free"), "lead:update", "lead"),
]  # fmt: skip


@pytest.mark.parametrize(("tool", "arg", "keys", "perm", "rtype"), DECISION_TWINS)
async def test_chat_tool_matches_the_decision_point(
    world, tool, arg, keys, perm, rtype
):
    for who in world.person:
        ctx = await perm_ctx(world, who)
        for key in keys:
            args = {arg: str(world.res[key]), "tag_name": "x"}
            refusal = await chat_refusal(world, who, tool, args)
            expected = await can(world.db, ctx, perm, rtype, world.res[key])
            assert (refusal is None) is expected, (who, key)


# Lead tools ask lead:update on the lead, lead:create in the own eenheid.
LEAD_TOOLS = [
    ("afd_editor", "update_lead", {"lead_id": "{lead}"}, True),
    ("role_only", "update_lead", {"lead_id": "{lead}"}, True),  # contributor
    ("team_editor", "update_lead", {"lead_id": "{lead}"}, False),  # below owner
    ("viewer", "move_lead", {"lead_id": "{lead}", "stage": "koelkast"}, False),
    ("afd_editor", "move_lead", {"lead_id": "{lead}", "stage": "koelkast"}, True),
    ("team_editor", "add_lead_activity", {"lead_id": "{lead}", "content": "x"}, False),
    ("afd_editor", "add_lead_activity", {"lead_id": "{lead}", "content": "x"}, True),
    ("team_editor", "update_lead", {"lead_id": "{lead_free}"}, True),  # unscoped
    ("viewer", "update_lead", {"lead_id": "{lead_free}"}, False),
    ("team_editor", "create_lead", {"title": "x"}, True),
    ("manager", "create_lead", {"title": "x"}, True),
    ("viewer", "create_lead", {"title": "x"}, False),
    ("role_only", "create_lead", {"title": "x"}, False),  # placed nowhere
]  # fmt: skip


@pytest.mark.parametrize(
    ("who", "tool", "args", "allowed"),
    LEAD_TOOLS,
    ids=[f"{c[0]}-{c[1]}-{next(iter(c[2].values()))}" for c in LEAD_TOOLS],
)
async def test_chat_lead_tools_ask_authz(world, who, tool, args, allowed):
    assert (await chat_refusal(world, who, tool, args) is None) is allowed


async def test_chat_create_lead_uses_a_placement_where_the_user_may_create(world):
    """The oldest placement has no lead:create; a later one does."""
    person = await make_person(world.db, "Twee plaatsingen")
    world.db.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=world.org["elders"].id,
            start_datum=date(2020, 1, 1),
        )
    )
    await place(world.db, person, world.org["afdeling"])
    await grant_role(world.db, person, "editor", world.org["afdeling"])
    result = await _execute_write_tool(
        "create_lead", {"title": "Lead via chat"}, world.db, person_id=person.id
    )
    assert result["success"], result
    lead = await world.db.get(Lead, uuid.UUID(result["entity_id"]))
    assert lead.organisatie_eenheid_id == world.org["afdeling"].id


async def test_chat_and_slash_share_one_caller(world):
    person = world.person["team_editor"]
    chat = await caller_for(world.db, person.id)
    slash = await MattermostSlashService(world.db)._caller(person.id)
    assert slash is not None
    assert slash.perm_ctx is chat.perm_ctx  # one context per session
    assert slash.org_ctx is chat.org_ctx
    # a command always comes from a known person, never anonymous
    assert await MattermostSlashService(world.db)._caller(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# The confirm card, and a confirm that runs once
# ---------------------------------------------------------------------------


async def test_confirm_card_names_the_item_the_person_and_the_fields(world):
    manager = world.person["manager"]

    async def card(who: str, tool: str, **args) -> str:
        caller = await caller_for(world.db, world.person[who].id)
        return await _describe_pending(tool, world.fill(args), world.db, caller)

    stake = "add_stakeholder"
    seen = await card("team_editor", stake, node_id=NT, person_id="{p_manager}")
    hidden = await card(
        "team_editor", stake, node_id="{node_elders}", person_id="{p_manager}"
    )
    lead = await card(
        "role_only", "update_lead", lead_id="{lead}", assignee_id="{p_manager}"
    )
    assert '"Teamdossier"' in seen and "Directeur" in seen
    assert "Dossier elders" not in hidden and "niet mag zien" in hidden
    assert '"Lead"' in lead
    assert f"toegewezen aan: Directeur ({str(manager.id)[:8]})" in lead
    assert "wijzigt: toegewezen aan" in lead


class _SilentLLM:
    async def chat_with_tools(self, **_kwargs):
        raise RuntimeError("no model in tests")


async def test_confirming_twice_at_once_runs_the_action_once(_test_engine, monkeypatch):
    """Two real sessions, as two requests: the second waits, then finds nothing."""
    runs: list[str] = []

    async def _write(tool_name, _args, _db, **_kwargs):
        runs.append(tool_name)
        await asyncio.sleep(0.2)
        return {"success": True, "summary": "gedaan"}

    monkeypatch.setattr("bouwmeester.services.chat_service._execute_write_tool", _write)
    async with AsyncSession(_test_engine, expire_on_commit=False) as setup:
        conv = ChatConversation(
            messages=[{"role": "system", "content": "x"}],
            pending_actions={"a1": {"tool_name": "update_lead", "arguments": {}}},
        )
        setup.add(conv)
        await setup.commit()
    try:

        async def _confirm() -> str:
            async with AsyncSession(_test_engine) as db:
                reply = await ChatService(_SilentLLM(), db).confirm_action(
                    str(conv.id), "a1", approved=True
                )
                await db.commit()
                return reply.content

        replies = await asyncio.gather(_confirm(), _confirm())
    finally:
        async with AsyncSession(_test_engine) as cleanup:
            await cleanup.execute(
                delete(ChatConversation).where(ChatConversation.id == conv.id)
            )
            await cleanup.commit()
    assert runs == ["update_lead"]
    assert any("al verwerkt" in reply for reply in replies)


# ---------------------------------------------------------------------------
# Mattermost slash commands and suggestion buttons
# ---------------------------------------------------------------------------


@pytest.fixture
async def slash(world, monkeypatch):
    """A linked channel of the initiatief, someone who only sees it, and a
    Mattermost account for everyone.  Channel membership is pinned below in
    ``test_slash_koppel_needs_a_reader_of_the_channel``: here every channel
    counts as linkable."""
    from bouwmeester.services import mattermost_slash_service

    monkeypatch.setattr(
        mattermost_slash_service, "channel_link_refusal", AsyncMock(return_value=None)
    )
    init_viewer = await make_person(world.db, "Initiatiefkijker")
    world.person["init_viewer"] = init_viewer
    channel = mm_id()
    await add(
        world,
        rp("initiatief", world.res["initiatief"], "viewer", person=init_viewer),
        MattermostChannelLink(
            channel_id=channel,
            channel_name="kanaal",
            channel_display_name="kanaal",
            scope_type="initiatief",
            scope_id=world.res["initiatief"],
        ),
    )
    accounts = {who: await mm_account(world, who) for who in world.person}
    return {"channel": channel, "mm": accounts}


# (who, command, on the linked channel?, allowed)
SLASH_CASES = [
    ("init_viewer", "koppel initiatief {naam}", False, False),
    ("role_only", "koppel initiatief {naam}", False, True),  # contributor
    ("init_viewer", "ontkoppel", True, False),
    ("role_only", "ontkoppel", True, True),
    ("init_viewer", "volg Digitale Dienst", True, False),
    ("afd_editor", "volg Digitale Dienst", True, True),
]  # fmt: skip


@pytest.mark.parametrize(
    ("who", "command", "linked", "allowed"),
    SLASH_CASES,
    ids=[f"{c[0]}-{c[1].split()[0]}" for c in SLASH_CASES],
)
async def test_slash_command_writes_ask_authz(
    world, slash, who, command, linked, allowed
):
    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    channel = slash["channel"] if linked else mm_id()
    result = await MattermostSlashService(world.db).handle_command(
        slash["mm"][who],
        command.format(naam=naam),
        channel_id=channel,
        channel_name="kanaal",
    )
    assert (_NO_WRITE not in result["text"]) is allowed, result["text"]
    if command.startswith("koppel"):
        repo = MattermostChannelLinkRepository(world.db)
        assert (await repo.get_by_channel_id(channel) is not None) is allowed


# (who, button, match an existing lead?, allowed).  Reviewing a suggestion
# is initiatief:update; creating a lead from it is lead:create there.
BUTTONS = [
    ("init_viewer", "create_lead_from_suggestion", False, False),
    ("afd_editor", "create_lead_from_suggestion", False, True),
    ("init_viewer", "reject_suggestion", True, False),
    ("role_only", "reject_suggestion", True, True),  # contributor
    ("init_viewer", "link_lead_to_suggestion", True, False),
    ("role_only", "link_lead_to_suggestion", True, True),
]  # fmt: skip


@pytest.mark.parametrize(("who", "action", "match", "allowed"), BUTTONS)
async def test_suggestion_buttons_ask_authz(world, slash, who, action, match, allowed):
    suggested = await add(
        world,
        SuggestedLead(
            source_post_id=mm_id(),
            source_channel_id=slash["channel"],
            initiatief_id=world.res["initiatief"],
            proposed_title="Gemeente",
            raw_text="Gemeente vraagt om een gesprek.",
            match_existing_lead_id=world.res["lead"] if match else None,
            status="pending",
        ),
    )
    if match:
        ctx = await perm_ctx(world, who)
        decision = await can(
            world.db, ctx, "suggested_lead:update", "suggested_lead", suggested.id
        )
        assert decision is allowed
    context = {"suggested_lead_id": str(suggested.id)}
    with patch.object(MattermostSlashService, "_update_thread_post", AsyncMock()):
        result = await MattermostSlashService(world.db).handle_action(
            slash["mm"][who], action, context
        )
    assert (result["ephemeral_text"] != _NO_WRITE) is allowed, result
    assert (suggested.status != "pending") is allowed
    if allowed and action.startswith("create"):
        assert suggested.status == "approved_new"


# (channel type, team member?, channel member?, Mattermost reachable?, linked?)
KOPPEL_CASES = [
    ("O", True, False, True, True),  # an open channel of your own team
    ("O", False, False, True, False),  # an open channel of another team
    ("O", False, True, True, True),  # a member of the channel itself
    ("P", True, True, True, True),
    ("P", True, False, True, False),  # a team member, not in the channel
    ("P", True, True, False, False),  # fails closed
]  # fmt: skip


@pytest.mark.parametrize(
    ("kind", "in_team", "member", "reachable", "linked"), KOPPEL_CASES
)
async def test_slash_koppel_needs_a_reader_of_the_channel(
    world, kind, in_team, member, reachable, linked
):
    """Only someone who can read a channel may link it (its posts are ingested)."""
    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    user = await mm_account(world, "role_only")  # contributor: may link
    channel = mm_id()
    found = {"id": channel, "type": kind, "team_id": "team"}
    down = MattermostUnavailableError("weg")
    with (
        patch.object(
            MattermostService,
            "get_channel",
            AsyncMock(return_value=found, side_effect=None if reachable else down),
        ),
        patch.object(
            MattermostService, "is_member_of_team", AsyncMock(return_value=in_team)
        ),
        patch.object(
            MattermostService, "is_member_of_channel", AsyncMock(return_value=member)
        ),
    ):
        await MattermostSlashService(world.db).handle_command(
            user, f"koppel initiatief {naam}", channel_id=channel, channel_name="k"
        )
    link = await MattermostChannelLinkRepository(world.db).get_by_channel_id(channel)
    assert (link is not None) is linked


@pytest.mark.parametrize("revoked", ["active", "inactive", "off_whitelist"])
async def test_slash_command_refuses_a_revoked_person(world, monkeypatch, revoked):
    """A linked account acts only while its person may log in."""
    user = await mm_account(world, "viewer")
    if revoked == "inactive":
        world.person["viewer"].is_active = False
    elif revoked == "off_whitelist":
        monkeypatch.setattr(
            "bouwmeester.services.caller.is_email_allowed", lambda _email: False
        )
    await world.db.flush()
    result = await MattermostSlashService(world.db).handle_command(user, "taken")
    assert ("niet gekoppeld" in result["text"]) is (revoked != "active")
