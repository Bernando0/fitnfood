"""Typed settings loaded from the environment / .env file."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str

    # OpenAI-compatible LLM endpoint (alem.ai / Gemma).
    llm_base_url: str = "https://llm.alem.ai/v1"
    llm_api_key: str
    llm_model: str = "gemma4"

    allowed_chat_id: int | None = None
    tz: str = "Asia/Almaty"
    daily_report_hour: int = 22
    db_path: str = "data/fitfood.db"

    @field_validator("allowed_chat_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        # An empty value in .env (ALLOWED_CHAT_ID=) means "any chat".
        if v in ("", None):
            return None
        return v


settings = Settings()
