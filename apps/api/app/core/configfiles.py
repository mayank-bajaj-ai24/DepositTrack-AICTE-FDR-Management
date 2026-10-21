"""Cached loaders for the YAML configuration files in apps/api/config/."""

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@lru_cache
def load_config(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def workflow() -> dict:
    return load_config("workflow.yaml")


def checks() -> dict:
    return load_config("checks.yaml")
