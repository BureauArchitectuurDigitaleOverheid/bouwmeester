"""Shared fixtures for API tests.

Uses the running PostgreSQL database with per-test transaction rollback
so tests never commit real data.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import get_db

settings = get_settings()


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
    """HTTPX async client talking to the FastAPI app with overridden DB session."""
    from bouwmeester.core.app import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def sample_node(db_session: AsyncSession):
    """Create a corpus node for testing."""
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
