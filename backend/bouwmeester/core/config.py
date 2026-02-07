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


@lru_cache
def get_settings() -> Settings:
    return Settings()
