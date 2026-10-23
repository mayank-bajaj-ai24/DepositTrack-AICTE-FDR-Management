from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MB_", env_file=".env", extra="ignore")

    # Shared token the DepositTrack API presents (stands in for mutual TLS). Required.
    api_token: str = ""
    # Token of the bank's own operator, who records the FDRs the bank issued. Kept separate
    # from api_token so DepositTrack can read and verify the bank's records but never write them.
    operator_token: str = ""
    ledger_file: str = "var/ledger.json"
    keys_dir: str = "var/keys"
    # How long a status confirmation stays fresh before it must be re-checked (N4).
    freshness_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
