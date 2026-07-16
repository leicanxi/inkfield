from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_version: str = "dev"
    database_url: str
    redis_url: str
    token_signing_key: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    policy_config_version: str = "policy-v1"
    prompt_config_version: str = "prompt-v1"
    correlation_header: str = "X-Correlation-ID"
    service_name: str = "yantian-backend"

    @field_validator("token_signing_key")
    @classmethod
    def validate_signing_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("TOKEN_SIGNING_KEY must contain at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+"):
            raise ValueError("DATABASE_URL must use an explicit PostgreSQL SQLAlchemy driver")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
