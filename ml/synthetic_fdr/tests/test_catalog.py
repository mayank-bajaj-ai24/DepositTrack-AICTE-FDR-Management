import json

import pytest

from fdrsynth.catalog import (
    default_institutions,
    load_api_config,
    load_branches,
    load_institutions,
    load_placeholders,
    repair_text,
)
from tests.conftest import API_CONFIG, FIXTURES, INSTITUTIONS, RULES


def _ifsc_dir(tmp_path, banks: dict, rows: list[str], sublet: dict | None = None):
    (tmp_path / "banks.json").write_text(json.dumps(banks), encoding="utf-8")
    (tmp_path / "sublet.json").write_text(json.dumps(sublet or {}), encoding="utf-8")
    (tmp_path / "IFSC.csv").write_text(
        "BANK,IFSC,BRANCH,CENTRE,CITY\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )
    return tmp_path


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


def test_sublet_keys_are_matched_in_upper_case(tmp_path):
    path = _ifsc_dir(
        tmp_path,
        {"HDFC": {"type": "Private"}},
        ["HDFC Bank,HDFC0000001,NARIMAN POINT,MUMBAI,Mumbai", "Other Bank,HDFC0CAACOB,X,Y,Z"],
        sublet={"hdfc0caacob": "AACX"},
    )
    assert [b.ifsc for b in load_branches(path, ["Private"])] == ["HDFC0000001"]


def test_bank_on_the_page_is_the_ifsc_prefixs_bank(tmp_path):
    path = _ifsc_dir(
        tmp_path,
        {"YESB": {"type": "Private"}},
        [
            "Yes Bank,YESB0000001,FORT,MUMBAI,Mumbai",
            "Amravati District Central Co-operative Bank,YESB0ADB002,AMRAVATI,AMRAVATI,Amravati",
        ],
    )
    assert [(b.bank, b.ifsc) for b in load_branches(path, ["Private"])] == [
        ("Yes Bank", "YESB0000001")
    ]


def test_payment_office_and_member_bank_rows_are_not_branches(tmp_path):
    path = _ifsc_dir(
        tmp_path,
        {"BARB": {"type": "PSB"}, "IBKL": {"type": "Private"}},
        [
            "Bank of Baroda,BARB0000001,MANDVI,MUMBAI,Mumbai",
            "Bank of Baroda,BARB0TREASU,Bank of Baroda IMPS,NA,Mumbai",
            "Bank of Baroda,BARB0000RTG,RTGS-HO,MUMBAI,Mumbai",
            "Bank of Baroda,BARB0CPPC01,CPPC CENTRE,MUMBAI,Mumbai",
            "IDBI,IBKL0000001,NARIMAN POINT,MUMBAI,Mumbai",
            "IDBI,IBKL0069S11,THE SIRSI URBAN SAHAKARI BANK LIMITED,SIRSI,Uttar Kannad",
        ],
    )
    ifscs = [b.ifsc for b in load_branches(path, ["PSB", "Private"])]
    assert ifscs == ["BARB0000001", "IBKL0000001"]


def test_merged_banks_are_excluded():
    merged = load_api_config(API_CONFIG).merged_banks
    assert {"ANDB", "SYNB", "VIJB"} <= merged
    branches = load_branches(FIXTURES, ["PSB", "Foreign"], merged)
    assert not {b.ifsc[:4] for b in branches} & merged


def test_branch_names_are_tidied(tmp_path):
    path = _ifsc_dir(
        tmp_path, {"BARB": {"type": "PSB"}}, ['Bank of Baroda,BARB0KOVURX,"KOVUR ,NELLORE",K,Kovur']
    )
    assert load_branches(path, ["PSB"])[0].branch == "KOVUR,NELLORE"


def test_missing_master_data_names_the_fetch_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch-banks"):
        load_branches(tmp_path, ["PSB"])
    with pytest.raises(FileNotFoundError, match="fetch-institutions"):
        load_institutions(tmp_path / "institutions.json")


def test_institutions_keep_their_aicte_id():
    snapshot = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    ids = {i.aicte_id for i in load_institutions(INSTITUTIONS)}
    assert ids == {item["row"][0] for item in snapshot["rows"]}


def test_short_snapshot_row_is_refused_like_the_api_does(tmp_path):
    snapshot = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    snapshot["rows"][0]["row"] = snapshot["rows"][0]["row"][:2]
    path = tmp_path / "s.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError, match="fewer than"):
        load_institutions(path)


def test_mis_decoded_names_are_repaired():
    assert repair_text("WOMENâ\u0080\u0099S  COLLEGE") == "WOMEN’S COLLEGE"
    assert repair_text("PLAIN COLLEGE") == "PLAIN COLLEGE"


def test_default_snapshot_follows_the_configured_academic_year():
    assert default_institutions(API_CONFIG).name == "institutions_2024-2025.json"


def test_captions_and_fields_come_from_extraction_yaml():
    config = load_api_config(API_CONFIG)
    assert config.fields == tuple(name.upper() for name in RULES["fields"])
    assert config.captions["FDR_NO"] == tuple(RULES["fields"]["fdr_no"]["captions"])


def test_placeholders_refuse_missing_keys(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"bank_types": ["PSB"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing keys"):
        load_placeholders(path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"amount": {"step_inr": 50000, "min_steps": 0, "max_steps": 10}}, "amount"),
        ({"amount": {"step_inr": 0, "min_steps": 1, "max_steps": 10}}, "amount"),
        ({"amount": {"step_inr": 50000, "min_steps": 9, "max_steps": 2}}, "min_steps"),
        ({"deposit_date": {"start": "2021-01-01", "span_days": -1}}, "span_days"),
        ({"deposit_date": {"start": "soon", "span_days": 10}}, "start"),
        ({"tenure_months": [12, 0]}, "tenure_months"),
    ],
)
def test_placeholders_refuse_bad_ranges(tmp_path, change, message):
    data = load_placeholders() | change
    path = tmp_path / "p.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_placeholders(path)
