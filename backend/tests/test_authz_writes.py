"""Who may write what: every write route asks ``core/authz.py`` the same question.

On ``iw`` from ``tests/authz_world.py`` plus ``ww``: an opdrachtgever of the
lead (``rp_viewer`` only reads the initiatief), leads of the team and of
``elders`` with an editor there, lead sub-records and posts, opdrachten, a
tag, assessments, an initiatief post and a share.  A write on something the
caller cannot see answers 404, as if it did not exist.
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from bouwmeester.models.bron import Bron
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.tag import Tag
from bouwmeester.schema.lead import LeadCreate
from bouwmeester.services.lead_rules import require_lead_create
from tests.authz_world import (
    World,
    add,
    ask,
    assert_route_case,
    chat_refusal,
    evaluate,
    make_agent,
    make_item,
    opdracht,
    perm_ctx,
    request,
    rp,
    task,
)
from tests.factories import grant_role, make_person, place


@pytest.fixture
async def ww(iw: World) -> World:
    w, org, lead, db = iw, iw.org, iw.res["lead"], iw.db
    opdrachtgever = await make_person(db, "Opdrachtgever")
    eigenaar = await make_person(db, "Aanmaker stakeholder-eenheid")
    elders_editor = await make_person(db, "Redacteur elders")
    await place(db, elders_editor, org["elders"])
    await grant_role(db, elders_editor, "editor", org["elders"])
    w.person.update(opdrachtgever=opdrachtgever, eenheid_eigenaar=eigenaar,
                    elders_editor=elders_editor)  # fmt: skip
    tag_name = f"Bestaande tag {uuid.uuid4().hex[:6]}"
    role_only, viewer = w.person["role_only"], w.person["viewer"]
    init, team = w.res["initiatief"], org["team"].id
    published = datetime(2026, 1, 1, tzinfo=UTC)
    rows = {
        "lead_other": Lead(title="L", stage="verkennen", initiatief_id=init),
        "lead_team": Lead(title="T", stage="verkennen", organisatie_eenheid_id=team),
        "lead_elders": Lead(title="E", stage="verkennen",
                            organisatie_eenheid_id=org["elders"].id),
        "activity": LeadActivity(lead_id=lead, content="N", activity_type="note",
                                 author_id=role_only.id),
        "post": LeadUpdatePost(lead_id=lead, titel="Update"),
        "public_post": LeadUpdatePost(lead_id=lead, titel="Openbaar", body_public="T"),
        "published": LeadUpdatePost(lead_id=lead, titel="Oud", body_public="Oud",
                                    published_at=published),
        "attachment": LeadAttachment(lead_id=lead, soort="link", url="https://x.nl"),
        "github_link": GitHubLink(scope_type=SCOPE_LEAD, scope_id=lead, owner="foo",
                                  url="https://github.com/foo/bar/pull/1", repo="bar",
                                  link_type="pull_request"),
        "opdrachtgever_grant": rp("lead", lead, "opdrachtgever", person=opdrachtgever),
        "opdracht_afdeling": opdracht(w, "Afdeling", "afdeling"),
        "opdracht_elders": opdracht(w, "Elders", "elders"),
        "opdracht_voor_team": opdracht(w, "T", "elders",
                                       opdrachtnemer_eenheid_id=team),
        "task_directie": task(w, "Directietaak", "node_directie", "directie"),
        "sa_team": StakeholderAssessment(person_id=viewer.id, scope_type="corpus_node",
                                         scope_id=w.res["node_team"], belang=3),
        "sa_directie": StakeholderAssessment(person_id=viewer.id, belang=3,
                                             scope_type="corpus_node",
                                             scope_id=w.res["node_directie"]),
        "tag": Tag(name=tag_name),
        "init_post": InitiatiefUpdatePost(initiatief_id=init, titel="T"),
        "share": SharedAccess(source_eenheid_id=org["dg"].id, access_level="read",
                              target_eenheid_id=team, geldig_van=date.today()),
    }  # fmt: skip
    bronnen = [Bron(id=w.res[node]) for node in ("node_team", "node_directie")]
    owner = rp("organisatie_eenheid", org["elders"].id, "eigenaar", person=eigenaar)
    await add(w, *rows.values(), *bronnen, owner)
    w.res.update({k: v.id for k, v in rows.items()}, tag_name=tag_name)
    w.res["item"] = (await make_item(w)).id
    return w


@pytest.fixture(autouse=True)
def linkable(monkeypatch):
    """Every Mattermost channel counts as one the caller may link."""
    monkeypatch.setattr(
        "bouwmeester.api.routes.mattermost_channels.channel_link_refusal",
        AsyncMock(return_value=None),
    )


# Body builders; ``{key}`` placeholders are filled from the world.
_MISSING = uuid.UUID("00000000-0000-4000-8000-000000000000")
_NODE = {"title": "Nieuw", "node_type": "dossier", "status": "actief"}
_COLUMN = {"name": "Nieuwe kolom", "color": "accent"}
L, LF = "/api/leads/{lead}", "/api/leads/{lead_free}"
INIT, OD = "/api/initiatieven/{initiatief}", "/api/opdrachten/{opdracht_directie}"
ORG, SA = "/api/organisatie", "/api/stakeholder-assessments"
NT = "/api/nodes/{node_directie}/tags"
C, CF = L + "/contacts", LF + "/contacts"
SWV = "/api/samenwerkingsverbanden/{samenwerkingsverband}"


def _ph(key: str) -> str:
    """A placeholder for one of the world's ids."""
    return "{" + key + "}"


def _edge(src: str, dst: str) -> dict:
    return dict(from_node_id=_ph(src), to_node_id=_ph(dst), edge_type_id="{edge_type}")


def _task(node: str, eenheid: str) -> dict:
    return {"title": "Taak", "node_id": _ph(node)} | _in(eenheid)


def _in(eenheid: str | None) -> dict:
    return {"organisatie_eenheid_id": _ph(f"eenheid_{eenheid}") if eenheid else None}


def _lead(stage: str = "verkennen", **kw) -> dict:
    return {"title": "Nieuwe lead", "stage": stage, **kw}


def _grant(who: str, rol: str) -> dict:
    return {"person_id": _ph(f"p_{who}"), "rol": rol}


def _merge(src: str, dst: str) -> dict:
    return {"source_id": _ph(src), "target_id": _ph(dst)}


def _opdracht(**places) -> dict:
    body = {"type": "opdracht", "titel": "N", "begrotingsjaar": 2026}
    body["instrument_id"] = "{node_team}"
    return body | {k: _ph(f"eenheid_{v}") for k, v in places.items()}


def _koppeling(node: str) -> dict:
    body = _opdracht(opdrachtgever_id="afdeling") | {"instrument_id": "{node_afdeling}"}
    return body | {"node_koppelingen": [{"node_id": _ph(node)}]}


def _assessment(node: str) -> dict:
    body = dict(person_id="{p_manager}", scope_type="corpus_node", belang=4)
    return body | {"scope_id": _ph(node)}


def _share(source: str) -> dict:
    body = {"target_eenheid_id": "{eenheid_elders}", "access_level": "read"}
    if source.startswith("node_"):
        return body | {"source_node_id": _ph(source)}
    return body | {"source_eenheid_id": _ph(f"eenheid_{source}")}


def _channel(_w) -> dict:
    """Every link needs its own channel id."""
    return dict(
        channel_id=uuid.uuid4().hex[:26], channel_name="k", channel_display_name="K"
    )


_OLD_TAG = {"tag_name": "{tag_name}"}
_OPDR_DIRECTIE = _opdracht(opdrachtgever_id="directie")
_OPDR_TEAM_TEAM = _opdracht(opdrachtgever_id="team", opdrachtnemer_eenheid_id="team")
_OPDR_TEAM_ELDERS = _opdracht(
    opdrachtgever_id="team", opdrachtnemer_eenheid_id="elders"
)
_TO_DIRECTIE = {"opdrachtgever_id": "{eenheid_directie}"}
_INTO_INIT = {"initiatief_id": "{initiatief}", "stage": "verkennen"}
_NEW_IN_DIRECTIE = _lead("inbox", organisatie_eenheid_id="{eenheid_directie}")
_REORDER = {"lead_ids": ["{lead}", "{lead_other}"], "stage": "verkennen"}
_NOTE = {"content": "Ja", "activity_type": "note"}
_PR = {"url": "https://github.com/foo/bar/pull/2"}
_MODULE = {"module": "leads", "enabled": False}
_WRONG_PARENT = f"/api/initiatieven/{_MISSING}/updates/{{init_post}}"

# (who, method, path, body, expected status)
ROUTES = [
    # nodes: rights on the node's eenheid; unseen or missing is 404
    ("viewer", "POST", "/api/nodes", _NODE, 403),
    ("viewer", "PUT", "/api/nodes/{node_team}", {"title": "Nee"}, 403),
    ("viewer", "DELETE", "/api/nodes/{node_team}", None, 403),
    ("team_editor", "PUT", "/api/nodes/{node_team}", {"title": "Ja"}, 200),
    ("team_editor", "PUT", "/api/nodes/{node_directie}", {"title": "Nee"}, 403),
    ("team_editor", "PUT", "/api/nodes/{node_elders}", {"title": "Nee"}, 404),
    ("team_editor", "DELETE", "/api/nodes/{node_elders}", None, 404),
    ("team_editor", "PUT", f"/api/nodes/{_MISSING}", {"title": "?"}, 404),
    # linking a tag is editing the node; a new tag needs tag:create too
    ("role_only", "POST", NT, _OLD_TAG, 201),
    ("role_only", "POST", NT, {"tag_name": "Nieuw label"}, 403),
    ("team_editor", "POST", NT, _OLD_TAG, 403),
    # edges: one writable end, the other end must be visible
    ("viewer", "POST", "/api/edges", _edge("node_team", "node_free"), 403),
    ("team_editor", "POST", "/api/edges", _edge("node_directie", "node_team"), 201),
    ("team_editor", "POST", "/api/edges", _edge("node_free", "node_team"), 201),
    ("team_editor", "POST", "/api/edges", _edge("node_afdeling", "node_directie"), 403),
    ("team_editor", "POST", "/api/edges", _edge("node_team", "node_elders"), 404),
    ("team_editor", "POST", "/api/edges", _edge("node_elders", "node_team"), 404),
    # tasks: the eenheid they go into or are in; moving is update + create
    ("viewer", "POST", "/api/tasks", _task("node_team", "team"), 403),
    ("afd_editor", "POST", "/api/tasks", _task("node_directie", "team"), 201),
    ("afd_editor", "POST", "/api/tasks", _task("node_team", "directie"), 403),
    ("team_editor", "POST", "/api/tasks", _task("node_team", "elders"), 403),
    ("team_editor", "PUT", "/api/tasks/{task_team}", {"title": "Ja"}, 200),
    ("team_editor", "PUT", "/api/tasks/{task_team}", _in("afdeling"), 403),
    ("afd_editor", "PUT", "/api/tasks/{task_team}", _in("afdeling"), 200),
    ("afd_editor", "PUT", "/api/tasks/{task_team}", _in("elders"), 403),
    ("afd_editor", "PUT", "/api/tasks/{task_team}", _in("directie"), 403),
    ("team_editor", "PUT", "/api/tasks/{task_elders}", {"title": "Nee"}, 404),
    ("team_editor", "DELETE", "/api/tasks/{task_elders}", None, 404),
    ("team_editor", "DELETE", f"/api/tasks/{_MISSING}", None, 404),
    # leads in an initiatief: initiatief:update to create, lead:update to write
    ("rp_viewer", "GET", L, None, 200),
    ("rp_viewer", "PUT", L, {"title": "Nee"}, 403),
    ("rp_viewer", "POST", "/api/leads", _lead(initiatief_id="{initiatief}"), 403),
    ("role_only", "POST", "/api/leads", _lead(initiatief_id="{initiatief}"), 201),
    ("team_editor", "POST", "/api/leads", _NEW_IN_DIRECTIE, 403),
    ("opdrachtgever", "PUT", L, {"title": "Ja"}, 200),
    ("opdrachtgever", "PUT", "/api/leads/{lead_other}", {"title": "Nee"}, 404),
    ("opdrachtgever", "POST", L + "/move", {"stage": "verkennen"}, 200),
    # a move is lead:delete where it is and lead:create where it goes
    ("team_editor", "PUT", LF, {"initiatief_id": "{initiatief}"}, 403),
    ("afd_editor", "PUT", LF, _INTO_INIT, 403),
    ("manager", "PUT", LF, _INTO_INIT, 200),
    ("afd_editor", "PUT", "/api/leads/{lead_team}", _in("afdeling"), 403),
    ("manager", "PUT", "/api/leads/{lead_team}", _in("afdeling"), 200),
    ("elders_editor", "PUT", "/api/leads/{lead_elders}", _in(None), 403),
    ("super_admin", "PUT", "/api/leads/{lead_elders}", _in(None), 200),
    ("elders_editor", "PUT", "/api/leads/{lead_elders}", _in("team"), 403),
    ("manager", "PUT", "/api/leads/{lead_elders}", _in("team"), 404),
    ("manager", "PUT", L, {"initiatief_id": None}, 422),  # never back to none
    ("role_only", "PUT", L, _in("team"), 200),  # in an initiatief: a label
    # deleting and merging need lead:delete (initiatief:delete)
    ("role_only", "DELETE", "/api/leads/{lead_other}", None, 403),
    ("manager", "DELETE", "/api/leads/{lead_other}", None, 204),
    ("opdrachtgever", "POST", "/api/leads/merge", _merge("lead", "lead_other"), 403),
    ("role_only", "POST", "/api/leads/merge", _merge("lead_other", "lead"), 403),
    ("manager", "POST", "/api/leads/merge", _merge("lead_other", "lead"), 200),
    ("opdrachtgever", "POST", "/api/leads/reorder", _REORDER, 404),
    ("role_only", "POST", "/api/leads/reorder", _REORDER, 200),
    ("team_editor", "POST", LF + "/nodes", {"node_id": "{node_sibling}"}, 404),
    ("team_editor", "POST", LF + "/nodes", {"node_id": "{node_team}"}, 201),
    # lead sub-records; the author deletes their own activity
    ("role_only", "DELETE", L + "/activities/{activity}", None, 204),
    ("opdrachtgever", "DELETE", L + "/activities/{activity}", None, 403),
    ("manager", "DELETE", L + "/activities/{activity}", None, 204),
    ("rp_viewer", "POST", L + "/activities", _NOTE, 403),
    ("opdrachtgever", "POST", L + "/activities", _NOTE, 201),
    ("rp_viewer", "GET", L + "/updates", None, 200),
    ("rp_viewer", "POST", L + "/updates", {"titel": "Nee"}, 403),
    ("opdrachtgever", "POST", L + "/updates", {"titel": "Ja"}, 201),
    ("rp_viewer", "POST", L + "/updates/{post}/publish", None, 403),
    ("opdrachtgever", "POST", L + "/updates/{post}/publish", None, 200),
    ("rp_viewer", "DELETE", L + "/attachments/{attachment}", None, 403),
    ("opdrachtgever", "DELETE", L + "/attachments/{attachment}", None, 204),
    ("rp_viewer", "POST", L + "/github-links", _PR, 403),
    ("opdrachtgever", "POST", L + "/github-links", _PR, 201),
    ("rp_viewer", "DELETE", L + "/github-links/{github_link}", None, 403),
    ("opdrachtgever", "DELETE", L + "/github-links/{github_link}", None, 204),
    # lead contacts are grants: an editor of the lead adds them, opdrachtgever
    # (lead:update) never to yourself; no write access, no grants
    ("role_only", "POST", C, _grant("viewer", "contactpersoon"), 201),
    ("role_only", "POST", C, _grant("role_only", "betrokken"), 201),
    ("role_only", "POST", C, _grant("viewer", "opdrachtgever"), 201),
    ("role_only", "POST", C, _grant("role_only", "opdrachtgever"), 403),
    ("opdrachtgever", "POST", C, _grant("viewer", "opdrachtgever"), 201),
    ("rp_viewer", "POST", C, _grant("viewer", "contactpersoon"), 403),
    ("rp_viewer", "POST", C, _grant("rp_viewer", "opdrachtgever"), 403),
    ("role_only", "POST", C, _grant("viewer", "eigenaar"), 422),
    ("team_editor", "POST", CF, _grant("viewer", "opdrachtgever"), 201),
    ("team_editor", "POST", CF, _grant("team_editor", "opdrachtgever"), 403),
    ("viewer", "POST", CF, _grant("afd_editor", "contactpersoon"), 403),
    ("rp_viewer", "POST", L + "/contacts", {"person_id": "{p_viewer}"}, 403),
    ("role_only", "POST", L + "/contacts", {"person_id": "{p_viewer}"}, 201),
    ("opdrachtgever", "DELETE", L + "/contacts/{opdrachtgever_grant}", None, 204),
    ("role_only", "DELETE", L + "/contacts/{opdrachtgever_grant}", None, 204),
    ("rp_viewer", "DELETE", L + "/contacts/{opdrachtgever_grant}", None, 403),
    ("viewer", "DELETE", L + "/contacts/{opdrachtgever_grant}", None, 403),
    ("rp_viewer", "POST", L + "/tags", {"tag_name": "x"}, 403),
    ("opdrachtgever", "POST", L + "/tags", {"tag_name": "{tag_name}"}, 201),
    ("opdrachtgever", "POST", L + "/tags", {"tag_name": "Gloednieuw"}, 403),
    ("role_only", "POST", L + "/tags", {"tag_name": "Ook nieuw"}, 403),
    ("team_editor", "POST", LF + "/tags", {"tag_name": "Nieuw"}, 201),
    # internal lead edits stay lead:update (public ones: test below)
    ("opdrachtgever", "PUT", L, {"title": "Ander", "public_visible": False}, 200),
    ("opdrachtgever", "POST", L + "/updates", {"titel": "In", "publish": True}, 201),
    ("opdrachtgever", "PUT", L + "/updates/{published}", {"mail_subject": "M"}, 200),
    # the initiatief itself, its posts, columns, subscriptions and channels
    ("rp_viewer", "GET", INIT, None, 200),
    ("platform_admin", "GET", INIT, None, 404),
    ("team_editor", "PUT", INIT, {"naam": "Nee"}, 403),
    ("rp_viewer", "PUT", INIT, {"naam": "Nee"}, 403),
    ("role_only", "PUT", INIT, {"beschrijving": "Ja"}, 200),
    ("partner_member", "PUT", INIT, {"beschrijving": "Ja"}, 200),
    ("afd_editor", "PUT", INIT, {"beschrijving": "Ja"}, 200),
    ("partner_member", "PUT", INIT + "/settings", {"funnel_enabled": True}, 403),
    ("manager", "PUT", INIT + "/settings", {"funnel_enabled": True}, 200),
    ("role_only", "DELETE", INIT, None, 403),
    ("rp_viewer", "POST", INIT + "/updates", {"titel": "Nee"}, 403),
    ("team_editor", "POST", INIT + "/updates", {"titel": "Nee"}, 403),
    ("role_only", "POST", INIT + "/updates", {"titel": "Ja"}, 201),
    ("team_editor", "POST", INIT + "/updates/{init_post}/publish", None, 403),
    ("afd_editor", "POST", INIT + "/updates/{init_post}/publish", None, 200),
    ("afd_editor", "PUT", _WRONG_PARENT, {"titel": "X"}, 404),
    ("afd_editor", "DELETE", INIT + "/updates/{init_post}", None, 204),
    ("rp_viewer", "POST", INIT + "/columns", _COLUMN, 403),
    ("team_editor", "POST", INIT + "/columns", _COLUMN, 403),
    ("role_only", "POST", INIT + "/columns", _COLUMN, 201),
    ("team_editor", "POST", INIT + "/columns/reorder", {"column_ids": []}, 403),
    ("rp_viewer", "POST", INIT + "/abonnementen", {"term": "Nee maar"}, 403),
    ("role_only", "POST", INIT + "/abonnementen", {"term": "Wel degelijk"}, 201),
    ("rp_viewer", "PUT", INIT + "/signaalcontext", {"tekst": "Nee"}, 403),
    ("afd_editor", "PUT", INIT + "/signaalcontext", {"tekst": "Ja"}, 200),
    ("rp_viewer", "POST", INIT + "/mattermost-channels", _channel, 403),
    ("role_only", "POST", INIT + "/mattermost-channels", _channel, 201),
    ("team_editor", "POST", L + "/mattermost-channels", _channel, 403),
    ("afd_editor", "POST", L + "/mattermost-channels", _channel, 201),
    ("rp_viewer", "PATCH", "/api/mattermost-channels/{channel_link}", {}, 403),
    ("afd_editor", "PATCH", "/api/mattermost-channels/{channel_link}", {}, 200),
    ("rp_viewer", "DELETE", "/api/mattermost-channels/{channel_link}", None, 403),
    ("role_only", "DELETE", "/api/mattermost-channels/{channel_link}", None, 204),
    # seeing is not writing: every sub-resource reads
    ("rp_viewer", "GET", INIT + "/columns", None, 200),
    ("rp_viewer", "GET", INIT + "/updates", None, 200),
    ("rp_viewer", "GET", INIT + "/abonnementen", None, 200),
    ("rp_viewer", "GET", INIT + "/signaalcontext", None, 200),
    ("rp_viewer", "GET", INIT + "/mattermost-channels", None, 200),
    ("platform_admin", "GET", INIT + "/abonnementen", None, 404),
    # sharing: org:manage on every source eenheid, system roles for the rest
    ("org_admin", "POST", "/api/sharing", _share("afdeling"), 200),  # below own
    ("org_admin", "POST", "/api/sharing", _share("dg"), 403),  # above it
    ("org_admin", "POST", "/api/sharing", _share("node_team"), 200),
    ("org_admin", "POST", "/api/sharing", _share("node_free"), 403),
    ("super_admin", "POST", "/api/sharing", _share("node_free"), 200),
    ("afd_editor", "POST", "/api/sharing", _share("afdeling"), 403),
    ("org_admin", "DELETE", "/api/sharing/{share}", None, 403),
    ("super_admin", "DELETE", "/api/sharing/{share}", None, 200),
    # opdrachten: every eenheid named, and every one that changes
    ("afd_editor", "POST", "/api/opdrachten", _opdracht(opdrachtgever_id="team"), 201),
    ("afd_editor", "POST", "/api/opdrachten", _OPDR_DIRECTIE, 403),
    ("team_editor", "POST", "/api/opdrachten", _OPDR_TEAM_ELDERS, 403),
    ("team_editor", "POST", "/api/opdrachten", _OPDR_TEAM_TEAM, 201),
    ("afd_editor", "POST", "/api/opdrachten", _koppeling("node_elders"), 404),
    ("afd_editor", "POST", "/api/opdrachten", _koppeling("node_team"), 201),
    ("viewer", "GET", "/api/opdrachten/{opdracht_voor_team}", None, 200),
    ("afd_editor", "PUT", "/api/opdrachten/{opdracht_afdeling}", _TO_DIRECTIE, 403),
    ("afd_editor", "PUT", OD, {"titel": "Nee"}, 403),  # visible, not writable
    ("afd_editor", "POST", "/api/opdrachten/match-contacts-bulk", None, 403),
    ("manager", "PUT", OD, {"opdrachtgever_id": "{eenheid_team}"}, 200),
    ("manager", "PUT", OD, {"opdrachtgever_id": "{eenheid_elders}"}, 403),
    ("manager", "PUT", OD, {"opdrachtnemer_eenheid_id": "{eenheid_elders}"}, 403),
    ("manager", "PUT", OD, {"opdrachtgever_id": None}, 403),  # unscoping: system
    ("super_admin", "PUT", OD, {"opdrachtgever_id": None}, 200),
    ("afd_editor", "PUT", OD, {"opdrachtgever_id": "{eenheid_team}"}, 403),
    # eenheden: org:update (a manager below), org:manage for the modules
    ("manager", "PUT", ORG + "/{eenheid_team}", {"beschrijving": "Ja"}, 200),
    ("manager", "PUT", ORG + "/{eenheid_elders}", {"beschrijving": "Nee"}, 403),
    ("org_admin", "PUT", ORG + "/{eenheid_afdeling}", {"naam": "Nieuw"}, 200),
    ("org_admin", "PUT", ORG + "/{eenheid_dg}", {"naam": "Nee"}, 403),
    ("team_editor", "PUT", ORG + "/{eenheid_team}", {"naam": "Nee"}, 403),
    ("team_editor", "DELETE", ORG + "/{eenheid_team}", None, 403),
    ("eenheid_eigenaar", "PUT", ORG + "/{eenheid_elders}", {"naam": "Eigen"}, 200),
    ("org_admin", "PUT", "/api/eenheid-modules/{eenheid_team}", _MODULE, 200),
    ("org_admin", "PUT", "/api/eenheid-modules/{eenheid_elders}", _MODULE, 403),
    ("manager", "PUT", "/api/eenheid-modules/{eenheid_team}", _MODULE, 403),
    # tenant-wide vocabularies and people
    ("team_editor", "PUT", "/api/tags/{tag}", {"name": "hernoemd"}, 200),
    ("viewer", "PUT", "/api/tags/{tag}", {"name": "nee"}, 403),
    ("viewer", "POST", "/api/tags", {"name": "nee"}, 403),
    ("team_editor", "PUT", SWV, {"naam": "Ja"}, 200),
    ("team_editor", "DELETE", SWV, None, 403),
    ("viewer", "POST", SWV + "/leden", {"person_id": "{p_viewer}"}, 403),
    ("role_only", "POST", "/api/people", {"naam": "Geen rol"}, 403),
    # stakeholder assessments follow their scope
    ("team_editor", "POST", SA, _assessment("node_team"), 201),
    ("team_editor", "POST", SA, _assessment("node_directie"), 403),
    ("team_editor", "PUT", SA + "/{sa_directie}", {"belang": 1}, 403),
    ("team_editor", "DELETE", SA + "/{sa_team}", None, 204),
]  # fmt: skip


@pytest.mark.parametrize("case", ROUTES, ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in ROUTES])
async def test_routes(ww, case):
    await assert_route_case(ww, *case)


# (method, path, body, status when allowed): the public face of a lead
PUBLIC = [
    ("PUT", L, {"public_visible": True}, 200),
    ("PUT", L, {"public_title": "Casus"}, 200),
    ("PUT", L, {"public_summary": "Kort"}, 200),
    ("POST", L + "/updates", {"titel": "N", "body_public": "P", "publish": True}, 201),
    ("POST", L + "/updates/{public_post}/publish", None, 200),
    ("PUT", L + "/updates/{published}", {"body_public": "Nieuw"}, 200),
]  # fmt: skip


@pytest.mark.parametrize("who", ["opdrachtgever", "role_only"])
@pytest.mark.parametrize(("method", "path", "body", "allowed"), PUBLIC)
async def test_only_the_initiatief_puts_a_lead_on_its_public_page(
    ww, who, method, path, body, allowed
):
    """Public fields and public post texts need initiatief:update."""
    expected = 403 if who == "opdrachtgever" else allowed
    await assert_route_case(ww, who, method, path, body, expected)


# Records linked from a task body must be usable: (extra fields, status)
TASK_LINKS = [
    ({}, 201),
    ({"node_id": "{node_sibling}"}, 404),  # a node you do not see
    ({"opdracht_id": "{opdracht_elders}"}, 404),  # an opdracht you do not see
    ({"opdracht_id": "{opdracht_directie}"}, 201),
    ({"parent_id": "{task_team}"}, 201),  # a parent you may update
    ({"parent_id": "{task_directie}"}, 403),  # one you may only see
    ({"parlementair_item_id": "{item}"}, 201),
    ({"parlementair_item_id": str(_MISSING)}, 404),
]


@pytest.mark.parametrize(("extra", "expected"), TASK_LINKS)
async def test_task_body_links_are_checked(ww, extra, expected):
    body = _task("node_team", "team") | extra
    created = await request(ww, "team_editor", "POST", "/api/tasks", body)
    updated = await request(ww, "team_editor", "PUT", "/api/tasks/{task_team}", extra)
    assert created.status_code == expected, created.text
    assert updated.status_code == (200 if expected == 201 else expected), updated.text


async def test_refused_new_tag_is_not_created(ww):
    resp = await request(
        ww, "opdrachtgever", "POST", L + "/tags", {"tag_name": "Gloed"}
    )
    assert resp.status_code == 403, resp.text
    assert "Gloed" not in set((await ww.db.scalars(select(Tag.name))).all())


# (who, eenheid the new lead lands in, None when refused)
WITHOUT_PLACE = [
    ("team_editor", "team"),
    ("afd_editor", "afdeling"),
    ("viewer", None),  # an implicit viewer creates no leads
    ("role_only", None),  # a contributor creates leads in the initiatief only
    ("super_admin", "tenant-wide"),  # no placement: a system role may
]


@pytest.mark.parametrize(("who", "lands_in"), WITHOUT_PLACE)
async def test_new_lead_without_place_lands_in_own_eenheid(world, who, lands_in):
    """POST /leads without place, and ``lead:create`` anywhere, agree."""
    [asked] = await evaluate(world, who, ask("lead:create", "lead", anywhere=True))
    created = await request(world, who, "POST", "/api/leads", _lead("inbox"))
    assert asked is (lands_in is not None)
    if lands_in is None:
        assert created.status_code == 403, created.text
        return
    assert created.status_code == 201, created.text
    expected = None if lands_in == "tenant-wide" else str(world.org[lands_in].id)
    assert created.json()["organisatie_eenheid_id"] == expected


@pytest.mark.parametrize(
    ("team_start", "sibling_start", "lands_in"),
    [
        (date(2020, 1, 1), date(2024, 1, 1), "team"),  # longest-running first
        (date(2024, 1, 1), date(2020, 1, 1), "sibling_team"),
        (date(2022, 1, 1), date(2022, 1, 1), "sibling_team"),  # tie: by naam
    ],
)
async def test_new_lead_lands_in_longest_running_placement(
    world, team_start, sibling_start, lands_in
):
    """Several placements: the oldest one wins, over REST and in chat alike."""
    person = await make_person(world.db, "Dubbel geplaatst")
    for key, start in (("team", team_start), ("sibling_team", sibling_start)):
        (await place(world.db, person, world.org[key])).start_datum = start
        await grant_role(world.db, person, "editor", world.org[key])
    await world.db.flush()
    world.person["dubbel"] = person
    created = await request(world, "dubbel", "POST", "/api/leads", _lead("inbox"))
    assert created.status_code == 201, created.text
    expected = world.org[lands_in].id
    assert created.json()["organisatie_eenheid_id"] == str(expected)
    data = LeadCreate(title="Via chat")  # chat's create_lead, same rule
    await require_lead_create(world.db, await perm_ctx(world, "dubbel"), data)
    assert data.organisatie_eenheid_id == expected


async def test_moving_a_lead_into_own_new_initiatief_needs_lead_delete(ww):
    """An editor of the team may update its lead, not take it away.

    Starting a personal initiatief makes you its eigenaar (lead:create
    there), but moving the team's lead into it deletes it from the team.
    """
    created = await request(
        ww, "team_editor", "POST", "/api/initiatieven", {"naam": "Eigen initiatief"}
    )
    assert created.status_code == 201, created.text
    body = {"initiatief_id": created.json()["id"], "stage": "verkennen"}
    moved = await request(ww, "team_editor", "PUT", "/api/leads/{lead_team}", body)
    assert moved.status_code == 403, moved.text
    lead = await ww.db.get(Lead, ww.res["lead_team"])
    await ww.db.refresh(lead)
    assert lead.initiatief_id is None


@pytest.mark.parametrize(("who", "expected"), [("manager", 403), ("super_admin", 200)])
async def test_merge_moves_a_grant_to_an_agent_only_for_super_admin(ww, who, expected):
    """An agent acts on what it holds: a moved grant hands it the target."""
    agent = await make_agent(ww)
    await add(ww, rp("lead", ww.res["lead_other"], "opdrachtgever", person=agent))
    body = _merge("lead_other", "lead")
    await assert_route_case(ww, who, "POST", "/api/leads/merge", body, expected)


async def test_merge_keeps_an_eenheid_grant_next_to_other_grants(ww):
    """Only the same holder with the same rol is a duplicate."""
    await add(
        ww,
        rp("lead", ww.res["lead_other"], "betrokken", eenheid=ww.org["team"]),
        rp("lead", ww.res["lead"], "betrokken", eenheid=ww.org["elders"]),
    )
    body = _merge("lead_other", "lead")
    await assert_route_case(ww, "manager", "POST", "/api/leads/merge", body, 200)
    holders = await ww.db.scalars(
        select(ResourcePermission.organisatie_eenheid_id).where(
            ResourcePermission.resource_type == "lead",
            ResourcePermission.resource_id == ww.res["lead"],
            ResourcePermission.organisatie_eenheid_id.isnot(None),
        )
    )
    assert set(holders.all()) == {ww.org["team"].id, ww.org["elders"].id}


async def test_create_initiatief_grants_only_the_creator(world):
    """Creation is allowlisted: the payload must not carry any other grant."""
    payload = {
        "naam": f"Eigen {uuid.uuid4().hex[:6]}", "created_by_id": "{p_team_editor}",
        "members": [{"person_id": "{p_team_editor}", "rol": "eigenaar"}],
        "eenheden": [{"eenheid_id": "{eenheid_ministerie}", "rol": "eigenaar"}],
        "access_level": "eigenaar", "slug": "gekaapt",
        "public_page_enabled": True, "funnel_enabled": True,
    }  # fmt: skip
    resp = await request(world, "viewer", "POST", "/api/initiatieven", payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] != "gekaapt"
    assert body["public_page_enabled"] is False and body["funnel_enabled"] is False
    grants = await world.db.execute(
        select(
            ResourcePermission.person_id,
            ResourcePermission.organisatie_eenheid_id,
            ResourcePermission.rol,
        ).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == uuid.UUID(body["id"]),
        )
    )
    assert grants.all() == [(world.person["viewer"].id, None, "eigenaar")]


async def test_initiatief_detail_does_not_expose_access_level(iw):
    resp = await request(iw, "rp_viewer", "GET", "/api/initiatieven/{initiatief}")
    assert resp.status_code == 200, resp.text
    assert "access_level" not in resp.json()


@pytest.mark.parametrize(
    ("method", "node", "expected"),
    [("POST", "node_team", 201), ("POST", "node_directie", 403),
     ("DELETE", "node_directie", 403)],
)  # fmt: skip
async def test_bijlage_needs_node_update_on_the_node(ww, method, node, expected):
    pdf = ("bijlage.pdf", b"%PDF-1.4\n%test\n", "application/pdf")
    files = {"files": {"file": pdf}} if method == "POST" else {}
    path = f"/api/nodes/{{{node}}}/bijlage"
    resp = await request(ww, "team_editor", method, path, **files)
    assert resp.status_code == expected, resp.text


# Chat write tools ask the same question: (tool, args, allowed for team_editor)
CHAT = [
    ("update_node", {"node_id": "{node_directie}", "title": "Nee"}, False),
    ("update_node", {"node_id": "{node_team}", "title": "Ja"}, True),
    ("create_edge", {"from_node_id": "{node_directie}", "to_node_id": "{node_team}",
                     "edge_type_id": "x"}, True),
    ("create_task", {"node_id": "{node_directie}", "title": "Nee"}, False),
]  # fmt: skip


@pytest.mark.parametrize(("tool", "args", "allowed"), CHAT)
async def test_chat_write_tools_ask_authz(world, tool, args, allowed):
    refusal = await chat_refusal(world, "team_editor", tool, args)
    assert (refusal is None) is allowed, refusal
