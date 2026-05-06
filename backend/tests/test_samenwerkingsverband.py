"""Tests voor het Samenwerkingsverband-domein."""

from datetime import date, timedelta


async def test_create_and_list(client):
    """POST + GET roundtrip."""
    create = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "CRI", "type": "programma"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["naam"] == "CRI"
    assert body["type"] == "programma"
    assert body["aantal_leden"] == 0

    listing = await client.get("/api/samenwerkingsverbanden")
    assert listing.status_code == 200
    assert any(item["id"] == body["id"] for item in listing.json())


async def test_filter_by_type(client):
    await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "Werkgroep AI", "type": "werkgroep"},
    )
    await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "Programma X", "type": "programma"},
    )

    resp = await client.get("/api/samenwerkingsverbanden?type=werkgroep")
    assert resp.status_code == 200
    types = {v["type"] for v in resp.json()}
    assert types == {"werkgroep"}


async def test_update(client):
    create = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "Voorlopig", "type": "werkgroep"},
    )
    swv_id = create.json()["id"]

    upd = await client.put(
        f"/api/samenwerkingsverbanden/{swv_id}",
        json={"naam": "Werkgroep AI-verordening"},
    )
    assert upd.status_code == 200
    assert upd.json()["naam"] == "Werkgroep AI-verordening"


async def test_delete_cascades_leden(client, sample_person):
    create = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "Tijdelijk", "type": "opschalingsticket"},
    )
    swv_id = create.json()["id"]

    add = await client.post(
        f"/api/samenwerkingsverbanden/{swv_id}/leden",
        json={
            "person_id": str(sample_person.id),
            "rol": "lid",
            "start_datum": date.today().isoformat(),
        },
    )
    assert add.status_code == 201

    delete = await client.delete(f"/api/samenwerkingsverbanden/{swv_id}")
    assert delete.status_code == 204

    # Lid is mee weg via CASCADE — detail-route geeft 404
    detail = await client.get(f"/api/samenwerkingsverbanden/{swv_id}")
    assert detail.status_code == 404


async def test_lid_lifecycle(client, sample_person, second_person):
    create = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "CRI", "type": "programma"},
    )
    swv_id = create.json()["id"]

    today = date.today().isoformat()
    add1 = await client.post(
        f"/api/samenwerkingsverbanden/{swv_id}/leden",
        json={
            "person_id": str(sample_person.id),
            "rol": "trekker",
            "start_datum": today,
        },
    )
    assert add1.status_code == 201
    lid_id = add1.json()["id"]
    assert add1.json()["person_naam"]
    assert add1.json()["rol"] == "trekker"

    add2 = await client.post(
        f"/api/samenwerkingsverbanden/{swv_id}/leden",
        json={"person_id": str(second_person.id), "rol": "lid", "start_datum": today},
    )
    assert add2.status_code == 201

    detail = await client.get(f"/api/samenwerkingsverbanden/{swv_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["aantal_leden"] == 2
    assert len(body["leden"]) == 2

    # Update rol
    upd = await client.put(
        f"/api/samenwerkingsverbanden/{swv_id}/leden/{lid_id}",
        json={"rol": "voorzitter"},
    )
    assert upd.status_code == 200
    assert upd.json()["rol"] == "voorzitter"

    # Verwijder
    rm = await client.delete(f"/api/samenwerkingsverbanden/{swv_id}/leden/{lid_id}")
    assert rm.status_code == 204

    after = await client.get(f"/api/samenwerkingsverbanden/{swv_id}")
    assert after.json()["aantal_leden"] == 1


async def test_duplicate_active_lid_409(client, sample_person):
    create = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "CRI", "type": "programma"},
    )
    swv_id = create.json()["id"]

    today = date.today().isoformat()
    a = await client.post(
        f"/api/samenwerkingsverbanden/{swv_id}/leden",
        json={"person_id": str(sample_person.id), "start_datum": today},
    )
    assert a.status_code == 201

    b = await client.post(
        f"/api/samenwerkingsverbanden/{swv_id}/leden",
        json={"person_id": str(sample_person.id), "start_datum": today},
    )
    assert b.status_code == 409


async def test_actief_filter(client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    actief_resp = await client.post(
        "/api/samenwerkingsverbanden",
        json={"naam": "Actief", "type": "programma"},
    )
    assert actief_resp.status_code == 201

    inactief_resp = await client.post(
        "/api/samenwerkingsverbanden",
        json={
            "naam": "Afgesloten",
            "type": "opschalingsticket",
            "start_datum": last_week.isoformat(),
            "eind_datum": yesterday.isoformat(),
        },
    )
    assert inactief_resp.status_code == 201

    only_actief = await client.get("/api/samenwerkingsverbanden?actief=true")
    namen = {v["naam"] for v in only_actief.json()}
    assert "Actief" in namen
    assert "Afgesloten" not in namen

    only_inactief = await client.get("/api/samenwerkingsverbanden?actief=false")
    namen = {v["naam"] for v in only_inactief.json()}
    assert "Afgesloten" in namen
    assert "Actief" not in namen
