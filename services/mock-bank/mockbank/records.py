"""What the issuing bank records about an FDR, and the one way to record it.

Both POST /fdrs and `python -m mockbank register` go through `FdrRecord` and
`record_issued_fdr`, so the same input is accepted or refused the same way on both paths.
"""

from datetime import date
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from mockbank.ledger import Ledger
from mockbank.settings import Settings


class FdrRecord(BaseModel):
    """What the issuing bank knows about an FDR it issued (entered by the bank, not AICTE)."""

    # Leading/trailing spaces would become part of the ledger key and break later lookups.
    model_config = ConfigDict(str_strip_whitespace=True)

    fdr_no: str = Field(min_length=1, max_length=64)
    ifsc: str = Field(pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    # Rupees with paise. At most 15 digits, so the JSON number round-trips exactly.
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    issue_date: date
    maturity_date: date
    beneficiary: str = Field(min_length=1)
    depositor: str = Field(min_length=1)

    @field_validator("ifsc", mode="before")
    @classmethod
    def _ifsc_upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _maturity_after_issue(self) -> "FdrRecord":
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self

    @field_serializer("amount", when_used="json")
    def _amount_number(self, amount: Decimal) -> int | float:
        # A JSON number, as in the credential schema (plan N3): whole rupees stay an integer
        # (500000), paise keep two places (500000.5). DepositTrack's comparison normalises both
        # to the same text ("500000" / "500000.50").
        return int(amount) if amount == amount.to_integral_value() else float(amount)


class NotIssuedHere(ValueError):
    """The FDR's bank code is not one this mock bank issues for (MB_BANK_CODES)."""


def record_issued_fdr(record: FdrRecord, settings: Settings) -> dict:
    """Add an FDR the bank issued to its ledger.

    Insert-only: raises AlreadyRecorded if the FDR is on the ledger already, NotIssuedHere if
    MB_BANK_CODES is set and does not include the FDR's bank code.
    """
    bank = record.ifsc[:4]
    if settings.issuing_banks and bank not in settings.issuing_banks:
        raise NotIssuedHere(
            f"bank code {bank} is not one this mock bank issues FDRs for "
            f"(MB_BANK_CODES={settings.bank_codes})"
        )
    return Ledger(settings.ledger_file).insert(record.model_dump(mode="json"))
