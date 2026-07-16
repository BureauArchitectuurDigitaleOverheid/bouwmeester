"""Tests voor WorkerLock: Postgres session-advisory-lock als singleton-guard
voor de background worker.

Zonder deze lock kunnen twee overlappende worker-processen (bv. tijdens een
deploy waarbij de oude pod nog niet is opgeruimd) allebei een Mattermost-
websocket openen en dezelfde posts verwerken — zie de race in
``test_mattermost_ingest.py::test_post_link_row_exists_before_suggestion_side_effect``
voor het directe gevolg daarvan. De lock voorkomt dat een tweede instantie
ooit begint te draaien."""

import uuid

from bouwmeester.core.worker_lock import WorkerLock

# Elke test gebruikt een eigen willekeurige lock-key zodat tests niet met
# elkaar (of met een echt draaiende worker tijdens lokale dev) om dezelfde
# advisory lock botsen.


def _random_key() -> int:
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


async def test_acquire_succeeds_when_unheld(_test_engine):
    lock = WorkerLock(_test_engine, key=_random_key())
    try:
        assert await lock.acquire() is True
    finally:
        await lock.release()


async def test_second_acquire_on_same_key_fails_while_first_holds_it(_test_engine):
    key = _random_key()
    first = WorkerLock(_test_engine, key=key)
    second = WorkerLock(_test_engine, key=key)
    try:
        assert await first.acquire() is True
        assert await second.acquire() is False
    finally:
        await first.release()
        await second.release()


async def test_second_acquire_succeeds_after_first_releases(_test_engine):
    key = _random_key()
    first = WorkerLock(_test_engine, key=key)
    second = WorkerLock(_test_engine, key=key)
    try:
        assert await first.acquire() is True
        await first.release()
        assert await second.acquire() is True
    finally:
        await first.release()
        await second.release()


async def test_second_acquire_succeeds_after_first_connection_closes(_test_engine):
    """Als het proces crasht zonder release (bv. OOM-kill), sluit
    Postgres de connectie en geeft de session-advisory-lock vanzelf vrij
    — de volgende worker die opstart mag dan gewoon de lock krijgen."""
    key = _random_key()
    first = WorkerLock(_test_engine, key=key)
    second = WorkerLock(_test_engine, key=key)
    try:
        assert await first.acquire() is True
        # Simuleer een crash: de onderliggende connectie sluit zonder
        # expliciete unlock. `release()` zou daarna zelf opnieuw op de
        # (dan al gesloten) connectie proberen te unlocken, dus we
        # laten `first` los zonder `release()` te callen — precies het
        # scenario dat we simuleren.
        await first._conn.close()  # noqa: SLF001
        first._conn = None  # noqa: SLF001

        assert await second.acquire() is True
    finally:
        await first.release()
        await second.release()


async def test_release_without_acquire_is_a_noop(_test_engine):
    """Release mag veilig aangeroepen worden als acquire() nooit
    (succesvol) is gedaan — bv. in een ``finally``-block na een mislukte
    acquire-poging."""
    lock = WorkerLock(_test_engine, key=_random_key())
    await lock.release()  # mag niet raisen
