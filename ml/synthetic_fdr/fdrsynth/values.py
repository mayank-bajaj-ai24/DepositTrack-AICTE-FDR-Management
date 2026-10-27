"""Random but well-formed FDR field values.

Bank, branch, IFSC and depositor come from the public master data (catalog.py); amounts,
tenures, dates and wording come from the placeholder ranges. This module holds only
formatting and sampling logic.
"""

import calendar
import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from fdrsynth.catalog import Branch, Catalog

# English number words used to spell amounts in Indian numbering.
ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
    "Eighteen", "Nineteen",
]  # fmt: skip
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


@dataclass(frozen=True)
class FDRValues:
    fdr_no: str
    bank: str
    branch: str
    ifsc: str
    amount: int
    amount_text: str
    amount_words: str
    deposit_date: str
    maturity_date: str
    deposit_date_iso: str
    maturity_date_iso: str
    tenure_months: int
    depositor: str
    depositor_aicte_id: str
    beneficiary: str
    lien_text: str

    def as_dict(self) -> dict:
        return asdict(self)

    def mockbank_record(self) -> dict:
        """The same FDR as the issuing bank records it (mock bank POST /fdrs body)."""
        return {
            "fdr_no": self.fdr_no,
            "ifsc": self.ifsc,
            "amount": str(self.amount),
            "issue_date": self.deposit_date_iso,
            "maturity_date": self.maturity_date_iso,
            "beneficiary": self.beneficiary,
            "depositor": self.depositor,
        }


def _two_digits(n: int) -> str:
    return ONES[n] if n < 20 else f"{TENS[n // 10]} {ONES[n % 10]}".strip()


def _three_digits(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} Hundred")
    if rest:
        parts.append(_two_digits(rest))
    return " ".join(parts)


def _words(n: int) -> str:
    """n >= 1 in words, Indian numbering; crores above 99 are spelled the same way."""
    crore, rest = divmod(n, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    thousand, rest = divmod(rest, 1000)
    parts = []
    if crore:
        parts.append(f"{_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if rest:
        parts.append(_three_digits(rest))
    return " ".join(parts)


def amount_in_words(amount: int) -> str:
    """Indian numbering: crore, lakh, thousand. 1500000 -> 'Rupees Fifteen Lakh Only'."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    return f"Rupees {_words(amount)} Only"


def _indian_digits(amount: int) -> str:
    """1500000 -> '15,00,000' (groups of two above the last three digits)."""
    head, tail = divmod(amount, 1000)
    if not head:
        return str(tail)
    groups = []
    while head:
        head, group = divmod(head, 100)
        groups.insert(0, str(group) if not head else f"{group:02d}")
    return ",".join(groups) + f",{tail:03d}"


def indian_format(amount: int) -> str:
    """1500000 -> 'Rs. 15,00,000/-'."""
    return f"Rs. {_indian_digits(amount)}/-"


def amount_text(amount: int, rng: random.Random) -> str:
    """The figure as banks print it, in one of the forms extraction reads."""
    rupees = _indian_digits(amount)
    return rng.choice([f"Rs. {rupees}/-", f"Rs. {rupees}.00", f"INR {rupees}.00"])


def add_months(start: date, months: int) -> date:
    """Same day `months` later, clamped to the month's last day (31 Jan + 1 -> 28/29 Feb)."""
    year, month = divmod(start.month - 1 + months, 12)
    year, month = start.year + year, month + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def branch_text(branch: Branch) -> str:
    """'AMBUR Branch, Chennai'; no second 'Branch' when the name already has one."""
    if "BRANCH" in branch.branch.upper():
        return f"{branch.branch}, {branch.city}"
    return f"{branch.branch} Branch, {branch.city}"


def fdr_number(rng: random.Random) -> str:
    """Digits only or a branch-style prefix; matches extraction's FDR-number pattern."""
    digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(9, 14)))
    return rng.choice([digits, f"FD{digits}", f"{digits[:4]}/{digits[4:]}"])


def random_values(rng: random.Random, catalog: Catalog) -> FDRValues:
    branch = rng.choice(catalog.branches)
    institution = rng.choice(catalog.institutions)
    amount = rng.randint(catalog.amount_min_steps, catalog.amount_max_steps) * catalog.amount_step
    deposit = catalog.deposit_start + timedelta(days=rng.randint(0, catalog.deposit_span_days))
    tenure = rng.choice(catalog.tenure_months)
    maturity = add_months(deposit, tenure)
    date_format = rng.choice(catalog.date_formats)
    return FDRValues(
        fdr_no=fdr_number(rng),
        bank=branch.bank,
        branch=branch_text(branch),
        ifsc=branch.ifsc,
        amount=amount,
        amount_text=amount_text(amount, rng),
        amount_words=amount_in_words(amount),
        deposit_date=deposit.strftime(date_format),
        maturity_date=maturity.strftime(date_format),
        deposit_date_iso=deposit.isoformat(),
        maturity_date_iso=maturity.isoformat(),
        tenure_months=tenure,
        depositor=institution.name,
        depositor_aicte_id=institution.aicte_id,
        beneficiary=rng.choice(catalog.beneficiary),
        lien_text=rng.choice(catalog.lien_text),
    )
