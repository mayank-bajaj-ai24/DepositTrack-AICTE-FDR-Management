import random
import re

import pytest

from fdrsynth.values import BANKS, amount_in_words, indian_format, random_values

IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (50_000, "Rupees Fifty Thousand Only"),
        (100_000, "Rupees One Lakh Only"),
        (1_500_000, "Rupees Fifteen Lakh Only"),
        (2_550_000, "Rupees Twenty Five Lakh Fifty Thousand Only"),
        (10_000_000, "Rupees One Crore Only"),
        (
            12_345_678,
            "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Only",
        ),
    ],
)
def test_amount_in_words(amount, expected):
    assert amount_in_words(amount) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (500, "Rs. 500/-"),
        (50_000, "Rs. 50,000/-"),
        (1_500_000, "Rs. 15,00,000/-"),
        (12_345_678, "Rs. 1,23,45,678/-"),
    ],
)
def test_indian_format(amount, expected):
    assert indian_format(amount) == expected


def test_values_are_well_formed():
    rng = random.Random(1)
    for _ in range(200):
        v = random_values(rng)
        assert IFSC.match(v.ifsc)
        assert v.amount > 0
        assert v.amount_text == indian_format(v.amount)


def test_only_fictional_bank_prefixes():
    assert all(prefix[0] in "XZ" for _, prefix in BANKS)


def test_same_seed_same_values():
    assert random_values(random.Random(42)) == random_values(random.Random(42))
