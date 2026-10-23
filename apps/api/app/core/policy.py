"""Load the policy configuration and expose typed, null-aware accessors.

Every AICTE-specific value may be null (unconfirmed, plan §14). Accessors return None
in that case and callers must treat the feature as "awaiting AICTE policy".
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def load_policy(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Policy file {path} must contain a mapping")
    return data


def unconfirmed_keys(policy: dict[str, Any]) -> list[str]:
    """Top-level policy entries that still have a null value (pending AICTE, plan §14)."""
    pending = []
    for key, entry in policy.items():
        if not isinstance(entry, dict):
            continue
        values = [v for k, v in entry.items() if k != "source"]
        if any(v is None for v in values):
            pending.append(key)
    return sorted(pending)


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    label: str
    evidence: str


@dataclass(frozen=True)
class Policy:
    raw: dict[str, Any]

    def _entry(self, key: str) -> dict[str, Any]:
        entry = self.raw.get(key)
        return entry if isinstance(entry, dict) else {}

    @property
    def version(self) -> str:
        return str(self.raw.get("policy_version", "unknown"))

    @property
    def is_demo(self) -> bool:
        return bool(self.raw.get("demo", False))

    @property
    def accepted_kinds(self) -> list[str] | None:
        return self._entry("accepted_instrument_kinds").get("value")

    @property
    def deposit_requirements(self) -> list[dict] | None:
        return self._entry("deposit_requirements").get("value")

    @property
    def beneficiary_wording(self) -> str | None:
        return self._entry("beneficiary_wording").get("value")

    @property
    def reminder_days(self) -> list[int] | None:
        days = self._entry("reminders").get("days_before_maturity")
        return sorted(days, reverse=True) if days else None

    @property
    def escalation_chain(self) -> list[str] | None:
        return self._entry("reminders").get("escalation_chain")

    @property
    def release_approver_role(self) -> str | None:
        value = self._entry("release_conditions").get("value") or {}
        return value.get("approver_role")

    @property
    def release_checklist(self) -> list[ChecklistItem] | None:
        value = self._entry("release_conditions").get("value")
        if not value:
            return None
        return [ChecklistItem(i["id"], i["label"], i["evidence"]) for i in value["checklist"]]

    @property
    def require_bank_attestation_for_active(self) -> bool | None:
        return self._entry("require_bank_attestation_for_active").get("value")

    @property
    def query_response_days(self) -> int | None:
        return self._entry("time_boxes").get("institution_query_response_days")

    @property
    def officer_action_days(self) -> int | None:
        return self._entry("time_boxes").get("officer_action_days")

    @property
    def unconfirmed(self) -> list[str]:
        return unconfirmed_keys(self.raw)


@lru_cache
def get_policy(path: str) -> Policy:
    return Policy(load_policy(path))
