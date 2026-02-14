import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.gzip import GZipMiddleware

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session, close_db, init_db
from bouwmeester.core.session_store import DatabaseSessionStore, run_cleanup_loop
from bouwmeester.middleware.auth_required import AuthRequiredMiddleware
from bouwmeester.middleware.csrf import CSRFMiddleware
from bouwmeester.middleware.session import ServerSideSessionMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()

    from bouwmeester.core.whitelist import (
        refresh_whitelist_cache,
        seed_admins_from_file,
    )

    async with async_session() as session:
        await seed_admins_from_file(session)
        await refresh_whitelist_cache(session)
        await session.commit()

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
        version="1.0.0",
        description=(
            "Policy corpus management API for the Dutch government (BZK). "
            "Manages policy dossiers, goals, instruments, measures, and their "
            "relationships as a directed graph.\n\n"
            "**Authentication:** Use `Authorization: Bearer bm_...` for agent "
            "API keys, or OIDC session tokens for browser users.\n\n"
            "**Agent guide:** `GET /api/skill.md` returns a comprehensive "
            "Markdown skill document for LLM agents."
        ),
        debug=settings.DEBUG,
        lifespan=lifespan,
        redirect_slashes=False,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_tags=[
            {"name": "nodes", "description": "Corpus nodes"},
            {"name": "edges", "description": "Edges between nodes"},
            {"name": "edge-types", "description": "Edge type definitions"},
            {"name": "tasks", "description": "Tasks on corpus nodes"},
            {"name": "people", "description": "Users and agents"},
            {"name": "organisatie", "description": "Org hierarchy"},
            {"name": "tags", "description": "Hierarchical tags"},
            {"name": "search", "description": "Full-text search"},
            {"name": "graph", "description": "Graph views and paths"},
            {"name": "activity", "description": "Audit log"},
            {"name": "notifications", "description": "Messages"},
            {"name": "parlementair", "description": "Parliamentary imports"},
            {"name": "mentions", "description": "Mention search"},
            {"name": "bijlage", "description": "File attachments"},
            {"name": "import-export", "description": "Bulk import/export"},
            {"name": "admin", "description": "Admin operations"},
            {"name": "skill", "description": "Agent skill document"},
            {"name": "auth", "description": "Authentication"},
        ],
    )

    session_store = DatabaseSessionStore(
        session_factory=async_session,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
        encryption_key=settings.SESSION_SECRET_KEY,
    )
    app.state.session_store = session_store

    # ---- Middleware registration order ----
    # Starlette's add_middleware *prepends*, so the LAST added middleware
    # becomes the OUTERMOST layer.  Request flow (outermost → innermost):
    #
    #   CORS → Session → Auth → CSRF → Route handler
    #
    # CORS MUST be outermost so that ALL responses (including error
    # responses short-circuited by Auth/CSRF middleware, and any
    # unhandled-exception 500s from inner layers) carry the correct
    # Access-Control-Allow-Origin header.  Without this, the browser
    # blocks the response and JS only sees "Failed to fetch".

    # GZip is the innermost middleware — compresses responses ≥500 bytes.
    app.add_middleware(GZipMiddleware, minimum_size=500)

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

    # CORS must be added LAST so it is the outermost middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        expose_headers=["Content-Disposition"],
    )

    from bouwmeester.api.routes import api_router

    app.include_router(api_router, prefix="/api")

    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Catch Pydantic ValidationError during response serialisation.

        Without this handler, a schema constraint violation on *output* data
        (e.g. a title exceeding max_length) results in a bare 500 with no log
        entry.  We log the full error details so the root cause is immediately
        visible, and return a descriptive JSON body.
        """
        logger.error(
            "Response serialisation error on %s %s: %s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Response serialisation error — stored data does "
                "not match the response schema.",
                "errors": [
                    {
                        "loc": list(e["loc"]),
                        "msg": e["msg"],
                        "type": e["type"],
                    }
                    for e in exc.errors()
                ],
            },
        )

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
