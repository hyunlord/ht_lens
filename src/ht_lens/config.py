"""Application settings (Phase 0 minimal).

Phase 2+에서 LLM provider, DB path 등을 추가한다.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_prefix="HT_LENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
