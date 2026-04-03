"""Tests for FCC OData client and mock client."""

from bouwmeester.services.fcc_odata_mock import FccODataMockClient

# ---------------------------------------------------------------------------
# Mock client: metadata discovery
# ---------------------------------------------------------------------------


async def test_mock_discover_metadata():
    """Mock client returns entity sets with FCC field names."""
    async with FccODataMockClient() as client:
        meta = await client.discover_metadata()

    assert "entity_sets" in meta
    assert "Portfolio_item" in meta["entity_sets"]
    props = meta["entity_sets"]["Portfolio_item"]
    assert "Portfolio_itemKey" in props
    assert "Naam" in props
    assert "Budget_huidig_jaar_" in props


# ---------------------------------------------------------------------------
# Mock client: fetch entities
# ---------------------------------------------------------------------------


async def test_mock_fetch_all_portfolio_items():
    """Mock client returns multiple portfolio items."""
    async with FccODataMockClient() as client:
        items = await client.fetch_entities("Portfolio_item")

    assert len(items) >= 5
    first = items[0]
    assert "Portfolio_itemKey" in first
    assert "Naam" in first
    assert "Budget_huidig_jaar_" in first
    assert "Laatst_gewijzigd_op" in first


async def test_mock_fetch_with_top():
    """Mock client respects $top parameter."""
    async with FccODataMockClient() as client:
        items = await client.fetch_entities("Portfolio_item", top=2)

    assert len(items) == 2


async def test_mock_fetch_with_skip():
    """Mock client respects $skip parameter."""
    async with FccODataMockClient() as client:
        all_items = await client.fetch_entities("Portfolio_item")
        skipped = await client.fetch_entities("Portfolio_item", skip=2)

    assert len(skipped) == len(all_items) - 2


async def test_mock_fetch_with_select():
    """Mock client respects $select parameter."""
    async with FccODataMockClient() as client:
        items = await client.fetch_entities(
            "Portfolio_item", select=["Portfolio_itemKey", "Naam"]
        )

    first = items[0]
    assert set(first.keys()) == {"Portfolio_itemKey", "Naam"}


async def test_mock_fetch_with_filter():
    """Mock client supports basic $filter on key field."""
    async with FccODataMockClient() as client:
        items = await client.fetch_entities(
            "Portfolio_item",
            filters="Portfolio_itemKey eq '900001'",
        )

    assert len(items) == 1
    assert items[0]["Naam"] == "Realisatie publieke NL-Wallet"


async def test_mock_fetch_unknown_entity():
    """Mock client returns empty list for unknown entity sets."""
    async with FccODataMockClient() as client:
        result = await client.fetch_entities("NonExistent")

    assert result == []


# ---------------------------------------------------------------------------
# Mock client: get single entity
# ---------------------------------------------------------------------------


async def test_mock_get_entity():
    """Mock client returns a single entity by Portfolio_itemKey."""
    async with FccODataMockClient() as client:
        entity = await client.get_entity("Portfolio_item", "900001")

    assert entity is not None
    assert entity["Naam"] == "Realisatie publieke NL-Wallet"
    assert entity["Uitvoeringsorganisatie"] == "ICTU"


async def test_mock_get_entity_not_found():
    """Mock client returns None for unknown key."""
    async with FccODataMockClient() as client:
        entity = await client.get_entity("Portfolio_item", "999999")

    assert entity is None


# ---------------------------------------------------------------------------
# Mock client: create entity
# ---------------------------------------------------------------------------


async def test_mock_create_entity():
    """Mock client creates an entity and returns it with key."""
    async with FccODataMockClient() as client:
        data = {"Naam": "Nieuw Project", "Budget_huidig_jaar_": 100_000}
        result = await client.create_entity("Portfolio_item", data)

    assert "Portfolio_itemKey" in result
    assert result["Naam"] == "Nieuw Project"
    assert "Laatst_gewijzigd_op" in result


async def test_mock_create_and_retrieve():
    """Created entity is retrievable via get_entity."""
    client = FccODataMockClient()
    async with client:
        created = await client.create_entity("Portfolio_item", {"Naam": "Retrievable"})
        fetched = await client.get_entity(
            "Portfolio_item", created["Portfolio_itemKey"]
        )

    assert fetched is not None
    assert fetched["Naam"] == "Retrievable"


# ---------------------------------------------------------------------------
# Mock client: update entity
# ---------------------------------------------------------------------------


async def test_mock_update_entity():
    """Mock client updates entity fields."""
    async with FccODataMockClient() as client:
        original = await client.get_entity("Portfolio_item", "900001")
        result = await client.update_entity(
            "Portfolio_item",
            "900001",
            {"Naam": "Gewijzigde naam"},
        )

    assert result["Naam"] == "Gewijzigde naam"
    assert result["Budget_huidig_jaar_"] == original["Budget_huidig_jaar_"]


async def test_mock_update_nonexistent():
    """Mock client returns input data for nonexistent entity."""
    async with FccODataMockClient() as client:
        result = await client.update_entity(
            "Portfolio_item", "999999", {"Naam": "Ghost"}
        )

    assert result["Portfolio_itemKey"] == "999999"
    assert result["Naam"] == "Ghost"


# ---------------------------------------------------------------------------
# Mock client: isolation between instances
# ---------------------------------------------------------------------------


async def test_mock_instances_isolated():
    """Changes in one mock client don't affect another."""
    client_a = FccODataMockClient()
    client_b = FccODataMockClient()

    async with client_a:
        await client_a.create_entity("Portfolio_item", {"Naam": "Only in A"})
        a_items = await client_a.fetch_entities("Portfolio_item")

    async with client_b:
        b_items = await client_b.fetch_entities("Portfolio_item")

    assert len(a_items) == len(b_items) + 1
