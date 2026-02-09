from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    DATABASE_URL: str = (
        "postgresql+asyncpg://bouwmeester:bouwmeester@localhost:5432/bouwmeester"
    )
    APP_NAME: str = "Bouwmeester"
    DEBUG: bool = False

    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    ANTHROPIC_API_KEY: str = ""
    TK_API_BASE_URL: str = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0"
    EK_API_BASE_URL: str = "https://opendata.eerstekamer.nl"
    TK_POLL_INTERVAL_SECONDS: int = 3600
    TK_IMPORT_LIMIT: int = 100
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    ENABLED_IMPORT_TYPES: list[str] = ["motie"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
