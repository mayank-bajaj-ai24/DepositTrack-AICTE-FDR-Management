"""Random but well-formed FDR field values.

Banks, branches and institutions are fictional. Amounts and tenures are random and
are NOT AICTE requirements (those are unconfirmed, plan §14).
"""

import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta

# Fictional banks: (display name, 4-letter IFSC prefix). Prefixes start with X or Z
# so they cannot collide with a real bank's code by accident.
BANKS = [
    ("Example National Bank", "XNBK"),
    ("Sample Co-operative Bank", "XSCB"),
    ("Demo Federal Bank", "ZDFB"),
    ("Placeholder Union Bank", "ZPUB"),
    ("Mock Rural Bank", "XMRB"),
    ("Specimen City Bank", "ZSCB"),
]

CITIES = ["Nagpur", "Pune", "Bhopal", "Jaipur", "Lucknow", "Kochi", "Guwahati", "Indore"]

INSTITUTION_WORDS = ["Synthetic", "Sample", "Demo", "Model"]
INSTITUTION_KINDS = [
    "Institute of Technology",
    "College of Engineering",
    "School of Management",
    "Polytechnic",
]

# Placeholder lien wording: the real required wording is unconfirmed (plan §14, Q2).
LIEN_TEXT = "Lien marked in favour of AICTE (synthetic placeholder wording)"

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
    tenure_months: int
    depositor: str
    beneficiary: str
    lien_text: str

    def as_dict(self) -> dict:
        return asdict(self)


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


def amount_in_words(amount: int) -> str:
    """Indian numbering: crore, lakh, thousand. 1500000 -> 'Rupees Fifteen Lakh Only'."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    crore, rest = divmod(amount, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    thousand, rest = divmod(rest, 1000)
    parts = []
    if crore:
        parts.append(f"{amount_in_words_plain(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if rest:
        parts.append(_three_digits(rest))
    return f"Rupees {' '.join(parts)} Only"


def amount_in_words_plain(n: int) -> str:
    return amount_in_words(n).removeprefix("Rupees ").removesuffix(" Only")


def indian_format(amount: int) -> str:
    """1500000 -> 'Rs. 15,00,000/-'."""
    digits = str(amount)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"Rs. {digits}/-"


def make_ifsc(rng: random.Random, prefix: str) -> str:
    return f"{prefix}0{rng.randint(0, 999999):06d}"


def random_values(rng: random.Random) -> FDRValues:
    bank, prefix = rng.choice(BANKS)
    city = rng.choice(CITIES)
    amount = rng.randint(1, 100) * 50_000
    deposit = date(2024, 1, 1) + timedelta(days=rng.randint(0, 900))
    tenure = rng.choice([12, 24, 36, 60])
    maturity = deposit + timedelta(days=round(tenure * 30.4375))
    institution = (
        f"{rng.choice(INSTITUTION_WORDS)} {rng.choice(INSTITUTION_KINDS)}, {rng.choice(CITIES)}"
    )
    return FDRValues(
        fdr_no=f"{prefix[:2]}{rng.randint(10**9, 10**10 - 1)}",
        bank=bank,
        branch=f"{city} Main Branch",
        ifsc=make_ifsc(rng, prefix),
        amount=amount,
        amount_text=indian_format(amount),
        amount_words=amount_in_words(amount),
        deposit_date=deposit.strftime("%d/%m/%Y"),
        maturity_date=maturity.strftime("%d/%m/%Y"),
        tenure_months=tenure,
        depositor=institution,
        beneficiary="AICTE, New Delhi",
        lien_text=LIEN_TEXT,
    )
