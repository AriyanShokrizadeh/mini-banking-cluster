"""Settings used by tests without reading the developer environment file."""

from pydantic_settings import SettingsConfigDict

from banking.config import Settings


class IsolatedSettings(Settings):
    model_config = SettingsConfigDict(env_prefix="TEST_BANKING_", env_file=None, extra="ignore")
