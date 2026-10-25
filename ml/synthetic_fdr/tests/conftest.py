from pathlib import Path

import pytest

from fdrsynth.catalog import load_catalog

# Excerpts of the real public master data, shared with the API's tests.
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "apps" / "api" / "tests" / "fixtures" / "masterdata"
INSTITUTIONS = FIXTURES / "institutions_2024-2025.json"


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(FIXTURES, INSTITUTIONS)
