"""Lead content sent to a language model: who may, what goes in, which model.

Uses ``world`` from ``tests/authz_world.py``: the afdeling owns the
initiatief (its editor reads it and holds people:read), ``role_only`` is a
contributor on it.  Added here: an opdrachtgever on the lead who is placed
nowhere (writes the lead, reads neither the initiatief nor the people
directory) and a contact person with an email on the lead.
"""

import logging
from unittest.mock import AsyncMock

import pytest

from bouwmeester.api.routes import leads as leads_module
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services.llm import DataSensitivity
from tests.authz_world import World
from tests.factories import client_as, make_person

_DRAFT = '{"titel": "T", "body_internal": "B", "body_public": "P"}'
_INTAKE = '{"title": "Lead", "contact_email": "geheim@example.org"}'


@pytest.fixture
async def llm(monkeypatch):
    """A fake language model; records the sensitivity asked and the prompts."""
    fake = AsyncMock()
    fake.asked = []
    fake._complete = AsyncMock(return_value=_DRAFT)

    async def _for(sensitivity, _db):
        fake.asked.append(sensitivity)
        return fake

    monkeypatch.setattr(leads_module, "get_llm_service_for", _for)
    return fake


@pytest.fixture
async def lw(world: World) -> World:
    db = world.db
    opdrachtgever = await make_person(db, "Opdrachtgever")
    contact = await make_person(db, "Contact")
    lead = world.res["lead"]
    db.add_all(
        [
            ResourcePermission(
                person_id=opdrachtgever.id,
                resource_type="lead",
                resource_id=lead,
                rol="opdrachtgever",
            ),
            ResourcePermission(
                person_id=contact.id,
                resource_type="lead",
                resource_id=lead,
                rol="contactpersoon",
            ),
        ]
    )
    await db.flush()
    world.person.update(opdrachtgever=opdrachtgever, contact=contact)
    return world


async def _parse_update(w: World, who: str):
    async with client_as(w.db, w.person[who]) as c:
        return await c.post(
            f"/api/leads/{w.res['lead']}/updates/parse",
            data={"raw_text": "Kort verslag"},
        )


async def test_update_prompt_holds_only_what_the_caller_may_read(lw, llm):
    initiatief = await lw.db.get(Initiatief, lw.res["initiatief"])
    email = lw.person["contact"].email

    resp = await _parse_update(lw, "opdrachtgever")
    assert resp.status_code == 200, resp.text
    prompt = llm._complete.await_args.args[0]
    assert initiatief.naam not in prompt
    assert email not in prompt
    assert "Contact" in prompt  # the lead's contacts are on the lead itself
    assert resp.json()["suggested_to"] == []

    resp = await _parse_update(lw, "afd_editor")
    assert resp.status_code == 200, resp.text
    prompt = llm._complete.await_args.args[0]
    assert initiatief.naam in prompt
    assert email in prompt
    assert email in resp.json()["suggested_to"]


async def test_lead_prompts_only_go_to_a_confidential_model(lw, llm, monkeypatch):
    await _parse_update(lw, "afd_editor")
    async with client_as(lw.db, lw.person["team_editor"]) as c:
        await c.post("/api/leads/parse-intake", data={"raw_text": "Mail"})
    assert llm.asked == [DataSensitivity.CONFIDENTIAL] * 2

    async def _none(_sensitivity, _db):
        return None

    monkeypatch.setattr(leads_module, "get_llm_service_for", _none)
    assert (await _parse_update(lw, "afd_editor")).status_code == 503


@pytest.mark.parametrize(
    ("who", "with_initiatief", "expected"),
    [
        ("team_editor", False, 200),  # creates leads in the own team
        ("viewer", False, 403),  # creates leads nowhere
        ("role_only", False, 403),  # only in the initiatief
        ("role_only", True, 200),
        ("team_editor", True, 403),  # sees the initiatief, may not add to it
    ],
)
async def test_parse_intake_is_for_who_may_create_a_lead(
    lw, llm, who, with_initiatief, expected
):
    llm._complete.return_value = _INTAKE
    data = {"raw_text": "Mail van iemand"}
    if with_initiatief:
        data["initiatief_id"] = str(lw.res["initiatief"])
    async with client_as(lw.db, lw.person[who]) as c:
        resp = await c.post("/api/leads/parse-intake", data=data)
    assert resp.status_code == expected, resp.text


@pytest.mark.parametrize("too_many", [True, False])
async def test_parse_intake_limits_uploads(lw, llm, too_many):
    if too_many:
        files = [
            ("files", (f"f{i}.txt", b"x", "text/plain"))
            for i in range(leads_module.MAX_LLM_UPLOADS + 1)
        ]
    else:
        big = b"x" * (leads_module.MAX_LLM_UPLOAD_BYTES + 1)
        files = [("files", ("groot.txt", big, "text/plain"))]
    async with client_as(lw.db, lw.person["team_editor"]) as c:
        resp = await c.post("/api/leads/parse-intake", files=files)
    assert resp.status_code == 400, resp.text
    llm._complete.assert_not_awaited()


async def test_parse_intake_does_not_log_the_model_output(lw, llm, caplog):
    llm._complete.return_value = _INTAKE
    with caplog.at_level(logging.DEBUG):
        async with client_as(lw.db, lw.person["team_editor"]) as c:
            ok = await c.post("/api/leads/parse-intake", data={"raw_text": "Mail"})
        llm._complete.return_value = "geen json, wel geheim@example.org"
        async with client_as(lw.db, lw.person["team_editor"]) as c:
            broken = await c.post("/api/leads/parse-intake", data={"raw_text": "M"})
    assert ok.status_code == 200, ok.text
    assert broken.status_code == 500, broken.text
    assert "geheim@example.org" not in caplog.text
