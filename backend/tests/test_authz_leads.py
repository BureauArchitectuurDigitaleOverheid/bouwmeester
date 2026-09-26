"""Leads on the single decision point (``core/authz.py``).

Uses ``world`` from ``tests/authz_world.py``: the afdeling owns the
initiatief, ``role_only`` is a contributor on it, the manager of the
directie above holds unit_manager.  Added here: a person who may only read
the initiatief, a lead opdrachtgever, and sub-records of the lead.
"""

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import can, prefetch
from bouwmeester.core.initiatief_context import build_initiatief_context
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.resource_permission import ResourcePermission
from tests.authz_world import (
    World,
    ask,
    assert_can_case,
    assert_route_case,
    can_case_id,
    perm_ctx,
    route_case_id,
)
from tests.factories import client_as, make_person


@pytest.fixture
async def lw(world: World) -> World:
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
    return world


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
    # creating one that lives nowhere: system roles only (without a place
    # the route puts a new lead in the caller's own eenheid)
    ("team_editor", "lead:create", "lead", None, None, False),
    ("viewer", "lead:create", "lead", None, None, False),
    ("super_admin", "lead:create", "lead", None, None, True),
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


@pytest.mark.parametrize("case", CASES, ids=[can_case_id(c) for c in CASES])
async def test_can(lw, case):
    await assert_can_case(lw, case)


async def test_initiatief_viewer_sees_but_does_not_write(lw):
    person = lw.person["init_viewer"]
    init_ctx = await build_initiatief_context(lw.db, person)
    assert lw.id("initiatief") in init_ctx.visible_initiatief_ids
    async with client_as(lw.db, person) as c:
        read = await c.get(f"/api/leads/{lw.id('lead')}")
        write = await c.put(f"/api/leads/{lw.id('lead')}", json={"title": "Nee"})
    assert read.status_code == 200, read.text
    assert write.status_code == 403


# (who, eenheid the lead lands in or None for tenant-wide, None when refused)
WITHOUT_PLACE = [
    ("team_editor", "team"),
    ("afd_editor", "afdeling"),
    ("viewer", None),  # an implicit viewer creates no leads
    ("role_only", None),  # a contributor creates leads in the initiatief only
    ("super_admin", "tenant-wide"),  # no placement: a system role may
]


@pytest.mark.parametrize(("who", "lands_in"), WITHOUT_PLACE)
async def test_new_lead_without_place_lands_in_own_eenheid(lw, who, lands_in):
    """POST /leads without place, and ``lead:create`` anywhere, agree."""
    async with client_as(lw.db, lw.person[who]) as c:
        asked = await c.post(
            "/api/authz/evaluations",
            json={"evaluations": [ask("lead:create", "lead", anywhere=True)]},
        )
        created = await c.post("/api/leads", json=_lead_body(stage="inbox"))
    assert asked.json()["evaluations"][0]["decision"] is (lands_in is not None)
    if lands_in is None:
        assert created.status_code == 403, created.text
        return
    assert created.status_code == 201, created.text
    expected = None if lands_in == "tenant-wide" else str(lw.org[lands_in].id)
    assert created.json()["organisatie_eenheid_id"] == expected


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
    # create without initiatief: in the eenheid it goes into (none given:
    # the own eenheid, see test_new_lead_without_place_lands_in_own_eenheid)
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
    # a lead the opdrachtgever cannot see answers as missing
    (
        "opdrachtgever",
        "PUT",
        "/api/leads/{lead_other}",
        lambda lw: {"title": "Nee"},
        404,
    ),
    (
        "opdrachtgever",
        "POST",
        "/api/leads/{lead}/move",
        lambda lw: {"stage": "verkennen"},
        200,
    ),
    # a lead without initiatief moves with lead:update where it is and
    # lead:create where it goes
    (
        "team_editor",  # updates lead_free, may not create in the initiatief
        "PUT",
        "/api/leads/{lead_free}",
        lambda lw: {"initiatief_id": str(lw.id("initiatief"))},
        403,
    ),
    (
        "afd_editor",  # updates lead_free and creates in the initiatief
        "PUT",
        "/api/leads/{lead_free}",
        lambda lw: {"initiatief_id": str(lw.id("initiatief")), "stage": "verkennen"},
        200,
    ),
    (
        "manager",
        "PUT",
        "/api/leads/{lead_free}",
        lambda lw: {"initiatief_id": str(lw.id("initiatief")), "stage": "verkennen"},
        200,
    ),
    # a lead in an initiatief never goes back to none
    (
        "manager",
        "PUT",
        "/api/leads/{lead}",
        lambda lw: {"initiatief_id": None},
        422,
    ),
    # in an initiatief the eenheid is a label, changing it moves nothing
    (
        "role_only",
        "PUT",
        "/api/leads/{lead}",
        lambda lw: {"organisatie_eenheid_id": str(lw.id("team"))},
        200,
    ),
    # delete: initiatief:delete for a lead in an initiatief
    ("role_only", "DELETE", "/api/leads/{lead_other}", None, 403),
    ("manager", "DELETE", "/api/leads/{lead_other}", None, 204),
    # merge deletes the source (lead:delete) and writes the target
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
        "role_only",  # a contributor writes both leads but deletes none
        "POST",
        "/api/leads/merge",
        lambda lw: {
            "source_id": str(lw.id("lead_other")),
            "target_id": str(lw.id("lead")),
        },
        403,
    ),
    (
        "manager",
        "POST",
        "/api/leads/merge",
        lambda lw: {
            "source_id": str(lw.id("lead_other")),
            "target_id": str(lw.id("lead")),
        },
        200,
    ),
    (
        "opdrachtgever",  # lead_other is not visible to them
        "POST",
        "/api/leads/reorder",
        lambda lw: {
            "lead_ids": [str(lw.id("lead")), str(lw.id("lead_other"))],
            "stage": "verkennen",
        },
        404,
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
        lambda lw: {"person_id": str(lw.person["viewer"].id)},
        403,
    ),
    (
        "role_only",
        "POST",
        "/api/leads/{lead}/contacts",
        lambda lw: {"person_id": str(lw.person["viewer"].id)},
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


@pytest.mark.parametrize("case", ROUTES, ids=[route_case_id(c) for c in ROUTES])
async def test_routes(lw, case):
    await assert_route_case(lw, *case)


async def _decision_queries(lw, who: str, n: int) -> int:
    """Queries spent deciding lead:update on *n* leads of one initiatief."""
    from sqlalchemy import event

    db = lw.db
    leads = [
        Lead(title=f"Lead {i}", stage="verkennen", initiatief_id=lw.id("initiatief"))
        for i in range(n)
    ]
    db.add_all(leads)
    await db.flush()
    ctx = await perm_ctx(lw, who)
    count = 0

    def _count(_state):
        nonlocal count
        count += 1

    event.listen(db.sync_session, "do_orm_execute", _count)
    try:
        await prefetch(db, ctx, "lead", [lead.id for lead in leads])
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
    body = {"person_id": str(lw.person[contact].id), "rol": rol}
    async with client_as(lw.db, lw.person[who]) as c:
        resp = await c.post(f"/api/leads/{lw.id(lead)}/contacts", json=body)
    assert resp.status_code == expected, resp.text


async def test_tagging_with_a_new_name_needs_tag_create(lw):
    """The opdrachtgever edits the lead but holds no tag:create anywhere."""
    from bouwmeester.models.tag import Tag

    lw.db.add(Tag(name="Bestaande tag"))
    await lw.db.flush()
    url = f"/api/leads/{lw.id('lead')}/tags"
    async with client_as(lw.db, lw.person["opdrachtgever"]) as c:
        new = await c.post(url, json={"tag_name": "Gloednieuw"})
        existing = await c.post(url, json={"tag_name": "Bestaande tag"})
    async with client_as(lw.db, lw.person["role_only"]) as c:
        # a contributor on the initiatief holds no tag:create either
        contributor_new = await c.post(url, json={"tag_name": "Ook nieuw"})
    async with client_as(lw.db, lw.person["team_editor"]) as c:
        editor_new = await c.post(
            f"/api/leads/{lw.id('lead_free')}/tags", json={"tag_name": "Nieuw"}
        )
    assert new.status_code == 403, new.text
    assert existing.status_code == 201, existing.text
    assert contributor_new.status_code == 403, contributor_new.text
    assert editor_new.status_code == 201, editor_new.text
    names = set((await lw.db.scalars(select(Tag.name))).all())
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
    async with client_as(lw.db, lw.person[who]) as c:
        resp = await c.delete(url)
    assert resp.status_code == expected, resp.text
