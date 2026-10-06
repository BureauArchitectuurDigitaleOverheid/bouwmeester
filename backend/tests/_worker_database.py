"""A database of its own for every pytest-xdist worker.

Every test with ``db_session`` starts by deleting the edge schema rules the
migrations seed, inside its own transaction.  That delete locks those rows
until the test rolls back.  With one database for all workers, every other
worker waits for that lock in its own setup: the suite ran one test at a
time, however many workers there were, and three quarters of the time on the
clock was waiting.

So a worker migrates a database of its own, next to the configured one, and
points ``DATABASE_URL`` at it.  Nothing a test does can then hold up a test
in another worker.  A side effect worth having: under xdist the tests no
longer see whatever is in a developer's database.

Without xdist (``-n 0``, ``-p no:xdist``) nothing changes: the tests use the
configured database, as before.
"""

import asyncio
import contextlib
import os
import re
import subprocess
import sys
import time
import uuid
import warnings
from pathlib import Path

import asyncpg
from sqlalchemy.engine import URL, make_url

_BACKEND = Path(__file__).resolve().parent.parent

# A run that was killed leaves its databases behind.  The next run drops
# those, but only when they are old enough that no run can still be using
# them: two runs at the same time (two worktrees, one Postgres) must not
# drop each other's database.
_STALE_AFTER_SECONDS = 6 * 60 * 60


def _connect(url: URL, database: str | None = None):
    return asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=database or url.database,
    )


async def _create(base: URL, name: str) -> None:
    prefix = f"{base.database}_test_"
    conn = await _connect(base)
    try:
        rows = await conn.fetch(
            "SELECT datname FROM pg_database WHERE datname LIKE $1",
            prefix.replace("_", r"\_") + "%",
        )
        now = time.time()
        for row in rows:
            match = re.fullmatch(
                re.escape(prefix) + r"(\d+)_[0-9a-f]+_gw\d+", row["datname"]
            )
            if match and now - int(match.group(1)) > _STALE_AFTER_SECONDS:
                # Another worker of this run may be dropping it right now.
                with contextlib.suppress(asyncpg.PostgresError):
                    await conn.execute(
                        f'DROP DATABASE IF EXISTS "{row["datname"]}" WITH (FORCE)'
                    )
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop(base: URL, name: str) -> None:
    conn = await _connect(base)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


def use_worker_database() -> tuple[URL, str] | None:
    """Create and migrate this worker's database and point the settings at it.

    Must run before the first ``get_settings()``.  Returns what
    ``drop_worker_database`` needs, or ``None`` when the tests stay on the
    configured database.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return None

    from bouwmeester.core.config import Settings

    configured = Settings()
    if configured.DATABASE_SCHEMA:
        # A schema inside a database somebody else owns: leave it alone.
        return None
    base = make_url(configured.DATABASE_URL)
    name = f"{base.database}_test_{int(time.time())}_{uuid.uuid4().hex[:8]}_{worker}"

    try:
        asyncio.run(_create(base, name))
    except asyncpg.InsufficientPrivilegeError:
        warnings.warn(
            "This database user may not create databases, so all xdist "
            "workers share one database and wait for each other's locks.",
            stacklevel=2,
        )
        return None

    worker_url = base.set(database=name).render_as_string(hide_password=False)
    # A process of its own: Alembic's env.py configures logging and caches
    # the settings, and neither should happen inside the test process.
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND,
        env={**os.environ, "DATABASE_URL": worker_url},
        capture_output=True,
        text=True,
    )
    if migrated.returncode != 0:
        asyncio.run(_drop(base, name))
        raise RuntimeError(
            f"Could not migrate the test database of {worker}:\n{migrated.stderr}"
        )

    os.environ["DATABASE_URL"] = worker_url
    return base, name


def drop_worker_database(created: tuple[URL, str]) -> None:
    base, name = created
    # Cleaning up must not turn a green run red; the next run sweeps what
    # is left behind.
    with contextlib.suppress(asyncpg.PostgresError, OSError):
        asyncio.run(_drop(base, name))
