"""Leads on the single decision point (``core/authz.py``).

Builds on the tree of ``test_authz.world``: the afdeling owns the
initiatief, ``role_only`` is a contributor on it, the manager of the
directie above holds unit_manager.  Added here: a person who may only read
the initiatief, a lead opdrachtgever, and sub-records of the lead.
"""

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.core.initiatief_context import build_initiatief_context
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.resource_permission import ResourcePermission
from tests.factories import client_as, make_person
from tests.test_authz import World, _ctx, world  # noqa: F401 (fixture)


@dataclass
class LeadsWorld:
    w: World

    def id(self, key: str) -> uuid.UUID:
        if key in self.w.res:
            return self.w.res[key]
        return self.w.org[key].id


@pytest.fixture
async def lw(world: World) -> LeadsWorld:  # noqa: F811
    db = world.db
    init_viewer = await make_person(db, "Initiatieflezer")
    opdrachtgever = await make_person(db, "Opdrachtgever")
    initiatief = world.res["initiatief"]

    lead_other = Lead(title="Andere lead", stage="verkennen", initiatief_id=initiatief)
    lead_team = Lead(
        title="Teamlead", stage="verkennen", organisatie_eenheid_id=world.org["team"].id
    )
    db.add_all([lead_other, lead_team])
    await db.flush()
    lead = world.res["lead"]
    opdrachtgever_grant = ResourcePermission(
        person_id=opdrachtgever.id,
        resource_type="lead",
        resource_id=lead,
        rol="opdrachtgever",
    )
    db.add_all(
        [
            ResourcePermission(
                person_id=init_viewer.id,
                resource_type="initiatief",
                resource_id=initiatief,
                rol="viewer",
            ),
            opdrachtgever_grant,
        ]
    )
    activity = LeadActivity(
        lead_id=lead,
        content="Notitie",
        activity_type="note",
        author_id=world.person["role_only"].id,
    )
    post = LeadUpdatePost(lead_id=lead, titel="Update")
    attachment = LeadAttachment(lead_id=lead, soort="link", url="https://example.com")
    link = GitHubLink(
        scope_type=SCOPE_LEAD,
        scope_id=lead,
        url="https://github.com/foo/bar/pull/1",
        link_type="pull_request",
        owner="foo",
        repo="bar",
    )
    db.add_all([activity, post, attachment, link])
    await db.flush()

    world.person.update(init_viewer=init_viewer, opdrachtgever=opdrachtgever)
    world.res.update(
        lead_other=lead_other.id,
        lead_team=lead_team.id,
        activity=activity.id,
        post=post.id,
        attachment=attachment.id,
        github_link=link.id,
        opdrachtgever_grant=opdrachtgever_grant.id,
    )
    return LeadsWorld(world)


# (who, permission, resource type, resource key or None, eenheid key, expected)
CASES = [
    # an initiatief viewer sees its leads but cannot write them
    ("init_viewer", "lead:read", "lead", "lead", None, True),
    ("init_viewer", "lead:update", "lead", "lead", None, False),
    ("init_viewer", "lead:create", "initiatief", "initiatief", None, False),
    # a contributor writes leads in the initiatief, but deletes none
    ("role_only", "lead:update", "lead", "lead_other", None, True),
    ("role_only", "lead:create", "initiatief", "initiatief", None, True),
    ("role_only", "lead:delete", "lead", "lead", None, False),
    # deleting a lead in an initiatief is initiatief:delete
    ("manager", "lead:delete", "lead", "lead", None, True),
    ("team_editor", "lead:update", "lead", "lead", None, False),
    # the opdrachtgever writes their own lead only
    ("opdrachtgever", "lead:update", "lead", "lead", None, True),
    ("opdrachtgever", "lead:delete", "lead", "lead", None, False),
    ("opdrachtgever", "lead:update", "lead", "lead_other", None, False),
    ("opdrachtgever", "lead:update", "lead", "lead_free", None, False),
    # a lead without initiatief and eenheid: tenant-wide rule
    ("team_editor", "lead:update", "lead", "lead_free", None, True),
    ("viewer", "lead:update", "lead", "lead_free", None, False),
    ("init_viewer", "lead:update", "lead", "lead_free", None, False),
    ("team_editor", "lead:delete", "lead", "lead_free", None, False),
    ("manager", "lead:delete", "lead", "lead_free", None, True),
    ("team_editor", "lead:create", "lead", None, None, True),
    ("viewer", "lead:create", "lead", None, None, False),
    # a lead without initiatief but with an eenheid follows that eenheid
    ("team_editor", "lead:update", "lead", "lead_team", None, True),
    ("afd_editor", "lead:update", "lead", "lead_team", None, True),
    ("viewer", "lead:update", "lead", "lead_team", None, False),
    ("team_editor", "lead:create", "lead", None, "team", True),
    ("team_editor", "lead:create", "lead", None, "directie", False),
    # sub-records are decided on their lead
    ("opdrachtgever", "lead_update:update", "lead_update", "post", None, True),
    ("init_viewer", "lead_update:update", "lead_update", "post", None, False),
    ("opdrachtgever", "lead_activity:delete", "lead_activity", "activity", None, True),
    ("viewer", "lead_activity:delete", "lead_activity", "activity", None, False),
    (
        "role_only",
        "lead_attachment:delete",
        "lead_attachment",
        "attachment",
        None,
        True,
    ),
    (
        "init_viewer",
        "lead_attachment:delete",
        "lead_attachment",
        "attachment",
        None,
        False,
    ),
    ("opdrachtgever", "github_link:delete", "github_link", "github_link", None, True),
    ("team_editor", "github_link:delete", "github_link", "github_link", None, False),
    ("opdrachtgever", "github_link:create", "lead", "lead", None, True),
    ("init_viewer", "github_link:create", "lead", "lead", None, False),
]


@pytest.mark.parametrize(
    ("who", "permission", "resource_type", "resource", "eenheid", "expected"),
    CASES,
    ids=[f"{c[0]}-{c[1]}-{c[3] or c[4] or 'new'}" for c in CASES],
)
async def test_can(lw, who, permission, resource_type, resource, eenheid, expected):
    ctx = await _ctx(lw.w, who)
    got = await can(
        lw.w.db,
        ctx,
        permission,
        resource_type,
        lw.id(resource) if resource else None,
        eenheid_id=lw.id(eenheid) if eenheid else None,
    )
    assert got is expected


async def test_initiatief_viewer_sees_but_does_not_write(lw):
    person = lw.w.person["init_viewer"]
    init_ctx = await build_initiatief_context(lw.w.db, person)
    assert lw.id("initiatief") in init_ctx.visible_initiatief_ids
    async with client_as(lw.w.db, person) as c:
        read = await c.get(f"/api/leads/{lw.id('lead')}")
        write = await c.put(f"/api/leads/{lw.id('lead')}", json={"title": "Nee"})
    assert read.status_code == 200, read.text
    assert write.status_code == 403


def _lead_body(**extra) -> dict:
    return {"title": "Nieuwe lead", "stage": "verkennen", **extra}


# (who, method, path, body builder or None, expected status)
ROUTES = [
    # create: in an initiatief needs initiatief:update there
    (
        "init_viewer",
        "POST",
        "/api/leads",
        lambda lw: _lead_body(initiatief_id=str(lw.id("initiatief"))),
        403,
    ),
    (
        "role_only",
        "POST",
        "/api/leads",
        lambda lw: _lead_body(initiatief_id=str(lw.id("initiatief"))),
        201,
    ),
    # create without initiatief: tenant-wide, or the eenheid it goes into
    ("viewer", "POST", "/api/leads", lambda lw: _lead_body(stage="inbox"), 403),
    (
        "team_editor",
        "POST",
        "/api/leads",
        lambda lw: _lead_body(stage="inbox"),
        201,
    ),
    (
        "team_editor",
        "POST",
        "/api/leads",
        lambda lw: _lead_body(
            stage="inbox", organisatie_eenheid_id=str(lw.id("directie"))
        ),
        403,
    ),
    # update and move
    ("opdrachtgever", "PUT", "/api/leads/{lead}", lambda lw: {"title": "Ja"}, 200),
    (
        "opdrachtgever",
        "PUT",
        "/api/leads/{lead_other}",
        lambda lw: {"title": "Nee"},
        403,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/{lead}/move",
        lambda lw: {"stage": "verkennen"},
        200,
    ),
    # moving a lead into an initiatief needs write access there too
    (
        "team_editor",
        "PUT",
        "/api/leads/{lead_free}",
        lambda lw: {"initiatief_id": str(lw.id("initiatief"))},
        403,
    ),
    (
        "afd_editor",
        "PUT",
        "/api/leads/{lead_free}",
        lambda lw: {"initiatief_id": str(lw.id("initiatief")), "stage": "verkennen"},
        200,
    ),
    # delete: initiatief:delete for a lead in an initiatief
    ("role_only", "DELETE", "/api/leads/{lead_other}", None, 403),
    ("manager", "DELETE", "/api/leads/{lead_other}", None, 204),
    # merge and reorder need write access on every lead
    (
        "opdrachtgever",
        "POST",
        "/api/leads/merge",
        lambda lw: {
            "source_id": str(lw.id("lead")),
            "target_id": str(lw.id("lead_other")),
        },
        403,
    ),
    (
        "role_only",
        "POST",
        "/api/leads/merge",
        lambda lw: {
            "source_id": str(lw.id("lead_other")),
            "target_id": str(lw.id("lead")),
        },
        200,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/reorder",
        lambda lw: {
            "lead_ids": [str(lw.id("lead")), str(lw.id("lead_other"))],
            "stage": "verkennen",
        },
        403,
    ),
    (
        "role_only",
        "POST",
        "/api/leads/reorder",
        lambda lw: {
            "lead_ids": [str(lw.id("lead")), str(lw.id("lead_other"))],
            "stage": "verkennen",
        },
        200,
    ),
    # activities: the author deletes their own, others need lead:delete
    ("role_only", "DELETE", "/api/leads/{lead}/activities/{activity}", None, 204),
    ("opdrachtgever", "DELETE", "/api/leads/{lead}/activities/{activity}", None, 403),
    ("manager", "DELETE", "/api/leads/{lead}/activities/{activity}", None, 204),
    (
        "init_viewer",
        "POST",
        "/api/leads/{lead}/activities",
        lambda lw: {"content": "Nee", "activity_type": "note"},
        403,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/{lead}/activities",
        lambda lw: {"content": "Ja", "activity_type": "note"},
        201,
    ),
    # update posts, attachments, github links, contacts, tags via the lead
    ("init_viewer", "GET", "/api/leads/{lead}/updates", None, 200),
    (
        "init_viewer",
        "POST",
        "/api/leads/{lead}/updates",
        lambda lw: {"titel": "Nee"},
        403,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/{lead}/updates",
        lambda lw: {"titel": "Ja"},
        201,
    ),
    ("init_viewer", "POST", "/api/leads/{lead}/updates/{post}/publish", None, 403),
    ("opdrachtgever", "POST", "/api/leads/{lead}/updates/{post}/publish", None, 200),
    ("init_viewer", "DELETE", "/api/leads/{lead}/attachments/{attachment}", None, 403),
    (
        "opdrachtgever",
        "DELETE",
        "/api/leads/{lead}/attachments/{attachment}",
        None,
        204,
    ),
    (
        "init_viewer",
        "POST",
        "/api/leads/{lead}/github-links",
        lambda lw: {"url": "https://github.com/foo/bar/pull/2"},
        403,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/{lead}/github-links",
        lambda lw: {"url": "https://github.com/foo/bar/pull/2"},
        201,
    ),
    (
        "init_viewer",
        "DELETE",
        "/api/leads/{lead}/github-links/{github_link}",
        None,
        403,
    ),
    (
        "opdrachtgever",
        "DELETE",
        "/api/leads/{lead}/github-links/{github_link}",
        None,
        204,
    ),
    (
        "init_viewer",
        "POST",
        "/api/leads/{lead}/contacts",
        lambda lw: {"person_id": str(lw.w.person["viewer"].id)},
        403,
    ),
    (
        "role_only",
        "POST",
        "/api/leads/{lead}/contacts",
        lambda lw: {"person_id": str(lw.w.person["viewer"].id)},
        201,
    ),
    (
        "init_viewer",
        "POST",
        "/api/leads/{lead}/tags",
        lambda lw: {"tag_name": "x"},
        403,
    ),
]


@pytest.mark.parametrize(
    ("who", "method", "path", "body", "expected"),
    ROUTES,
    ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in ROUTES],
)
async def test_routes(lw, who, method, path, body, expected):
    url = path.format(**{k: lw.w.res[k] for k in lw.w.res})
    kwargs = {"json": body(lw)} if body else {}
    async with client_as(lw.w.db, lw.w.person[who]) as c:
        resp = await c.request(method, url, **kwargs)
    assert resp.status_code == expected, resp.text


async def test_leads_of_one_initiatief_share_one_decision(lw):
    """Reorder asks per lead; the per-request cache decides the initiatief once."""
    ctx = await _ctx(lw.w, "role_only")
    for key in ("lead", "lead_other"):
        assert await can(lw.w.db, ctx, "lead:update", "lead", lw.id(key))
    decisions = [
        k for k in ctx.authz_cache if k[0] == "decision" and k[1] == "initiatief:update"
    ]
    assert len(decisions) == 1


async def _decision_queries(lw, who: str, n: int) -> int:
    """Queries spent deciding lead:update on *n* leads of one initiatief."""
    from sqlalchemy import event

    db = lw.w.db
    leads = [
        Lead(title=f"Lead {i}", stage="verkennen", initiatief_id=lw.id("initiatief"))
        for i in range(n)
    ]
    db.add_all(leads)
    await db.flush()
    ctx = await _ctx(lw.w, who)
    count = 0

    def _count(_state):
        nonlocal count
        count += 1

    event.listen(db.sync_session, "do_orm_execute", _count)
    try:
        for lead in leads:
            assert await can(db, ctx, "lead:update", "lead", lead.id)
    finally:
        event.remove(db.sync_session, "do_orm_execute", _count)
    return count


@pytest.mark.parametrize("who", ["role_only", "afd_editor"])
async def test_reorder_decision_costs_constant_queries(lw, who):
    """Owner eenheden and resource roles are looked up once, not per lead."""
    few = await _decision_queries(lw, who, 2)
    many = await _decision_queries(lw, who, 12)
    assert many == few


# Lead contacts are grants: (who, lead key, contact, rol, expected status)
CONTACT_GRANTS = [
    # an editor of the lead adds contacts, themselves included
    ("role_only", "lead", "viewer", "contactpersoon", 201),
    ("role_only", "lead", "role_only", "betrokken", 201),
    # opdrachtgever gives lead:update: an editor hands it out, not to themselves
    ("role_only", "lead", "viewer", "opdrachtgever", 201),
    ("role_only", "lead", "role_only", "opdrachtgever", 403),
    ("opdrachtgever", "lead", "viewer", "opdrachtgever", 201),
    # no write access, no grants
    ("init_viewer", "lead", "viewer", "contactpersoon", 403),
    ("init_viewer", "lead", "init_viewer", "opdrachtgever", 403),
    # only the lead's own rols
    ("role_only", "lead", "viewer", "eigenaar", 422),
    # a lead without initiatief and eenheid: the tenant-wide editors decide
    ("team_editor", "lead_free", "viewer", "opdrachtgever", 201),
    ("team_editor", "lead_free", "team_editor", "opdrachtgever", 403),
    ("viewer", "lead_free", "afd_editor", "contactpersoon", 403),
]


@pytest.mark.parametrize(
    ("who", "lead", "contact", "rol", "expected"),
    CONTACT_GRANTS,
    ids=[f"{c[0]}-{c[3]}-for-{c[2]}-on-{c[1]}" for c in CONTACT_GRANTS],
)
async def test_contact_is_a_grant(lw, who, lead, contact, rol, expected):
    body = {"person_id": str(lw.w.person[contact].id), "rol": rol}
    async with client_as(lw.w.db, lw.w.person[who]) as c:
        resp = await c.post(f"/api/leads/{lw.id(lead)}/contacts", json=body)
    assert resp.status_code == expected, resp.text


async def test_tagging_with_a_new_name_needs_tag_create(lw):
    """The opdrachtgever edits the lead but holds no tag:create anywhere."""
    from bouwmeester.models.tag import Tag

    lw.w.db.add(Tag(name="Bestaande tag"))
    await lw.w.db.flush()
    url = f"/api/leads/{lw.id('lead')}/tags"
    async with client_as(lw.w.db, lw.w.person["opdrachtgever"]) as c:
        new = await c.post(url, json={"tag_name": "Gloednieuw"})
        existing = await c.post(url, json={"tag_name": "Bestaande tag"})
    async with client_as(lw.w.db, lw.w.person["role_only"]) as c:
        # a contributor on the initiatief holds no tag:create either
        contributor_new = await c.post(url, json={"tag_name": "Ook nieuw"})
    async with client_as(lw.w.db, lw.w.person["team_editor"]) as c:
        editor_new = await c.post(
            f"/api/leads/{lw.id('lead_free')}/tags", json={"tag_name": "Nieuw"}
        )
    assert new.status_code == 403, new.text
    assert existing.status_code == 201, existing.text
    assert contributor_new.status_code == 403, contributor_new.text
    assert editor_new.status_code == 201, editor_new.text
    names = set((await lw.w.db.scalars(select(Tag.name))).all())
    assert "Gloednieuw" not in names and "Nieuw" in names


@pytest.mark.parametrize(
    ("who", "expected"),
    [
        ("opdrachtgever", 204),  # leaving yourself
        ("role_only", 204),  # an editor removes someone else's grant
        ("init_viewer", 403),
        ("viewer", 403),
    ],
)
async def test_remove_contact_is_a_grant_change(lw, who, expected):
    url = f"/api/leads/{lw.id('lead')}/contacts/{lw.id('opdrachtgever_grant')}"
    async with client_as(lw.w.db, lw.w.person[who]) as c:
        resp = await c.delete(url)
    assert resp.status_code == expected, resp.text
