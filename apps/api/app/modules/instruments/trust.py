"""Trust Ladder computation (N1)."""

from datetime import UTC, datetime

from app.core.configfiles import workflow
from app.models import FieldValue
from app.modules.lifecycle.states import TrustLevel


def _same(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    try:
        return float(a) == float(b)
    except ValueError:
        return a.replace(" ", "").upper() == b.replace(" ", "").upper()


def machine_level(fv: FieldValue, flagged: bool, threshold: float) -> TrustLevel:
    """L1 when the scan agrees with the declared value, confidently, and nothing is flagged."""
    if (
        not flagged
        and _same(fv.declared, fv.extracted_b or fv.extracted_a)
        and (fv.confidence or 0) >= threshold
    ):
        return TrustLevel.MACHINE_CHECKED
    return TrustLevel.DECLARED


def effective_level(fv: FieldValue, now: datetime | None = None) -> int:
    """L4 decays to L3 once its freshness window has passed (N4)."""
    level = fv.trust_level
    if level == TrustLevel.LIVE_CONFIRMED and fv.fresh_until is not None:
        fresh = fv.fresh_until if fv.fresh_until.tzinfo else fv.fresh_until.replace(tzinfo=UTC)
        if fresh < (now or datetime.now(UTC)):
            return int(TrustLevel.BANK_ATTESTED)
    return level


def instrument_level(values: list[FieldValue], now: datetime | None = None) -> int:
    """The weakest key field decides the instrument's trust level."""
    keys = set(workflow()["key_fields"])
    levels = [effective_level(fv, now) for fv in values if fv.field in keys]
    return min(levels) if len(levels) == len(keys) else int(TrustLevel.DECLARED)
