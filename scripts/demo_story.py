"""Walk the demo story (plan §12) against a running stack, with synthetic FDRs.

Needs the stack from AGENTS.md "Common commands" running (Compose, API on :8000 with
config/policy.demo.yaml, mock bank on :8090), master data imported, `app.seed demo` run
with --institution-user-aicte-id, and three synthetic FDRs for that institution:

    apps/api/.venv/Scripts/python -m fdrsynth --count 3 --out data/synthetic_fdr/demo --seed 31 \\
        --institutions <AICTE snapshot holding only the linked institution>
    apps/api/.venv/Scripts/python scripts/demo_story.py --fdrs data/synthetic_fdr/demo

Story: the bank records the FDRs it issued; the institution uploads a scan (OCR auto-fill)
and submits; scrutiny verifies; the verifier checks with the bank (signed credential, Trust
L4) and activates; the sweep sends reminders and marks an unrenewed matured FDR overdue; a
wrong declared amount raises explained flags; a release is blocked until its checklist is
done, then approved, and the bank removes the lien; audit events are anchored (immudb
receipt), and a submitted file is verified byte for byte. Uses the Keycloak dev users and
the development-only tokens from the .env.example files; every FDR is synthetic.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

OIDC_ENDPOINT = "/realms/depositrack/protocol/openid-connect/token"
USERS = {
    "institution": ("institution.demo", "dev-only-institution"),
    "scrutiny": ("scrutiny.demo", "dev-only-scrutiny"),
    "verifier": ("verifier.demo", "dev-only-verifier"),
    "authority": ("authority.demo", "dev-only-authority"),
    "auditor": ("auditor.demo", "dev-only-auditor"),
    "admin": ("admin.demo", "dev-only-admin"),
}


class Story:
    def __init__(self, args):
        self.api, self.bank, self.fdrs = f"{args.api}/api/v1", args.bank, args.fdrs
        self.operator = {"Authorization": f"Bearer {args.operator_token}"}
        self.h = {
            role: self._token(args.keycloak, *cred) for role, cred in USERS.items()
        }
        self.failures = 0

    @staticmethod
    def _token(keycloak: str, user: str, password: str) -> dict:
        r = httpx.post(
            keycloak + OIDC_ENDPOINT,
            data={
                "grant_type": "password",
                "client_id": "depositrack-dev-cli",
                "username": user,
                "password": password,
            },
        )
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def step(self, title: str, r: httpx.Response, expect: int | None = None) -> dict:
        ok = r.status_code == expect if expect else r.is_success
        self.failures += not ok
        print(f"[{'ok' if ok else 'FAIL'}] {title} ({r.status_code})")
        if not ok:
            print(f"       {r.text[:300]}")
        is_json = r.headers.get("content-type", "").startswith("application/json")
        return r.json() if is_json else {}

    def get(self, role: str, path: str, **kw) -> dict:
        return httpx.get(self.api + path, headers=self.h[role], timeout=60, **kw).json()

    def post(self, role: str, path: str, **kw) -> httpx.Response:
        return httpx.post(self.api + path, headers=self.h[role], timeout=120, **kw)

    def sample(self, index: int) -> tuple[dict, dict, bytes]:
        records = sorted(
            p for p in self.fdrs.glob("*.json") if p.stem.startswith("fdr_")
        )
        path = records[index]
        bank = next(
            json.loads(line)
            for line in (self.fdrs / "mockbank.jsonl").read_text().splitlines()
            if json.loads(line)["id"] == path.stem
        )
        bank.pop("id")
        return json.loads(path.read_text()), bank, path.with_suffix(".png").read_bytes()

    def submit(self, png: bytes, declared: dict | None = None) -> str:
        scan = {"file": ("fdr.png", png, "image/png")}
        if declared is None:
            preview = self.step(
                "institution uploads the scan: OCR auto-fill",
                self.post("institution", "/extract", files=scan),
            )
            declared = {
                k: v["value"] for k, v in preview["fields"].items() if v["value"]
            }
            print(f"       read: {json.dumps(declared)[:200]}")
        body = {"declared": json.dumps(declared), "kind": "fdr"}
        created = self.step(
            "institution submits",
            self.post("institution", "/instruments", data=body, files=scan),
        )
        return created["id"]

    def activate(self, iid: str) -> None:
        self.step(
            "scrutiny officer: -> verified",
            self.post(
                "scrutiny",
                f"/instruments/{iid}/transition",
                json={
                    "target": "verified",
                    "reason": "fields checked against the scan",
                },
            ),
        )
        bank = self.step(
            "verifier: verify with bank",
            self.post("verifier", f"/instruments/{iid}/bank-verification"),
        )
        print(
            f"       bank result: {bank.get('result')}, trust level {bank.get('trust_level')}"
        )
        self.step(
            "verifier: -> active",
            self.post(
                "verifier",
                f"/instruments/{iid}/transition",
                json={"target": "active", "reason": "bank attested"},
            ),
        )

    def run(self) -> int:
        samples = [self.sample(i) for i in range(3)]
        for _, bank, _ in samples:
            self.step(
                "bank operator records an FDR it issued",
                httpx.post(f"{self.bank}/fdrs", json=bank, headers=self.operator),
            )
        self.step(
            "admin pins the bank keys", self.post("admin", "/admin/bank-keys/pin")
        )

        # 1. Upload -> extraction -> scrutiny -> bank -> active, for the first two FDRs.
        ids = []
        for record, _, png in samples[:2]:
            iid = self.submit(png)
            detail = self.get("scrutiny", f"/instruments/{iid}")
            flags = [f["type"] for f in detail["flags"]]
            print(
                f"       {record['values']['fdr_no']}: state {detail['instrument']['state']}, "
                f"flags {flags or 'none'}"
            )
            self.activate(iid)
            ids.append(iid)

        # 2. Sweep: reminders, and an FDR past maturity without renewal becomes overdue.
        sweep = self.step(
            "admin runs the lifecycle sweep", self.post("admin", "/admin/sweep")
        )
        print(
            f"       moved {len(sweep.get('moved', []))}, notifications "
            f"{sweep.get('notifications')}"
        )
        tiles = self.get("scrutiny", "/dashboard")["tiles"]
        print(f"       dashboard: {json.dumps(tiles)}")

        # 3. A wrong declared amount: explained flags.
        record, _, png = samples[2]
        v = record["values"]
        wrong = {
            "fdr_no": v["fdr_no"],
            "ifsc": v["ifsc"],
            "amount": str(v["amount"] * 10),
            "issue_date": v["deposit_date_iso"],
            "maturity_date": v["maturity_date_iso"],
            "depositor": v["depositor"],
            "beneficiary": v["beneficiary"],
            "bank": v["bank"],
        }
        bad = self.submit(png, wrong)
        for f in self.get("scrutiny", f"/instruments/{bad}")["flags"]:
            print(f"       flag {f['type']} [{f['severity']}]: {f['reason']}")

        # 4. Release of an active FDR: blocked until the checklist is done, then approved.
        active = next(
            i
            for i in ids
            if self.get("scrutiny", f"/instruments/{i}")["instrument"]["state"]
            == "active"
        )
        case = self.step(
            "institution requests release",
            self.post(
                "institution",
                f"/instruments/{active}/release-requests",
                json={
                    "case_type": "release",
                    "reason": "approval withdrawn by the institution",
                },
            ),
        )
        cid = case["id"]
        self.step(
            "authority approval is blocked while the checklist is open",
            self.post(
                "authority",
                f"/cases/{cid}/decision",
                json={"approve": True, "reason": "x"},
            ),
            409,
        )
        order = {
            "file": ("order.pdf", b"%PDF-1.4 synthetic demo order", "application/pdf")
        }
        self.step(
            "institution uploads the closure order",
            self.post(
                "institution",
                f"/cases/{cid}/evidence",
                params={"item_id": "closure_order"},
                files=order,
            ),
        )
        self.step(
            "institution declares no pending dues",
            self.post(
                "institution",
                f"/cases/{cid}/checklist/no_pending_dues",
                json={"note": "none"},
            ),
        )
        self.step(
            "scrutiny officer recommends release",
            self.post(
                "scrutiny",
                f"/cases/{cid}/checklist/officer_scrutiny",
                json={"note": "in order"},
            ),
        )
        self.step(
            "competent authority approves",
            self.post(
                "authority",
                f"/cases/{cid}/decision",
                json={"approve": True, "reason": "all conditions met"},
            ),
        )
        released = self.get("scrutiny", f"/instruments/{active}")
        print(
            f"       state {released['instrument']['state']}, "
            f"lien marked {released['lien_marked']}"
        )

        # 5. Audit: anchor with an immudb receipt, chains, file verification.
        anchor = self.step(
            "admin anchors the audit events", self.post("admin", "/audit/anchors")
        )
        print(
            f"       {anchor.get('events')} events, store_error {anchor.get('store_error')}"
        )
        latest = (self.get("auditor", "/audit/anchors").get("items") or [{}])[0]
        print(
            f"       anchor valid {latest.get('valid')}, receipt {latest.get('receipt')}"
        )
        _, _, png = samples[0]
        for title, data, want in (
            ("the submitted scan", png, 1),
            ("an edited copy", png + b"\0", 0),
        ):
            found = self.step(
                f"verify {title}",
                self.post(
                    "auditor",
                    "/verify-file",
                    files={"file": ("f.png", data, "image/png")},
                ),
            )
            if len(found.get("matches", [])) != want:
                self.failures += 1
                print(f"       expected {want} match(es)")
        print(f"\n{self.failures} step(s) failed")
        return 1 if self.failures else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fdrs", type=Path, required=True, help="output of python -m fdrsynth"
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--keycloak", default="http://localhost:8080")
    parser.add_argument("--bank", default="http://127.0.0.1:8090")
    parser.add_argument(
        "--operator-token",
        default="dev-only-change-me-operator-token",
        help="MB_OPERATOR_TOKEN of the mock bank (development-only default)",
    )
    sys.exit(Story(parser.parse_args()).run())


if __name__ == "__main__":
    main()
