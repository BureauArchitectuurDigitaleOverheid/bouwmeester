"""Tests for creating a channel, pinning, and the rights check.

The client is a real `httpx.AsyncClient` on a `MockTransport`, so each test
sees the request Mattermost would get: method, path and body. A fake with
`post()`/`get()` methods would accept a call to the wrong endpoint.
"""

from __future__ import annotations

import json

import httpx
import pytest

from bouwmeester.services.mattermost_service import (
    ChannelNameTakenError,
    MattermostPermissionError,
    MattermostService,
    MattermostUnavailableError,
)


def _service(monkeypatch, handler) -> tuple[MattermostService, list[httpx.Request]]:
    """A service whose HTTP calls go to `handler`; returns the requests too."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(
        base_url="http://mm.test", transport=httpx.MockTransport(recording)
    )

    async def fake_get_client(self):
        return client

    monkeypatch.setattr(MattermostService, "_get_client", fake_get_client)
    return MattermostService(None), seen


def _body(request: httpx.Request):
    return json.loads(request.content)


CREATE_ARGS = {
    "team_id": "team1",
    "name": "debat-digitale-overheid-7-okt",
    "display_name": "Debat: Digitale overheid",
}


@pytest.mark.asyncio
class TestCreateChannel:
    async def test_header_and_purpose_travel_with_the_create_call(self, monkeypatch):
        """One call, so one permission: patching afterwards needs another."""
        svc, seen = _service(
            monkeypatch, lambda r: httpx.Response(201, json={"id": "chan1"})
        )

        channel = await svc.create_channel(
            **CREATE_ARGS, header="7 oktober 10:00", purpose="Waar het over gaat"
        )

        assert channel["id"] == "chan1"
        assert len(seen) == 1
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/api/v4/channels"
        assert _body(seen[0]) == {
            "team_id": "team1",
            "name": "debat-digitale-overheid-7-okt",
            "display_name": "Debat: Digitale overheid",
            "header": "7 oktober 10:00",
            "purpose": "Waar het over gaat",
            "type": "O",
        }

    async def test_private_channel_has_type_p(self, monkeypatch):
        svc, seen = _service(
            monkeypatch, lambda r: httpx.Response(201, json={"id": "chan1"})
        )
        await svc.create_channel(**CREATE_ARGS, private=True)
        assert _body(seen[0])["type"] == "P"

    @pytest.mark.parametrize(
        ("private", "permission"),
        [(False, "create_public_channel"), (True, "create_private_channel")],
    )
    async def test_403_names_the_missing_permission(
        self, monkeypatch, private, permission
    ):
        """An administrator has to know which permission to grant."""
        svc, _ = _service(
            monkeypatch,
            lambda r: httpx.Response(
                403, json={"id": "api.context.permissions.app_error"}
            ),
        )
        with pytest.raises(MattermostPermissionError) as raised:
            await svc.create_channel(**CREATE_ARGS, private=private)
        assert raised.value.permission == permission

    async def test_403_from_a_proxy_is_not_a_missing_permission(self, monkeypatch):
        """Otherwise an administrator is sent to grant a permission while
        the request never reached Mattermost."""
        svc, _ = _service(
            monkeypatch, lambda r: httpx.Response(403, text="<html>Forbidden</html>")
        )
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_duplicate_name_is_its_own_error(self, monkeypatch):
        svc, _ = _service(
            monkeypatch,
            lambda r: httpx.Response(
                400, json={"id": "store.sql_channel.save_channel.exists.app_error"}
            ),
        )
        with pytest.raises(ChannelNameTakenError) as raised:
            await svc.create_channel(**CREATE_ARGS)
        assert raised.value.name == CREATE_ARGS["name"]

    async def test_other_400_is_not_a_duplicate_name(self, monkeypatch):
        """A too-long display name is a 400 as well. Retrying with another
        name would then loop on an error that a new name does not fix."""
        svc, _ = _service(
            monkeypatch,
            lambda r: httpx.Response(
                400, json={"id": "model.channel.is_valid.display_name.app_error"}
            ),
        )
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_400_without_json_body_is_not_a_crash(self, monkeypatch):
        svc, _ = _service(
            monkeypatch, lambda r: httpx.Response(400, text="<html>proxy</html>")
        )
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_server_error_is_temporary(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(502))
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_network_error_is_temporary(self, monkeypatch):
        def boom(request):
            raise httpx.ConnectError("no route", request=request)

        svc, _ = _service(monkeypatch, boom)
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_success_without_id_is_not_a_channel(self, monkeypatch):
        """Without an id nothing can be posted or pinned afterwards."""
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(201, json={}))
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)


def _broken_config(monkeypatch) -> MattermostService:
    """A service whose client cannot be built: no token, or a bad URL."""

    async def raising(self):
        raise ValueError("MATTERMOST_BOT_TOKEN is not configured")

    monkeypatch.setattr(MattermostService, "_get_client", raising)
    return MattermostService(None)


@pytest.mark.asyncio
class TestBrokenConfiguration:
    """`_get_client` raises ValueError. A worker that catches the
    documented exceptions must not die on a fourth."""

    async def test_create_channel_raises_unavailable(self, monkeypatch):
        svc = _broken_config(monkeypatch)
        with pytest.raises(MattermostUnavailableError):
            await svc.create_channel(**CREATE_ARGS)

    async def test_team_permissions_raises_unavailable(self, monkeypatch):
        svc = _broken_config(monkeypatch)
        with pytest.raises(MattermostUnavailableError):
            await svc.team_permissions()

    async def test_the_soft_methods_stay_soft(self, monkeypatch):
        svc = _broken_config(monkeypatch)
        assert await svc.pin_post("post1") is False
        assert await svc.add_channel_member("chan1", "user1") is False
        assert await svc.update_channel("chan1", header="x") is False
        assert await svc.get_channel("chan1") is None
        assert await svc.get_channel_by_name("team1", "naam") is None
        assert await svc.channel_is_gone("chan1") is False


@pytest.mark.asyncio
class TestPinning:
    async def test_pin_posts_to_the_pin_endpoint(self, monkeypatch):
        svc, seen = _service(
            monkeypatch, lambda r: httpx.Response(200, json={"status": "OK"})
        )
        assert await svc.pin_post("post1") is True
        assert (seen[0].method, seen[0].url.path) == ("POST", "/api/v4/posts/post1/pin")

    async def test_unpin_posts_to_the_unpin_endpoint(self, monkeypatch):
        svc, seen = _service(
            monkeypatch, lambda r: httpx.Response(200, json={"status": "OK"})
        )
        assert await svc.unpin_post("post1") is True
        assert seen[0].url.path == "/api/v4/posts/post1/unpin"

    async def test_failed_pin_is_false(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(403))
        assert await svc.pin_post("post1") is False


@pytest.mark.asyncio
class TestUpdateChannel:
    async def test_only_given_fields_are_sent(self, monkeypatch):
        """Mattermost announces a changed header in the channel, so an
        unchanged purpose must not ride along."""
        svc, seen = _service(monkeypatch, lambda r: httpx.Response(200, json={}))
        assert await svc.update_channel("chan1", header="nieuwe tijd") is True
        assert (seen[0].method, seen[0].url.path) == (
            "PUT",
            "/api/v4/channels/chan1/patch",
        )
        assert _body(seen[0]) == {"header": "nieuwe tijd"}

    async def test_empty_string_clears_a_field(self, monkeypatch):
        svc, seen = _service(monkeypatch, lambda r: httpx.Response(200, json={}))
        await svc.update_channel("chan1", purpose="")
        assert _body(seen[0]) == {"purpose": ""}

    async def test_nothing_to_change_makes_no_call(self, monkeypatch):
        svc, seen = _service(monkeypatch, lambda r: httpx.Response(500))
        assert await svc.update_channel("chan1") is True
        assert seen == []

    async def test_failure_is_false(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(403))
        assert await svc.update_channel("chan1", header="x") is False


@pytest.mark.asyncio
class TestChannelMembers:
    async def test_add_member_sends_the_user(self, monkeypatch):
        svc, seen = _service(monkeypatch, lambda r: httpx.Response(201, json={}))
        assert await svc.add_channel_member("chan1", "user1") is True
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/api/v4/channels/chan1/members"
        assert _body(seen[0]) == {"user_id": "user1"}

    async def test_failure_is_false(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(403))
        assert await svc.add_channel_member("chan1", "user1") is False

    async def test_get_channel_returns_the_channel(self, monkeypatch):
        svc, seen = _service(
            monkeypatch,
            lambda r: httpx.Response(200, json={"id": "chan1", "team_id": "team1"}),
        )
        assert (await svc.get_channel("chan1"))["team_id"] == "team1"
        assert seen[0].url.path == "/api/v4/channels/chan1"

    async def test_get_channel_failure_is_none(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(404))
        assert await svc.get_channel("chan1") is None

    async def test_archived_channel_is_gone(self, monkeypatch):
        """Mattermost still returns an archived channel, with `delete_at`."""
        svc, seen = _service(
            monkeypatch,
            lambda r: httpx.Response(200, json={"id": "chan1", "delete_at": 1700}),
        )
        assert await svc.channel_is_gone("chan1") is True
        assert seen[0].url.path == "/api/v4/channels/chan1"

    async def test_deleted_channel_is_gone(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(404))
        assert await svc.channel_is_gone("chan1") is True

    async def test_live_channel_is_not_gone(self, monkeypatch):
        svc, _ = _service(
            monkeypatch,
            lambda r: httpx.Response(200, json={"id": "chan1", "delete_at": 0}),
        )
        assert await svc.channel_is_gone("chan1") is False

    @pytest.mark.parametrize("status", [401, 403, 500, 502])
    async def test_a_failed_check_is_not_gone(self, monkeypatch, status):
        """The caller forgets the channel on a yes. A hiccup must not make
        it forget a channel that is still there."""
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(status))
        assert await svc.channel_is_gone("chan1") is False

    async def test_get_channel_by_name_asks_within_the_team(self, monkeypatch):
        svc, seen = _service(
            monkeypatch,
            lambda r: httpx.Response(200, json={"id": "chan1", "creator_id": "bot"}),
        )
        channel = await svc.get_channel_by_name("team1", "debat-x-6-okt")
        assert channel["creator_id"] == "bot"
        assert seen[0].url.path == "/api/v4/teams/team1/channels/name/debat-x-6-okt"

    async def test_get_channel_by_name_unknown_is_none(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(404))
        assert await svc.get_channel_by_name("team1", "debat-x") is None

    async def test_get_channel_by_name_without_id_is_none(self, monkeypatch):
        """Whoever adopts the channel needs its id."""
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(200, json={}))
        assert await svc.get_channel_by_name("team1", "debat-x") is None


def _rights_handler(
    *, system_roles, team_roles, role_permissions, left=(), deleted_roles=()
):
    """A Mattermost that answers the three calls of the rights check.

    `left` are teams the bot was removed from: Mattermost keeps listing
    those, with a `delete_at`. `deleted_roles` likewise for roles.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v4/users/me":
            return httpx.Response(200, json={"id": "bot", "roles": system_roles})
        if path == "/api/v4/users/me/teams/members":
            return httpx.Response(
                200,
                json=[
                    {
                        "team_id": team_id,
                        "roles": roles,
                        "delete_at": 1700000000000 if team_id in left else 0,
                    }
                    for team_id, roles in team_roles.items()
                ],
            )
        if path == "/api/v4/roles/names":
            asked = json.loads(request.content)
            return httpx.Response(
                200,
                json=[
                    {
                        "name": name,
                        "permissions": role_permissions[name],
                        "delete_at": 1700000000000 if name in deleted_roles else 0,
                    }
                    for name in asked
                    if name in role_permissions
                ],
            )
        return httpx.Response(404)

    return handler


@pytest.mark.asyncio
class TestTeamPermissions:
    async def test_default_team_member_may_create_channels(self, monkeypatch):
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={"team1": "team_user"},
                role_permissions={
                    "system_user": ["create_direct_channel"],
                    "team_user": ["create_public_channel", "create_private_channel"],
                },
            ),
        )
        granted = await svc.team_permissions()
        assert "create_public_channel" in granted["team1"]
        assert "create_private_channel" in granted["team1"]

    async def test_rights_differ_per_team(self, monkeypatch):
        """A team with its own scheme carries its own role names. The
        answer for one team says nothing about the next."""
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={"open": "team_user", "locked": "scheme_abc_team_user"},
                role_permissions={
                    "system_user": [],
                    "team_user": ["create_public_channel"],
                    "scheme_abc_team_user": ["list_team_channels"],
                },
            ),
        )
        granted = await svc.team_permissions()
        assert "create_public_channel" in granted["open"]
        assert "create_public_channel" not in granted["locked"]

    async def test_a_system_role_counts_in_every_team(self, monkeypatch):
        """A bot that is system admin may create channels even where the
        team role forbids it; that is how Mattermost evaluates it."""
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user system_admin",
                team_roles={"locked": "scheme_abc_team_user"},
                role_permissions={
                    "system_user": [],
                    "system_admin": ["create_public_channel"],
                    "scheme_abc_team_user": [],
                },
            ),
        )
        granted = await svc.team_permissions()
        assert "create_public_channel" in granted["locked"]

    async def test_a_team_the_bot_left_is_not_reported(self, monkeypatch):
        """Mattermost keeps the membership, roles and all, with a
        `delete_at`. Reporting it promises a right that ends in a 403."""
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={"current": "team_user", "former": "team_user"},
                role_permissions={
                    "system_user": [],
                    "team_user": ["create_public_channel"],
                },
                left={"former"},
            ),
        )
        granted = await svc.team_permissions()
        assert set(granted) == {"current"}

    async def test_a_deleted_role_grants_nothing(self, monkeypatch):
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={"team1": "old_scheme_role"},
                role_permissions={
                    "system_user": [],
                    "old_scheme_role": ["create_public_channel"],
                },
                deleted_roles={"old_scheme_role"},
            ),
        )
        granted = await svc.team_permissions()
        assert "create_public_channel" not in granted["team1"]

    async def test_bot_in_no_team_is_an_empty_answer(self, monkeypatch):
        svc, _ = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={},
                role_permissions={"system_user": []},
            ),
        )
        assert await svc.team_permissions() == {}

    async def test_all_role_names_are_asked_in_one_call(self, monkeypatch):
        svc, seen = _service(
            monkeypatch,
            _rights_handler(
                system_roles="system_user",
                team_roles={"a": "team_user", "b": "team_user team_admin"},
                role_permissions={"system_user": [], "team_user": [], "team_admin": []},
            ),
        )
        await svc.team_permissions()
        role_calls = [r for r in seen if r.url.path == "/api/v4/roles/names"]
        assert len(role_calls) == 1
        assert _body(role_calls[0]) == ["system_user", "team_admin", "team_user"]

    async def test_failure_raises_instead_of_reporting_no_rights(self, monkeypatch):
        """An empty answer would send an administrator looking for a
        missing permission while the real problem is a failed call."""
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(500))
        with pytest.raises(MattermostUnavailableError):
            await svc.team_permissions()

    async def test_failing_roles_call_raises(self, monkeypatch):
        base = _rights_handler(
            system_roles="system_user",
            team_roles={"team1": "team_user"},
            role_permissions={},
        )

        def handler(request):
            if request.url.path == "/api/v4/roles/names":
                # A body that parses: only the status says it went wrong.
                return httpx.Response(500, json=[])
            return base(request)

        svc, _ = _service(monkeypatch, handler)
        with pytest.raises(MattermostUnavailableError):
            await svc.team_permissions()


@pytest.mark.asyncio
class TestChannelRightsEndpoint:
    async def test_reports_per_team(self, client, monkeypatch):
        async def enabled(self):
            return True

        async def permissions(self):
            return {
                "team-b": {"create_public_channel"},
                "team-a": {"create_private_channel"},
            }

        async def names(self):
            return {"team-a": "Alpha"}

        monkeypatch.setattr(MattermostService, "is_enabled", enabled)
        monkeypatch.setattr(MattermostService, "team_permissions", permissions)
        monkeypatch.setattr(MattermostService, "team_namen", names)

        resp = await client.get("/api/admin/mattermost-channel-rights")

        assert resp.status_code == 200
        assert resp.json() == [
            {
                "team_id": "team-a",
                "team_name": "Alpha",
                "can_create_public_channel": False,
                "can_create_private_channel": True,
            },
            {
                "team_id": "team-b",
                "team_name": None,
                "can_create_public_channel": True,
                "can_create_private_channel": False,
            },
        ]

    async def test_unanswerable_is_503_not_an_empty_list(self, client, monkeypatch):
        async def enabled(self):
            return True

        async def permissions(self):
            raise MattermostUnavailableError("down")

        monkeypatch.setattr(MattermostService, "is_enabled", enabled)
        monkeypatch.setattr(MattermostService, "team_permissions", permissions)

        resp = await client.get("/api/admin/mattermost-channel-rights")
        assert resp.status_code == 503

    async def test_unreadable_team_names_are_503_not_500(self, client, monkeypatch):
        async def enabled(self):
            return True

        async def permissions(self):
            return {"team-a": set()}

        async def names(self):
            raise ValueError("not json")

        monkeypatch.setattr(MattermostService, "is_enabled", enabled)
        monkeypatch.setattr(MattermostService, "team_permissions", permissions)
        monkeypatch.setattr(MattermostService, "team_namen", names)

        resp = await client.get("/api/admin/mattermost-channel-rights")
        assert resp.status_code == 503

    async def test_disabled_mattermost_is_503(self, client, monkeypatch):
        async def disabled(self):
            return False

        monkeypatch.setattr(MattermostService, "is_enabled", disabled)
        resp = await client.get("/api/admin/mattermost-channel-rights")
        assert resp.status_code == 503


@pytest.mark.asyncio
class TestTeamSlugs:
    async def test_gives_the_url_name_not_the_display_name(self, monkeypatch):
        """A link is built from the slug; "NLDD Team" in a url is a 404."""
        svc, seen = _service(
            monkeypatch,
            lambda r: httpx.Response(
                200,
                json=[
                    {"id": "team1", "name": "nldd", "display_name": "NLDD Team"},
                    {"id": "team2", "display_name": "Zonder slug"},
                    "geen dict",
                ],
            ),
        )
        assert await svc.team_slugs() == {"team1": "nldd"}
        assert seen[0].url.path == "/api/v4/users/me/teams"

    async def test_failure_is_empty(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(500))
        assert await svc.team_slugs() == {}

    async def test_odd_body_is_empty(self, monkeypatch):
        svc, _ = _service(monkeypatch, lambda r: httpx.Response(200, json={"x": 1}))
        assert await svc.team_slugs() == {}
