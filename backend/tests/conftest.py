"""Shared fixtures for API tests.

Uses the running PostgreSQL database with per-test transaction rollback
so tests never commit real data.
"""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import get_db
from bouwmeester.core.session_store import SessionStore

settings = get_settings()


class InMemorySessionStore(SessionStore):
    """Simple in-memory session store for tests (no DB connections)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> dict[str, Any] | None:
        return self._data.get(session_id)

    async def set(self, session_id: str, data: dict[str, Any]) -> None:
        self._data[session_id] = data

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)

    async def cleanup(self) -> int:
        return 0


@pytest.fixture
async def db_session():
    """Yield a session wrapped in a transaction that is rolled back after the test."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    """HTTPX async client talking to the FastAPI app with overridden DB session.

    Automatically obtains a CSRF token and injects it into all
    state-changing requests so existing tests pass without modification.
    """
    from bouwmeester.core.app import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    # Use an in-memory session store to avoid opening extra DB connections
    # (which exhaust the pool during parallel test runs).
    mem_store = InMemorySessionStore()
    app.state.session_store = mem_store
    # Also patch the session middleware's store reference.
    for mw in app.user_middleware:
        if hasattr(mw, "kwargs") and "store" in mw.kwargs:
            mw.kwargs["store"] = mem_store

    # Rebuild the middleware stack after patching.
    app.middleware_stack = app.build_middleware_stack()

    csrf = {"token": ""}

    async def _inject_csrf(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and csrf["token"]:
            request.headers["X-CSRF-Token"] = csrf["token"]

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        event_hooks={"request": [_inject_csrf]},
    ) as ac:
        # Bootstrap: GET to obtain CSRF cookie (uses in-memory store, no DB).
        init_resp = await ac.get("/api/auth/status")
        for cookie_header in init_resp.headers.get_list("set-cookie"):
            if cookie_header.startswith("bm_csrf="):
                csrf["token"] = cookie_header.split("=", 1)[1].split(";")[0]
                break
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def sample_node(db_session: AsyncSession):
    """Create a corpus node (dossier) for testing."""
    from bouwmeester.models.corpus_node import CorpusNode

    node = CorpusNode(
        id=uuid.uuid4(),
        title="Test dossier",
        node_type="dossier",
        description="Testomschrijving",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()
    return node


@pytest.fixture
async def second_node(db_session: AsyncSession):
    """Create a second corpus node (doel) for testing."""
    from bouwmeester.models.corpus_node import CorpusNode

    node = CorpusNode(
        id=uuid.uuid4(),
        title="Test doel",
        node_type="doel",
        description="Doelomschrijving",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()
    return node


@pytest.fixture
async def sample_person(db_session: AsyncSession):
    """Create a person for testing."""
    from bouwmeester.models.person import Person

    person = Person(
        id=uuid.uuid4(),
        naam="Jan Tester",
        email="jan@example.com",
        functie="beleidsmedewerker",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    return person


@pytest.fixture
async def second_person(db_session: AsyncSession):
    """Create a second person for testing."""
    from bouwmeester.models.person import Person

    person = Person(
        id=uuid.uuid4(),
        naam="Piet Tester",
        email="piet@example.com",
        functie="adviseur",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    return person


@pytest.fixture
async def sample_edge_type(db_session: AsyncSession):
    """Create an edge type for testing."""
    from bouwmeester.models.edge_type import EdgeType

    et = EdgeType(
        id="test_relatie",
        label_nl="Test relatie",
        label_en="Test relation",
        description="Een test relatie",
        is_custom=True,
    )
    db_session.add(et)
    await db_session.flush()
    return et


@pytest.fixture
async def sample_edge(
    db_session: AsyncSession, sample_node, second_node, sample_edge_type
):
    """Create an edge between sample_node and second_node."""
    from bouwmeester.models.edge import Edge

    edge = Edge(
        id=uuid.uuid4(),
        from_node_id=sample_node.id,
        to_node_id=second_node.id,
        edge_type_id=sample_edge_type.id,
        weight=1.0,
        description="Test edge",
    )
    db_session.add(edge)
    await db_session.flush()
    return edge


@pytest.fixture
async def sample_organisatie(db_session: AsyncSession):
    """Create an organisatie-eenheid for testing."""
    from bouwmeester.models.org_naam import OrganisatieEenheidNaam
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test Ministerie",
        type="ministerie",
        beschrijving="Een test ministerie",
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(
        OrganisatieEenheidNaam(
            eenheid_id=org.id, naam=org.naam, geldig_van=date.today()
        )
    )
    await db_session.flush()
    return org


@pytest.fixture
async def child_organisatie(db_session: AsyncSession, sample_organisatie):
    """Create a child organisatie-eenheid for testing."""
    from bouwmeester.models.org_naam import OrganisatieEenheidNaam
    from bouwmeester.models.org_parent import OrganisatieEenheidParent
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test Directie",
        type="directie",
        parent_id=sample_organisatie.id,
        beschrijving="Een test directie",
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(
        OrganisatieEenheidNaam(
            eenheid_id=org.id, naam=org.naam, geldig_van=date.today()
        )
    )
    db_session.add(
        OrganisatieEenheidParent(
            eenheid_id=org.id,
            parent_id=sample_organisatie.id,
            geldig_van=date.today(),
        )
    )
    await db_session.flush()
    return org


@pytest.fixture
async def sample_task(db_session: AsyncSession, sample_node, sample_person):
    """Create a task for testing."""
    from bouwmeester.models.task import Task

    task = Task(
        id=uuid.uuid4(),
        title="Test taak",
        description="Een test taak",
        node_id=sample_node.id,
        assignee_id=sample_person.id,
        status="open",
        priority="normaal",
    )
    db_session.add(task)
    await db_session.flush()
    return task


@pytest.fixture
async def sample_tag(db_session: AsyncSession):
    """Create a tag for testing."""
    from bouwmeester.models.tag import Tag

    tag = Tag(
        id=uuid.uuid4(),
        name="Test tag",
        description="Een test tag",
    )
    db_session.add(tag)
    await db_session.flush()
    return tag


@pytest.fixture
async def sample_notification(db_session: AsyncSession, sample_person, second_person):
    """Create a notification for testing."""
    from bouwmeester.models.notification import Notification

    notif = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="direct_message",
        title="Test notificatie",
        message="Een test bericht",
        sender_id=second_person.id,
        is_read=False,
    )
    db_session.add(notif)
    await db_session.flush()
    return notif


@pytest.fixture
async def third_person(db_session: AsyncSession):
    """Create a third person (manager) for testing."""
    from bouwmeester.models.person import Person

    person = Person(
        id=uuid.uuid4(),
        naam="Klaas Manager",
        email="klaas@example.com",
        functie="manager",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    return person


@pytest.fixture
async def org_with_manager(db_session: AsyncSession, third_person):
    """Create an org unit with a temporal manager record."""
    from bouwmeester.models.org_manager import OrganisatieEenheidManager
    from bouwmeester.models.org_naam import OrganisatieEenheidNaam
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Test Afdeling",
        type="afdeling",
        beschrijving="Afdeling met manager",
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(
        OrganisatieEenheidNaam(
            eenheid_id=org.id, naam=org.naam, geldig_van=date.today()
        )
    )
    db_session.add(
        OrganisatieEenheidManager(
            eenheid_id=org.id,
            manager_id=third_person.id,
            geldig_van=date.today() - timedelta(days=30),
        )
    )
    await db_session.flush()
    return org


@pytest.fixture
async def org_with_legacy_manager(db_session: AsyncSession, third_person):
    """Create an org unit with only legacy manager_id (no temporal record)."""
    from bouwmeester.models.org_naam import OrganisatieEenheidNaam
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Legacy Afdeling",
        type="afdeling",
        beschrijving="Afdeling met legacy manager",
        manager_id=third_person.id,
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(
        OrganisatieEenheidNaam(
            eenheid_id=org.id, naam=org.naam, geldig_van=date.today()
        )
    )
    await db_session.flush()
    return org
