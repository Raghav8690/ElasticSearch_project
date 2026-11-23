"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the read-only RERA explorer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    es_url: str = "http://192.168.1.14:9200"
    es_timeout_seconds: float = 15
    es_max_connections: int = 20

    es_username: str = ""
    es_password: str = ""
    es_api_key: str = ""
    es_verify_certs: bool = True

    index_rera: str = "gujrat_rera_data"
    pipeline_id: str = "gujrat_normalize_pipeline"
    allow_writes: bool = False

    request_timeout_seconds: float = 20
    pit_keep_alive: str = "2m"
    pit_ttl_seconds: float = 90

    @property
    def host(self) -> str:
        """Host (scheme-less netloc) safe to show in the browser. No credentials."""
        return urlparse(self.es_url).netloc or self.es_url


settings = Settings()
