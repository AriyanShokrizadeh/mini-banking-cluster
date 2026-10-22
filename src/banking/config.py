"""Single validated source of configuration; no secrets printed to logs."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BANKING_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Mini Banking Cluster"
    instance_name: str = Field(default="banking-a", min_length=1, max_length=64)
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    max_concurrent_requests: int = Field(default=50, ge=1, le=10000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    database_url: SecretStr | None = None
    db_pool_size: int = Field(default=3, ge=1, le=20)
    db_max_overflow: int = Field(default=2, ge=0, le=20)
    db_connect_timeout: int = Field(default=3, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=10000, ge=1000, le=120000)
    db_pool_timeout: int = Field(default=5, ge=1, le=30)
    transaction_retry_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("database_url")
    @classmethod
    def validate_ysql_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        url = value.get_secret_value()
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError("BANKING_DATABASE_URL must use postgresql+psycopg://")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
