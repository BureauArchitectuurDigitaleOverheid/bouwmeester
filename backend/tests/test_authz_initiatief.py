"""Initiatief routes on the single decision point (``core/authz.py``).

Builds on the tree from ``test_authz``: the initiatief there is owned by the
afdeling (eenheid-level eigenaar) and ``role_only`` is a direct contributor.
The team below the afdeling has its own editor, who must not be able to
write the afdeling's initiatief: a role on an eenheid counts for that eenheid
and everything below it, never above.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from bouwmeester.core.initiatief_context import initiatief_access_level
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.shared_access import SharedAccess
from tests.factories import client_as, grant_role, make_org, make_person, place
from tests.test_authz import World, _ctx, world  # noqa: F401  (shared fixture)


@pytest.fixture
async def iw(world: World) -> World:  # noqa: F811
    """The shared tree plus the roles only initiatieven care about."""
    db = world.db
    initiatief_id = world.res["initiatief"]

    # A viewer through a resource role, and a whole eenheid as contributor.
    rp_viewer = await make_person(db, "Kijker")
    partner = await make_org(db, "Partnerteam", "team", world.org["elders"])
    partner_member = await make_person(db, "Partnerlid")
    await place(db, partner_member, partner)
    db.add_all(
        [
            ResourcePermission(
                person_id=rp_viewer.id,
                resource_type="initiatief",
                resource_id=initiatief_id,
                rol="viewer",
            ),
            ResourcePermission(
                organisatie_eenheid_id=partner.id,
                resource_type="initiatief",
                resource_id=initiatief_id,
                rol="contributor",
            ),
        ]
    )

    # Shares need org:manage; ministry_admin carries it, scoped to the directie.
    org_admin = await make_person(db, "Directiebeheerder")
    await place(db, org_admin, world.org["directie"])
    await grant_role(db, org_admin, "ministry_admin", world.org["directie"])

    link = MattermostChannelLink(
        channel_id="a" * 26,
        channel_name="init-kanaal",
        channel_display_name="Init kanaal",
        scope_type="initiatief",
        scope_id=initiatief_id,
    )
    db.add(link)
    await db.flush()

    world.person.update(
        rp_viewer=rp_viewer, partner_member=partner_member, org_admin=org_admin
    )
    world.org["partner"] = partner
    world.res["channel_link"] = link.id
    return world


# ---------------------------------------------------------------------------
# Access level: one derivation from authz.can, where each right holds
# ---------------------------------------------------------------------------

LEVELS = [
    ("super_admin", "eigenaar"),
    ("manager", "eigenaar"),  # unit_manager on the directie above
    # placed in the owning afdeling: its eigenaar role applies to members
    ("afd_editor", "eigenaar"),
    ("role_only", "contributor"),  # direct resource role
    ("partner_member", "contributor"),  # via the eenheid's resource role
    ("rp_viewer", "viewer"),
    # initiatief:update in another eenheid does not count here, but members
    # below the owning afdeling read up the line (core.initiatief_context)
    ("team_editor", "viewer"),
    ("viewer", "viewer"),
    ("platform_admin", None),
]


@pytest.mark.parametrize(("who", "expected"), LEVELS, ids=[w for w, _ in LEVELS])
async def test_access_level_counts_only_where_rights_hold(iw, who, expected):
    ctx = await _ctx(iw, who)
    got = await initiatief_access_level(iw.db, ctx, iw.res["initiatief"])
    assert got == expected


async def test_detail_shows_access_level_and_hides_the_rest(iw):
    url = f"/api/initiatieven/{iw.res['initiatief']}"
    async with client_as(iw.db, iw.person["rp_viewer"]) as c:
        viewer = await c.get(url)
    async with client_as(iw.db, iw.person["platform_admin"]) as c:
        outsider = await c.get(url)
    assert viewer.status_code == 200, viewer.text
    assert viewer.json()["access_level"] == "viewer"
    assert outsider.status_code == 404


# ---------------------------------------------------------------------------
# Write routes: (who, method, path template, body, expected status)
# ---------------------------------------------------------------------------

_I = "/api/initiatieven/{initiatief}"
_COLUMN = {"name": "Nieuwe kolom", "color": "accent"}
_CHANNEL = {"channel_name": "k", "channel_display_name": "K"}

WRITES = [
    # the initiatief itself
    ("team_editor", "PUT", _I, {"naam": "Nee"}, 403),
    ("rp_viewer", "PUT", _I, {"naam": "Nee"}, 403),
    ("role_only", "PUT", _I, {"beschrijving": "Ja"}, 200),
    ("partner_member", "PUT", _I, {"beschrijving": "Ja"}, 200),
    ("afd_editor", "PUT", _I, {"beschrijving": "Ja"}, 200),
    ("partner_member", "PUT", _I + "/settings", {"funnel_enabled": True}, 403),
    ("manager", "PUT", _I + "/settings", {"funnel_enabled": True}, 200),
    ("role_only", "DELETE", _I, None, 403),
    # updates, via the initiatief
    ("rp_viewer", "POST", _I + "/updates", {"titel": "Nee"}, 403),
    ("team_editor", "POST", _I + "/updates", {"titel": "Nee"}, 403),
    ("role_only", "POST", _I + "/updates", {"titel": "Ja"}, 201),
    # funnel columns, via the initiatief (contributors shape the board)
    ("rp_viewer", "POST", _I + "/columns", _COLUMN, 403),
    ("team_editor", "POST", _I + "/columns", _COLUMN, 403),
    ("role_only", "POST", _I + "/columns", _COLUMN, 201),
    ("team_editor", "POST", _I + "/columns/reorder", {"column_ids": []}, 403),
    # parliamentary subscriptions: seeing is not following
    ("rp_viewer", "POST", _I + "/abonnementen", {"term": "Nee maar"}, 403),
    ("role_only", "POST", _I + "/abonnementen", {"term": "Wel degelijk"}, 201),
    ("rp_viewer", "PUT", _I + "/signaalcontext", {"tekst": "Nee"}, 403),
    ("afd_editor", "PUT", _I + "/signaalcontext", {"tekst": "Ja"}, 200),
    # Mattermost links on the initiatief and on its lead
    ("rp_viewer", "POST", _I + "/mattermost-channels", _CHANNEL, 403),
    ("role_only", "POST", _I + "/mattermost-channels", _CHANNEL, 201),
    ("team_editor", "POST", "/api/leads/{lead}/mattermost-channels", _CHANNEL, 403),
    ("afd_editor", "POST", "/api/leads/{lead}/mattermost-channels", _CHANNEL, 201),
    ("rp_viewer", "PATCH", "/api/mattermost-channels/{channel_link}", {}, 403),
    ("afd_editor", "PATCH", "/api/mattermost-channels/{channel_link}", {}, 200),
    ("rp_viewer", "DELETE", "/api/mattermost-channels/{channel_link}", None, 403),
    ("role_only", "DELETE", "/api/mattermost-channels/{channel_link}", None, 204),
]


def _fill(iw: World, path: str, body):
    path = path.format(**iw.res)
    if body is _CHANNEL:
        # Every link needs its own channel id.
        body = {**_CHANNEL, "channel_id": uuid.uuid4().hex[:26]}
    return path, body


@pytest.mark.parametrize(
    ("who", "method", "path", "body", "expected"),
    WRITES,
    ids=[f"{w[0]}-{w[1]}-{w[2].rsplit('}', 1)[-1] or '/'}" for w in WRITES],
)
async def test_write_routes_follow_authz(iw, who, method, path, body, expected):
    path, body = _fill(iw, path, body)
    async with client_as(iw.db, iw.person[who]) as c:
        resp = await c.request(method, path, json=body)
    assert resp.status_code == expected, resp.text


async def test_update_posts_are_decided_by_their_initiatief(iw):
    async with client_as(iw.db, iw.person["role_only"]) as c:
        created = await c.post(
            f"/api/initiatieven/{iw.res['initiatief']}/updates", json={"titel": "T"}
        )
    post = f"/api/initiatieven/{iw.res['initiatief']}/updates/{created.json()['id']}"
    async with client_as(iw.db, iw.person["team_editor"]) as c:
        denied = await c.post(post + "/publish")
    async with client_as(iw.db, iw.person["afd_editor"]) as c:
        published = await c.post(post + "/publish")
        # A post under another initiatief's path is not found there.
        wrong_parent = await c.put(
            f"/api/initiatieven/{uuid.uuid4()}/updates/{created.json()['id']}",
            json={"titel": "X"},
        )
        deleted = await c.delete(post)
    assert denied.status_code == 403
    assert published.status_code == 200, published.text
    assert wrong_parent.status_code == 404
    assert deleted.status_code == 204


async def test_viewer_may_read_what_they_may_not_write(iw):
    base = f"/api/initiatieven/{iw.res['initiatief']}"
    async with client_as(iw.db, iw.person["rp_viewer"]) as c:
        reads = [
            await c.get(base + p)
            for p in (
                "/columns",
                "/updates",
                "/abonnementen",
                "/signaalcontext",
                "/mattermost-channels",
            )
        ]
    async with client_as(iw.db, iw.person["platform_admin"]) as c:
        hidden = await c.get(base + "/abonnementen")
    assert [r.status_code for r in reads] == [200] * 5
    assert hidden.status_code == 404


# ---------------------------------------------------------------------------
# Creating: a personal initiatief, and nothing more
# ---------------------------------------------------------------------------


async def test_create_grants_only_the_creator(iw):
    """Creation is allowlisted: the payload must not carry any other grant."""
    other = iw.person["team_editor"]
    payload = {
        "naam": f"Eigen {uuid.uuid4().hex[:6]}",
        "members": [{"person_id": str(other.id), "rol": "eigenaar"}],
        "eenheden": [{"eenheid_id": str(iw.org["ministerie"].id), "rol": "eigenaar"}],
        "created_by_id": str(other.id),
        "access_level": "eigenaar",
        "slug": "gekaapt",
        "public_page_enabled": True,
        "funnel_enabled": True,
    }
    async with client_as(iw.db, iw.person["viewer"]) as c:
        resp = await c.post("/api/initiatieven", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] != "gekaapt"
    assert body["public_page_enabled"] is False
    assert body["funnel_enabled"] is False

    grants = (
        await iw.db.execute(
            select(
                ResourcePermission.person_id,
                ResourcePermission.organisatie_eenheid_id,
                ResourcePermission.rol,
            ).where(
                ResourcePermission.resource_type == "initiatief",
                ResourcePermission.resource_id == uuid.UUID(body["id"]),
            )
        )
    ).all()
    assert grants == [(iw.person["viewer"].id, None, "eigenaar")]


# ---------------------------------------------------------------------------
# Sharing: org:manage on every source eenheid, system roles for the rest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "source", "expected"),
    [
        ("org_admin", {"source_eenheid_id": "afdeling"}, 200),  # below own directie
        ("org_admin", {"source_eenheid_id": "dg"}, 403),  # above it
        ("org_admin", {"source_node_id": "node_team"}, 200),
        ("org_admin", {"source_node_id": "node_free"}, 403),  # tenant-wide source
        ("super_admin", {"source_node_id": "node_free"}, 200),
        ("afd_editor", {"source_eenheid_id": "afdeling"}, 403),  # no org:manage
    ],
    ids=["below", "above", "node-inside", "node-free", "node-free-admin", "editor"],
)
async def test_share_needs_org_manage_on_the_source(iw, who, source, expected):
    body = {"target_eenheid_id": str(iw.org["elders"].id), "access_level": "read"}
    for key, name in source.items():
        body[key] = str(iw.org[name].id if key == "source_eenheid_id" else iw.res[name])
    async with client_as(iw.db, iw.person[who]) as c:
        resp = await c.post("/api/sharing", json=body)
    assert resp.status_code == expected, resp.text


async def test_revoke_share_needs_the_same_authority(iw):
    share = SharedAccess(
        source_eenheid_id=iw.org["dg"].id,
        target_eenheid_id=iw.org["team"].id,
        access_level="read",
        geldig_van=date.today(),
    )
    iw.db.add(share)
    await iw.db.flush()
    async with client_as(iw.db, iw.person["org_admin"]) as c:
        denied = await c.delete(f"/api/sharing/{share.id}")
    async with client_as(iw.db, iw.person["super_admin"]) as c:
        allowed = await c.delete(f"/api/sharing/{share.id}")
    assert denied.status_code == 403
    assert allowed.status_code == 200, allowed.text
