"""Guards AGENTS.md rule 3: no invented AICTE values in the shipped policy config."""

from pathlib import Path

from app.core.policy import load_policy, unconfirmed_keys

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "policy.example.yaml"


def test_example_policy_loads():
    assert load_policy(EXAMPLE)["policy_version"].endswith("unconfirmed")


def test_every_aicte_value_is_unconfirmed():
    policy = load_policy(EXAMPLE)
    entries = [k for k, v in policy.items() if isinstance(v, dict)]
    assert unconfirmed_keys(policy) == sorted(entries)


def test_no_source_without_value():
    """A value is only filled when its AICTE source is recorded alongside it."""
    for key, entry in load_policy(EXAMPLE).items():
        if not isinstance(entry, dict):
            continue
        filled = any(v is not None for k, v in entry.items() if k != "source")
        if filled:
            assert entry.get("source"), f"{key} has a value but no source"
