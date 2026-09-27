"""Comprehensive API tests for the search router."""


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


async def test_search_returns_200(client, sample_node):
    """GET /api/search?q=... returns 200 and a SearchResponse."""
    resp = await client.get("/api/search", params={"q": "Test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "total" in data
    assert "query" in data
    assert data["query"] == "Test"


async def test_search_finds_node(client, sample_node):
    """GET /api/search?q=dossier finds the test dossier node."""
    resp = await client.get("/api/search", params={"q": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert str(sample_node.id) in ids


async def test_search_no_match(client):
    """GET /api/search?q=... returns empty results when nothing matches."""
    resp = await client.get("/api/search", params={"q": "xyznonexistent999"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


async def test_search_filter_by_result_type(client, sample_node):
    """GET /api/search?q=...&result_types=corpus_node filters by result type."""
    resp = await client.get(
        "/api/search", params={"q": "Test", "result_types": "corpus_node"}
    )
    assert resp.status_code == 200
    data = resp.json()
    for r in data["results"]:
        assert r["result_type"] == "corpus_node"


async def test_search_result_has_required_fields(client, sample_node):
    """Search results contain all required fields."""
    resp = await client.get("/api/search", params={"q": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    result = data["results"][0]
    assert "id" in result
    assert "result_type" in result
    assert "title" in result
    assert "score" in result
    assert "url" in result


# ---------------------------------------------------------------------------
# Visibility through shares only
# ---------------------------------------------------------------------------


async def test_search_with_only_shared_eenheden(db_session):
    """Someone who sees an eenheid only through a share still gets its nodes.

    The SQL filter refers to ``:visible_eenheid_ids``; it must be bound
    whenever the clause uses it, not only when own eenheden exist.
    """
    import uuid

    from bouwmeester.core.org_context import OrgContext
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.repositories.search import SearchRepository
    from tests.factories import make_org

    shared = await make_org(db_session, "Gedeelde directie")
    hidden = await make_org(db_session, "Verborgen directie")
    seen = CorpusNode(
        id=uuid.uuid4(),
        title="Deelbaar zonnepaneeldossier",
        node_type="dossier",
        organisatie_eenheid_id=shared.id,
    )
    unseen = CorpusNode(
        id=uuid.uuid4(),
        title="Verborgen zonnepaneeldossier",
        node_type="dossier",
        organisatie_eenheid_id=hidden.id,
    )
    db_session.add_all([seen, unseen])
    await db_session.flush()
    ctx = OrgContext(
        person_id=uuid.uuid4(),
        shared_eenheid_ids=[shared.id],
        is_authenticated=True,
    )
    repo = SearchRepository(db_session)

    found = await repo.full_text_search(
        "zonnepaneeldossier", result_types=["corpus_node"], org_ctx=ctx
    )
    similar = await repo.find_similar_nodes("zonnepaneeldossier", org_ctx=ctx)

    assert {str(r["id"]) for r in found} == {str(seen.id)}
    assert {str(r["id"]) for r in similar} == {str(seen.id)}
