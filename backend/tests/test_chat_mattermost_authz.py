"""Chat tools, slash commands and suggestion buttons refuse what REST refuses.

A chat write tool asks the decision point before it asks for confirmation; a
slash command or button acts as the linked person, only while they may log in.
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
from bouwmeester.services.mattermost_service import MattermostService as Mm
from bouwmeester.services.mattermost_service import MattermostUnavailableError
from bouwmeester.services.mattermost_slash_service import _NO_WRITE
from bouwmeester.services.mattermost_slash_service import (
    MattermostSlashService as Slash,
)
from tests import authz_world as aw
from tests.authz_world import add, chat_refusal, mm_account, mm_id, request, rp
from tests.factories import grant_role, make_person, place

# Chat write tools refuse what their REST routes refuse
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


_PARITY_IDS = [f"{p[0]}-{'-'.join(v.strip('{}') for v in p[1].values())}"
               for p in PARITY]  # fmt: skip


@pytest.mark.parametrize("who", WHO)
@pytest.mark.parametrize(("tool", "args", "rest", "allowed"), PARITY, ids=_PARITY_IDS)
async def test_chat_tool_refuses_what_rest_refuses(
    world, who, tool, args, rest, allowed
):
    tag = Tag(name=f"tag-{uuid.uuid4().hex[:6]}")
    dir_task = aw.task(world, "Directietaak", "node_directie", "directie")
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
        ctx = await aw.perm_ctx(world, who)
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


_LEAD_IDS = [f"{c[0]}-{c[1]}-{next(iter(c[2].values()))}" for c in LEAD_TOOLS]


@pytest.mark.parametrize(("who", "tool", "args", "allowed"), LEAD_TOOLS, ids=_LEAD_IDS)
async def test_chat_lead_tools_ask_authz(world, who, tool, args, allowed):
    assert (await chat_refusal(world, who, tool, args) is None) is allowed


async def test_chat_create_lead_uses_a_placement_where_the_user_may_create(world):
    """The oldest placement has no lead:create; a later one does."""
    person = await make_person(world.db, "Twee plaatsingen")
    world.db.add(PersonOrganisatieEenheid(
        person_id=person.id, start_datum=date(2020, 1, 1),
        organisatie_eenheid_id=world.org["elders"].id))  # fmt: skip
    await place(world.db, person, world.org["afdeling"])
    await grant_role(world.db, person, "editor", world.org["afdeling"])
    args = {"title": "Lead via chat"}
    result = await _execute_write_tool(
        "create_lead", args, world.db, person_id=person.id
    )
    assert result["success"], result
    lead = await world.db.get(Lead, uuid.UUID(result["entity_id"]))
    assert lead.organisatie_eenheid_id == world.org["afdeling"].id


async def test_chat_and_slash_share_one_caller(world):
    person = world.person["team_editor"]
    chat = await caller_for(world.db, person.id)
    slash = await Slash(world.db)._caller(person.id)
    assert slash is not None
    assert slash.perm_ctx is chat.perm_ctx  # one context per session
    assert slash.org_ctx is chat.org_ctx
    # a command always comes from a known person, never anonymous
    assert await Slash(world.db)._caller(uuid.uuid4()) is None


# The confirm card, and a confirm that runs once
async def test_confirm_card_names_the_item_the_person_and_the_fields(world):
    manager = world.person["manager"]

    async def card(who: str, tool: str, **args) -> str:
        caller = await caller_for(world.db, world.person[who].id)
        return await _describe_pending(tool, world.fill(args), world.db, caller)

    stake, pm = "add_stakeholder", "{p_manager}"
    seen = await card("team_editor", stake, node_id=NT, person_id=pm)
    hidden = await card("team_editor", stake, node_id="{node_elders}", person_id=pm)
    lead = await card("role_only", "update_lead", lead_id="{lead}", assignee_id=pm)
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
    pending = {"a1": {"tool_name": "update_lead", "arguments": {}}}
    async with AsyncSession(_test_engine, expire_on_commit=False) as setup:
        conv = ChatConversation(messages=[{"role": "system", "content": "x"}],
                                pending_actions=pending)  # fmt: skip
        setup.add(conv)
        await setup.commit()

    async def _confirm() -> str:
        async with AsyncSession(_test_engine) as db:
            chat = ChatService(_SilentLLM(), db)
            reply = await chat.confirm_action(str(conv.id), "a1", approved=True)
            await db.commit()
            return reply.content

    try:
        replies = await asyncio.gather(_confirm(), _confirm())
    finally:
        async with AsyncSession(_test_engine) as cleanup:
            await cleanup.execute(delete(ChatConversation).where(
                ChatConversation.id == conv.id))  # fmt: skip
            await cleanup.commit()
    assert runs == ["update_lead"]
    assert any("al verwerkt" in reply for reply in replies)


# Mattermost slash commands and suggestion buttons
@pytest.fixture
async def slash(world, monkeypatch):
    """A linked channel of the initiatief, someone who only sees it, and a
    Mattermost account for everyone.  Channel membership is pinned below in
    ``test_slash_koppel_needs_a_reader_of_the_channel``: here every channel
    counts as linkable."""
    monkeypatch.setattr(
        "bouwmeester.services.mattermost_slash_service.channel_link_refusal",
        AsyncMock(return_value=None),
    )
    viewer = world.person["init_viewer"] = await make_person(world.db, "Kijker")
    channel, init = mm_id(), world.res["initiatief"]
    await add(world, rp("initiatief", init, "viewer", person=viewer),
              MattermostChannelLink(channel_id=channel, channel_name="k",
                                    channel_display_name="k", scope_id=init,
                                    scope_type="initiatief"))  # fmt: skip
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


_SLASH_IDS = [f"{c[0]}-{c[1].split()[0]}" for c in SLASH_CASES]


@pytest.mark.parametrize(("who", "command", "linked", "allowed"), SLASH_CASES,
                         ids=_SLASH_IDS)  # fmt: skip
async def test_slash_command_writes_ask_authz(world, slash, who, command, linked,
                                              allowed):  # fmt: skip
    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    channel = slash["channel"] if linked else mm_id()
    result = await Slash(world.db).handle_command(
        slash["mm"][who], command.format(naam=naam), channel_id=channel,
        channel_name="kanaal")  # fmt: skip
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
    suggested = await add(world, SuggestedLead(
        source_post_id=mm_id(), source_channel_id=slash["channel"],
        initiatief_id=world.res["initiatief"], proposed_title="Gemeente",
        raw_text="Gemeente vraagt om een gesprek.", status="pending",
        match_existing_lead_id=world.res["lead"] if match else None))  # fmt: skip
    if match:
        ctx, rtype = await aw.perm_ctx(world, who), "suggested_lead"
        assert (
            await can(world.db, ctx, f"{rtype}:update", rtype, suggested.id) is allowed
        )
    context = {"suggested_lead_id": str(suggested.id)}
    with patch.object(Slash, "_update_thread_post", AsyncMock()):
        result = await Slash(world.db).handle_action(slash["mm"][who], action, context)
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


@pytest.mark.parametrize(("kind", "in_team", "member", "reachable", "linked"),
                         KOPPEL_CASES)  # fmt: skip
async def test_slash_koppel_needs_a_reader_of_the_channel(
        world, kind, in_team, member, reachable, linked):  # fmt: skip
    """Only someone who can read a channel may link it (its posts are ingested)."""
    naam = (await world.db.get(Initiatief, world.res["initiatief"])).naam
    user = await mm_account(world, "role_only")  # contributor: may link
    channel = mm_id()
    found = {"id": channel, "type": kind, "team_id": "team"}
    down = MattermostUnavailableError("weg")
    get = AsyncMock(return_value=found, side_effect=None if reachable else down)
    with (
        patch.object(Mm, "get_channel", get),
        patch.object(Mm, "is_member_of_team", AsyncMock(return_value=in_team)),
        patch.object(Mm, "is_member_of_channel", AsyncMock(return_value=member)),
    ):
        command = f"koppel initiatief {naam}"
        await Slash(world.db).handle_command(user, command, channel_id=channel,
                                             channel_name="k")  # fmt: skip
    link = await MattermostChannelLinkRepository(world.db).get_by_channel_id(channel)
    assert (link is not None) is linked


@pytest.mark.parametrize("revoked", ["active", "inactive", "off_whitelist"])
async def test_slash_command_refuses_a_revoked_person(world, monkeypatch, revoked):
    """A linked account acts only while its person may log in."""
    user = await mm_account(world, "viewer")
    world.person["viewer"].is_active = revoked != "inactive"
    if revoked == "off_whitelist":
        allowed = "bouwmeester.services.caller.is_email_allowed"
        monkeypatch.setattr(allowed, lambda _email: False)
    await world.db.flush()
    result = await Slash(world.db).handle_command(user, "taken")
    assert ("niet gekoppeld" in result["text"]) is (revoked != "active")
