from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Database — either provide DATABASE_URL directly, or the ZAD platform
    # env vars (DATABASE_SERVER_HOST, etc.) and it will be constructed.
    DATABASE_URL: str = ""
    DATABASE_SERVER_HOST: str = ""
    DATABASE_SERVER_PORT: str = "5432"
    DATABASE_SERVER_USER: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_DB: str = ""
    DATABASE_SCHEMA: str = ""

    APP_NAME: str = "Bouwmeester"
    DEBUG: bool = False

    # OIDC — either provide OIDC_ISSUER directly, or the ZAD platform
    # env vars (OIDC_URL + OIDC_REALM) and it will be constructed.
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = ""
    OIDC_URL: str = ""
    OIDC_REALM: str = ""

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "https://component-1.bouwmeester.rijks.app",
    ]

    ANTHROPIC_API_KEY: str = ""
    TK_API_BASE_URL: str = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0"
    EK_API_BASE_URL: str = "https://opendata.eerstekamer.nl"
    TK_POLL_INTERVAL_SECONDS: int = 3600
    TK_IMPORT_LIMIT: int = 100
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    ENABLED_IMPORT_TYPES: list[str] = ["motie", "kamervraag", "toezegging"]

    @model_validator(mode="after")
    def _derive_database_url(self) -> "Settings":
        """Build DATABASE_URL from ZAD individual env vars if not set."""
        if not self.DATABASE_URL and self.DATABASE_SERVER_HOST:
            password = quote_plus(self.DATABASE_PASSWORD)
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DATABASE_SERVER_USER}"
                f":{password}"
                f"@{self.DATABASE_SERVER_HOST}"
                f":{self.DATABASE_SERVER_PORT}"
                f"/{self.DATABASE_DB}"
            )
        if not self.DATABASE_URL:
            self.DATABASE_URL = "postgresql+asyncpg://bouwmeester:bouwmeester@localhost:5432/bouwmeester"
        return self

    @model_validator(mode="after")
    def _derive_oidc_issuer(self) -> "Settings":
        """Build OIDC_ISSUER from ZAD env vars if not set."""
        if not self.OIDC_ISSUER and self.OIDC_URL and self.OIDC_REALM:
            self.OIDC_ISSUER = f"{self.OIDC_URL.rstrip('/')}/realms/{self.OIDC_REALM}"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
