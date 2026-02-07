from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
