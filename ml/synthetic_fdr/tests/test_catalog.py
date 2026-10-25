import json

import pytest

from fdrsynth.catalog import load_branches, load_institutions, load_placeholders
from tests.conftest import FIXTURES, INSTITUTIONS


def test_branches_only_from_the_wanted_bank_types():
    banks = json.loads((FIXTURES / "banks.json").read_text(encoding="utf-8"))
    branches = load_branches(FIXTURES, ["PSB"])
    assert branches
    assert all(banks[b.ifsc[:4]]["type"] == "PSB" for b in branches)


def test_sublet_ifscs_are_excluded():
    sublet = json.loads((FIXTURES / "sublet.json").read_text(encoding="utf-8"))
    banks = json.loads((FIXTURES / "banks.json").read_text(encoding="utf-8"))
    every_type = sorted({b.get("type") for b in banks.values()})
    branches = load_branches(FIXTURES, [t for t in every_type if t])
    assert not {b.ifsc for b in branches} & set(sublet)


def test_missing_master_data_names_the_fetch_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch-banks"):
        load_branches(tmp_path, ["PSB"])
    with pytest.raises(FileNotFoundError, match="fetch-institutions"):
        load_institutions(tmp_path / "institutions.json")


def test_institutions_keep_their_aicte_id():
    snapshot = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    ids = {i.aicte_id for i in load_institutions(INSTITUTIONS)}
    assert ids == {item["row"][0] for item in snapshot["rows"]}


def test_placeholders_refuse_missing_keys(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"bank_types": ["PSB"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing keys"):
        load_placeholders(path)


def test_member_banks_using_a_sponsor_ifsc_are_excluded(tmp_path):
    (tmp_path / "banks.json").write_text(json.dumps({"IBKL": {"type": "Private"}}))
    (tmp_path / "IFSC.csv").write_text(
        "BANK,IFSC,BRANCH,CENTRE,CITY\n"
        "IDBI,IBKL0069S11,THE SIRSI URBAN SAHAKARI BANK LIMITED,SIRSI,Uttar Kannad\n"
        "IDBI,IBKL0000001,NARIMAN POINT,MUMBAI,Mumbai\n",
        encoding="utf-8",
    )
    assert [b.ifsc for b in load_branches(tmp_path, ["Private"])] == ["IBKL0000001"]
