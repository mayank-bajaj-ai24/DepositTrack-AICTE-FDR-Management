import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MB_", env_file=".env", extra="ignore")

    # Shared token the DepositTrack API presents (stands in for mutual TLS). Required.
    api_token: str = ""
    # Bank codes (first four IFSC letters) this mock bank issues FDRs for, comma-separated
    # (fictional codes only). GET /keys publishes a key for each one even while the ledger is
    # empty, so AICTE can pin them before any FDR is recorded, and recording an FDR under any
    # other bank code is refused. Empty: any bank code is accepted, and its key is published once
    # the first FDR for it is recorded (AICTE then pins it with another "Pin bank keys").
    bank_codes: str = ""
    ledger_file: str = "var/ledger.json"
    keys_dir: str = "var/keys"
    # How long a status confirmation stays fresh before it must be re-checked (N4).
    freshness_hours: int = 24

    @field_validator("bank_codes")
    @classmethod
    def _bank_codes_are_four_letters(cls, value: str) -> str:
        codes = [code.strip().upper() for code in value.split(",") if code.strip()]
        bad = [code for code in codes if not re.fullmatch(r"[A-Z]{4}", code)]
        if bad:
            raise ValueError(f"MB_BANK_CODES must be four-letter bank codes, got {bad}")
        return ",".join(sorted(set(codes)))

    @property
    def issuing_banks(self) -> list[str]:
        return self.bank_codes.split(",") if self.bank_codes else []


@lru_cache
def get_settings() -> Settings:
    return Settings()
