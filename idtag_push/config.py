from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://idtag_push:idtag_push@127.0.0.1:5432/idtag_push"
    http_host: str = "0.0.0.0"
    http_port: int = 7004
    socket_host: str = "0.0.0.0"
    socket_port: int = 7002
    api_key: SecretStr = Field(min_length=16)
    socket_secret: SecretStr = Field(min_length=16)
    worker_poll_seconds: float = 1.0
    max_attempts: int = 8
    dry_run: bool = True

    fcm_project_id: str | None = None
    fcm_service_account_file: Path | None = None

    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_key_file: Path | None = None
    apns_topic: str | None = None
    apns_use_sandbox: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
