"""Parse an amount written in words (Indian numbering) back to a number."""

import re

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
          "lac": 100_000, "crore": 10_000_000, "crores": 10_000_000}  # fmt: skip
IGNORED = {"rupees", "rupee", "rs", "only", "and", "inr"}


def words_to_amount(text: str) -> int | None:
    """'Rupees Twenty Four Lakh Fifty Thousand Only' -> 2450000. None if unparseable."""
    tokens = [t for t in re.split(r"[\s,-]+", text.lower()) if t and t not in IGNORED]
    if not tokens:
        return None
    total, current = 0, 0
    for token in tokens:
        if token in UNITS:
            current += UNITS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        elif token in SCALES:
            total += (current or 1) * SCALES[token]
            current = 0
        else:
            return None
    return total + current
