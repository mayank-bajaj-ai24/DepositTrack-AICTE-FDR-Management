from pathlib import Path

import pytest
import yaml

from fdrsynth.catalog import load_catalog

# Excerpts of the real public master data, shared with the API's tests.
ROOT = Path(__file__).resolve().parents[3]
API_CONFIG = ROOT / "apps" / "api" / "config"
FIXTURES = ROOT / "apps" / "api" / "tests" / "fixtures" / "masterdata"
INSTITUTIONS = FIXTURES / "institutions_2024-2025.json"
# The extractor's rules: tests compare against these, never against copies of them.
RULES = yaml.safe_load((API_CONFIG / "extraction.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(FIXTURES, INSTITUTIONS)
