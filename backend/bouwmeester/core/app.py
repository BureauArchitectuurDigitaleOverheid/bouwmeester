import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session, close_db, init_db
from bouwmeester.core.session_store import DatabaseSessionStore, run_cleanup_loop
from bouwmeester.middleware.auth_required import AuthRequiredMiddleware
from bouwmeester.middleware.csrf import CSRFMiddleware
from bouwmeester.middleware.session import ServerSideSessionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    from bouwmeester.core.whitelist import load_whitelist

    load_whitelist()
    cleanup_task = asyncio.create_task(run_cleanup_loop(app.state.session_store))
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    from bouwmeester.core.auth import close_http_client

    await close_http_client()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    session_store = DatabaseSessionStore(
        session_factory=async_session,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
        encryption_key=settings.SESSION_SECRET_KEY,
    )
    app.state.session_store = session_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    app.add_middleware(
        CSRFMiddleware,
        cookie_domain=settings.SESSION_COOKIE_DOMAIN,
        cookie_secure=settings.SESSION_COOKIE_SECURE,
    )

    app.add_middleware(
        AuthRequiredMiddleware,
        oidc_configured=bool(settings.OIDC_ISSUER),
        settings=settings,
    )

    app.add_middleware(
        ServerSideSessionMiddleware,
        store=session_store,
        secret_key=settings.SESSION_SECRET_KEY,
        cookie_domain=settings.SESSION_COOKIE_DOMAIN,
        cookie_secure=settings.SESSION_COOKIE_SECURE,
        cookie_max_age=settings.SESSION_TTL_SECONDS,
    )

    from bouwmeester.api.routes import api_router

    app.include_router(api_router, prefix="/api")

    @app.get("/api/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready")
    async def readiness() -> dict[str, str]:
        from bouwmeester.core.database import async_session

        async with async_session() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app
