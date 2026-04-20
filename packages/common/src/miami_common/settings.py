"""Environment configuration loaded from env vars with optional .env fallback."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database — three roles enforce the snapshot_owner / app / feature_compute split.
    db_url_app: str = Field(alias="MIAMI_DB_URL_APP")
    db_url_feature_compute: str = Field(alias="MIAMI_DB_URL_FEATURE_COMPUTE")
    db_url_owner: str = Field(alias="MIAMI_DB_URL_OWNER")

    dev_mode: bool = Field(default=True, alias="MIAMI_DEV_MODE")

    # External source credentials. Empty in dev mode.
    pricecharting_api_key: str = Field(default="", alias="PRICECHARTING_API_KEY")
    pokemontcg_api_key: str = Field(default="", alias="POKEMONTCG_API_KEY")
    ebay_oauth_token: str = Field(default="", alias="EBAY_OAUTH_TOKEN")
    psa_api_key: str = Field(default="", alias="PSA_API_KEY")

    # FastAPI <-> Next.js tokens.
    fastapi_service_token: str = Field(alias="FASTAPI_SERVICE_TOKEN")
    pipeline_revalidate_token: str = Field(alias="PIPELINE_REVALIDATE_TOKEN")
    next_public_api_url: str = Field(default="http://localhost:8000", alias="NEXT_PUBLIC_API_URL")

    # Observability + storage.
    sentry_dsn_api: str = Field(default="", alias="SENTRY_DSN_API")
    blob_read_write_token: str = Field(default="", alias="BLOB_READ_WRITE_TOKEN")
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    alerts_from_email: str = Field(default="alerts@example.com", alias="ALERTS_FROM_EMAIL")

    env: Literal["dev", "staging", "prod"] = Field(default="dev", alias="MIAMI_ENV")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
