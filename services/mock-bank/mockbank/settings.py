import re
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error must not print the tokens.
    model_config = SettingsConfigDict(
        env_prefix="MB_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    # Token the DepositTrack API presents (stands in for mutual TLS). Required. It reads the
    # bank's records and signed confirmations and removes AICTE's lien on release (/lien/remove);
    # it cannot record an FDR, list the ledger or record a bank-side event such as early closure.
    api_token: str = ""
    # Token of the bank's own operator, who records the FDRs the bank issued and bank-side events
    # (POST /fdrs, GET /ledger, POST /simulate/close). Required for those; must differ from
    # api_token, otherwise DepositTrack's token could write the bank's records.
    operator_token: str = ""
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

    @model_validator(mode="after")
    def _tokens_differ(self) -> "Settings":
        if self.api_token and self.api_token == self.operator_token:
            raise ValueError(
                "MB_OPERATOR_TOKEN must differ from MB_API_TOKEN: with the same value, "
                "DepositTrack's token could write the bank's ledger"
            )
        return self

    @property
    def issuing_banks(self) -> list[str]:
        return self.bank_codes.split(",") if self.bank_codes else []


@lru_cache
def get_settings() -> Settings:
    return Settings()
