from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives at the repo root; docker compose injects env directly.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    openai_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_emails: Annotated[list[str], NoDecode] = []
    session_secret: str = ""
    fernet_key: str = ""
    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    extraction_model: str = "gpt-6.1-sol"
    mapping_model: str = "gpt-6.1-terra"
    analyze_model: str = "gpt-6.1-terra"
    embedding_model: str = "text-embedding-3-small"

    worker_concurrency: int = 3
    poll_seconds: int = 60

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def _split_emails(cls, v):
        if isinstance(v, str):
            return [e.strip().lower() for e in v.split(",") if e.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
