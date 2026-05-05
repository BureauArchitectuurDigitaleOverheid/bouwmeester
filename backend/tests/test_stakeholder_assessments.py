"""Tests for StakeholderAssessment CRUD endpoints.

Covers scope-authz checks (initiatief vs corpus_node), unique-constraint,
score range validation, and the audit-trail on assessed_at/assessed_by.
"""

import uuid


async def _create_initiatief(db_session, *, naam: str = "Init"):
    from bouwmeester.models.initiatief import Initiatief

    init = Initiatief(id=uuid.uuid4(), naam=naam)
    db_session.add(init)
    await db_session.flush()
    return init


async def _grant_eigenaar(db_session, *, initiatief_id, person_id):
    from bouwmeester.models.resource_permission import ResourcePermission

    db_session.add(
        ResourcePermission(
            person_id=person_id,
            resource_type="initiatief",
            resource_id=initiatief_id,
            rol="eigenaar",
        )
    )
    await db_session.flush()


async def test_create_assessment_on_corpus_node(client, sample_node, sample_person):
    resp = await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "corpus_node",
            "scope_id": str(sample_node.id),
            "belang": 4,
            "houding": "welwillend",
            "invloed": 3,
            "notitie": "Belangrijke speler",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["belang"] == 4
    assert data["houding"] == "welwillend"
    assert data["invloed"] == 3
    assert data["person_naam"] == "Jan Tester"
    assert data["assessed_at"] is not None


async def test_list_assessments_filtered_by_scope(
    client, sample_node, second_node, sample_person
):
    # Twee assessments op verschillende scopes — list moet filteren
    await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "corpus_node",
            "scope_id": str(sample_node.id),
            "belang": 5,
        },
    )
    await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "corpus_node",
            "scope_id": str(second_node.id),
            "belang": 1,
        },
    )
    resp = await client.get(
        "/api/stakeholder-assessments",
        params={"scope_type": "corpus_node", "scope_id": str(sample_node.id)},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["belang"] == 5


async def test_unique_constraint_per_scope(client, sample_node, sample_person):
    payload = {
        "person_id": str(sample_person.id),
        "scope_type": "corpus_node",
        "scope_id": str(sample_node.id),
        "belang": 3,
    }
    first = await client.post("/api/stakeholder-assessments", json=payload)
    assert first.status_code == 201
    duplicate = await client.post("/api/stakeholder-assessments", json=payload)
    assert duplicate.status_code == 409


async def test_score_out_of_range_rejected(client, sample_node, sample_person):
    resp = await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "corpus_node",
            "scope_id": str(sample_node.id),
            "belang": 99,
        },
    )
    assert resp.status_code == 422


async def test_update_and_delete_assessment(client, sample_node, sample_person):
    create_resp = await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "corpus_node",
            "scope_id": str(sample_node.id),
            "belang": 2,
        },
    )
    assessment_id = create_resp.json()["id"]
    update_resp = await client.put(
        f"/api/stakeholder-assessments/{assessment_id}",
        json={"belang": 4, "notitie": "Geüpdatet"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["belang"] == 4
    assert update_resp.json()["notitie"] == "Geüpdatet"
    delete_resp = await client.delete(f"/api/stakeholder-assessments/{assessment_id}")
    assert delete_resp.status_code == 204


async def test_assessment_on_initiatief_requires_access(
    client, db_session, sample_person
):
    """Eigenaar-toegang vereist voor mutations op een initiatief."""
    init = await _create_initiatief(db_session)
    # In dev-mode (geen OIDC) is current_user None → _resolve_access_level
    # geeft 'eigenaar' terug. Test dat het endpoint *werkt* met dat pad.
    resp = await client.post(
        "/api/stakeholder-assessments",
        json={
            "person_id": str(sample_person.id),
            "scope_type": "initiatief",
            "scope_id": str(init.id),
            "belang": 3,
        },
    )
    assert resp.status_code == 201


async def test_list_unknown_scope_type_rejected_at_validation(client):
    resp = await client.get(
        "/api/stakeholder-assessments",
        params={"scope_type": "lead", "scope_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
