from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="coursegraph-dev", repr=False)
    coursegraph_backend: Literal["neo4j", "memory"] = "neo4j"
    coursegraph_api_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    search_limit: int = 8
    llm_provider: Literal["none", "openai", "gemini"] = "none"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = Field(default=None, repr=False)
    gemini_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

