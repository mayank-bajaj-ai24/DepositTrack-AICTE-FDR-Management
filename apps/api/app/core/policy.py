"""Load the policy configuration and report which AICTE values are still unconfirmed."""

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
