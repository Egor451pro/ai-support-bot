from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEBHOOK_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    # Default webhook for Render; use MODE=polling locally.
    mode: Literal["polling", "webhook"] = Field(default="webhook", alias="MODE")
    database_url: str = Field(..., alias="DATABASE_URL")
    groq_api_key: str = Field(..., alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL")
    support_group_chat_id: int = Field(..., alias="SUPPORT_GROUP_CHAT_ID")
    webhook_base_url: str = Field(default="", alias="WEBHOOK_BASE_URL")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    db_ssl: bool = Field(default=True, alias="DB_SSL")
    message_history_limit: int = 8
    message_log_keep: int = 50
    faq_path: str = "data/faq.txt"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        url = value.strip().strip('"').strip("'")
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]

        parsed = urlparse(url)
        if not parsed.hostname:
            raise ValueError(
                "DATABASE_URL без хоста БД. Нужен URI вида "
                "postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres "
                "(Supabase → Project Settings → Database → Connection string → URI). "
                "Если в пароле есть @ : / # — URL-кодируйте их "
                "(@→%40, :→%3A, /→%2F, #→%23)."
            )
        if parsed.port is None and ":" in (parsed.netloc or "") and parsed.netloc.rsplit("@", 1)[-1].endswith(":"):
            raise ValueError(
                "DATABASE_URL: пустой порт после ':'. Укажите :5432 (direct) или :6543 (pooler)."
            )
        return url

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("webhook_base_url", mode="before")
    @classmethod
    def normalize_webhook_base_url(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().rstrip("/")
        return value

    @field_validator("db_ssl", mode="before")
    @classmethod
    def normalize_db_ssl(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return value

    @model_validator(mode="after")
    def validate_webhook_config(self) -> Settings:
        if self.db_ssl:
            parsed = urlparse(self.database_url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            if "ssl" not in query and "sslmode" not in query:
                query["ssl"] = "require"
                self.database_url = urlunparse(parsed._replace(query=urlencode(query)))

        if self.mode != "webhook":
            return self

        if not self.webhook_base_url.startswith("https://"):
            raise ValueError(
                "MODE=webhook требует WEBHOOK_BASE_URL с префиксом https://"
            )
        if not _WEBHOOK_SECRET_RE.fullmatch(self.webhook_secret or ""):
            raise ValueError(
                "MODE=webhook требует WEBHOOK_SECRET вида [A-Za-z0-9_-]{1,256}"
            )
        return self

    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url or not self.webhook_secret:
            return ""
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
