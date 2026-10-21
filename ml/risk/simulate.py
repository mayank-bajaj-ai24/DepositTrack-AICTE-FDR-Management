"""Event-log simulator for renewal-risk training (plan §9.1).

Institutions get a behaviour persona (punctual, slow, chronically late, fraud-prone).
Each has several years of FDR cycles: maturity, renewal submission date (or never),
query response times and other actions. All data is synthetic.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta

PERSONAS = {
    # name: (share, probability a renewal is late, mean response days, flags rate)
    "punctual": (0.45, 0.04, 4, 0.2),
    "slow": (0.30, 0.22, 12, 0.6),
    "chronic_late": (0.15, 0.62, 25, 1.0),
    "fraud_prone": (0.10, 0.40, 18, 2.5),
}


@dataclass
class Cycle:
    maturity: date
    submitted: date | None  # renewal submission date; None = never renewed
    amount: float


@dataclass
class Institution:
    persona: str
    cycles: list[Cycle]
    responses: list[tuple[date, float]]  # (date answered, days taken)
    actions: list[date]
    flags_rate: float


def _persona(rng: random.Random) -> str:
    roll, total = rng.random(), 0.0
    for name, (share, *_rest) in PERSONAS.items():
        total += share
        if roll <= total:
            return name
    return "punctual"


def simulate_institution(rng: random.Random, start: date, years: int) -> Institution:
    persona = _persona(rng)
    _, p_late, mean_response, flags_rate = PERSONAS[persona]
    # Individual variation around the persona, plus a drift over time.
    p_late = min(0.95, max(0.01, rng.gauss(p_late, 0.06)))
    cycles, responses, actions = [], [], []
    current = start + timedelta(days=rng.randint(0, 200))
    amount = rng.randint(2, 60) * 50_000.0
    end = start + timedelta(days=365 * years)
    while current < end:
        tenure = rng.choice([365, 730, 1095])
        maturity = current + timedelta(days=tenure)
        late = rng.random() < p_late
        if late:
            submitted = None if rng.random() < 0.15 else maturity + timedelta(days=rng.randint(1, 90))
        else:
            submitted = maturity - timedelta(days=rng.randint(1, 80))
        cycles.append(Cycle(maturity, submitted, amount))
        # queries during the cycle
        for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
            asked = current + timedelta(days=rng.randint(0, max(1, tenure - 1)))
            taken = max(1.0, rng.expovariate(1 / mean_response))
            responses.append((asked + timedelta(days=int(taken)), taken))
        # ordinary actions (uploads, replies, logins that write events)
        for _ in range(rng.randint(2, 8)):
            actions.append(current + timedelta(days=rng.randint(0, tenure)))
        if submitted:
            actions.append(submitted)
        current = submitted if submitted and submitted < maturity else maturity
        p_late = min(0.95, max(0.01, p_late + rng.gauss(0, 0.03)))
    return Institution(persona, cycles, responses, sorted(actions), flags_rate)


def simulate(n: int, seed: int, start: date = date(2018, 1, 1), years: int = 7) -> list[Institution]:
    rng = random.Random(seed)
    return [simulate_institution(rng, start, years) for _ in range(n)]
