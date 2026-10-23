# CONTEXT.md — where the work stands

Hand-over notes so a new Claude session (or a teammate) can continue without re-reading the
whole history. Last updated: 22 Oct 2026. Read together with [AGENTS.md](AGENTS.md) (rules),
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (design) and [README.md](README.md) (overview).
**Update this file at the end of every working session.**

## 1. Project in one paragraph

DepositTrack is the team's prototype for **SIH 2026 problem statement SIH26265** (AICTE Regulation
Bureau: "Streamline of security deposit/ FDR portal"). It manages security deposits / FDRs from
submission to release: OCR auto-fill, discrepancy flags, bank verification, maturity/renewal
tracking with reminders, release workflow, dashboard/reports and a tamper-evident audit trail.
Prototype deadline: **before 28 Oct 2026**. Maintainer: Krrish (GitHub account `dreamybear66`,
commits authored as `dreamybear66@gmail.com`). Repo: `mayank-bajaj-ai24/DepositTrack-AICTE-FDR-Management`.

## 2. Git state (important)

| Branch | State |
| --- | --- |
| `dreamybear` (local + origin) | **The working branch.** 173 commits of work minus the CI file. Open PR **#1** → `main`: https://github.com/mayank-bajaj-ai24/DepositTrack-AICTE-FDR-Management/pull/1 |
| `main` (local only) | Same work **including** `.github/workflows/ci.yml`, 173 commits ahead of `origin/main`, never pushed. Diverged from `dreamybear` (history rewritten there). Do not push it over the PR. |
| `origin/main` | Plan, README, research only. |

- Pushing anything under `.github/workflows/` fails: the `dreamybear66` gh token lacks the
  `workflow` scope. Fix (user runs in PowerShell, **without** `!`): `gh auth refresh -h github.com -s workflow`.
  A second gh account `krrish89915` has the scope but is not active and was not chosen.
- The CI workflow content exists on local `main` (`git show main:.github/workflows/ci.yml`);
  add it to `dreamybear` once the scope is granted.
- AGENTS.md still says "push straight to main"; in practice work now goes to `dreamybear` + PR.
  Ask the user before changing that rule.

## 3. User rules and preferences (follow strictly)

- **Never assume — ask** when anything is unclear; tell the user about any manual step (installs,
  accounts, keys, Docker, GitHub permissions) instead of doing it yourself.
- **No hardcoding**: rules in `apps/api/config/*.yaml`; synthetic data lists in
  `ml/synth/fdrsynth/data/synthetic_lists.json`; web URLs in `apps/web/.env.local`.
- **No invented AICTE values**: `policy.example.yaml` stays all-`null`; demo values only in
  `policy.demo.yaml`, each labelled "DEMO PLACEHOLDER - not an AICTE rule".
- **Many small Conventional Commits**; **no AI attribution** in commits or PRs.
- **Update README** progress in the same push as the work.
- **UI work uses the taste-skill plugin** (installed at `~/.claude/plugins/marketplaces/taste-skill`).
  21st.dev only on its free plan (not worth it; taste-skill only).
- Docker: user will start Docker Desktop; the stack must be tested before submission.
- Team rules/decisions taken in conversation: no officer assistant (LLM) for now; OCR = RapidOCR;
  LayoutLMv3 is trained by the user on Colab with `ml/layoutlm/train_layoutlmv3_fdr.ipynb`;
  object storage = SeaweedFS (MinIO no longer publishes images); UI = English + Hindi, DepositTrack
  brand only (no AICTE logo); deck (SIH PPT) is on hold.

## 4. What is implemented

### Infrastructure — `infra/`
Docker Compose: PostgreSQL 16 + pgvector, Redis, SeaweedFS (S3), Keycloak 26.8 (realm import with
7 roles and one dev user per role, e.g. `scrutiny.demo` / `dev-only-scrutiny`), immudb. Config
validated; **never actually started** (Docker Desktop was not running).

### Backend — `apps/api` (FastAPI, SQLAlchemy 2, Alembic; 315 tests pass, ruff clean)
| Area | Where | Notes |
| --- | --- | --- |
| Auth M1 | `app/core/security.py`, `permissions.py`, `access.py` | Keycloak JWT (JWKS), role matrix, ABAC: institution / region / bank scoping via `user_account` |
| Data model | `app/models/`, migrations `0001`–`0004` | 19 tables incl. obligation/coverage, field_value (declared / extracted A+B / bank), notification, system_setting |
| Intake M2 | `modules/instruments/intake.py`, `modules/storage/store.py` | Fernet-encrypted docs (local or S3), versioned, SHA-256 |
| Extraction M3/N6 | `modules/extraction/` + `config/extraction.yaml` | RapidOCR; pass B = config rules; pass A = LayoutLMv3 when `models/layoutlmv3-fdr/` exists |
| Checks M4/N7/N8 | `modules/checks/`, `config/checks.yaml` | Flags carry fact/rule/clause/reason; double pledge (+IFSC lineage), near-duplicate, amount-in-words, continuity gap on late renewal |
| Forgery N6 | `modules/forgery/` | RGB-GLCM + ELA + ink + copy-move features per OCR line; SVM; grey/suspicious bands |
| Bank M5/N3/N4 | `modules/bank/` | Pinned Ed25519 keys, credential verify, field compare → Trust L3/L4, freshness decay, status re-check |
| Lifecycle M7/N2 | `modules/lifecycle/` + `config/workflow.yaml` | State machine, role-gated transitions, coverage curves + first-gap forecast, daily sweep with demo clock |
| Alerts M8 | `modules/alerts/`, `config/alerts.yaml` | One notification per threshold/audience; overdue, coverage gap, risk, case time boxes |
| Release M9/N5 | `modules/release/` | Policy checklist, blockers, mandatory reason, release letter PDF (marked PROTOTYPE), bank lien removal |
| Audit M6/N10 | `modules/audit/` + `config/conformance.yaml` | Hash chain per instrument, Merkle anchors over `anchor_event` membership (optional immudb receipt, read back with a verified get on verification; `[anchoring]` extra), file verifier, conformance replay (constraints unvalidated) |
| Risk N9 | `modules/risk/` | LightGBM + SHAP reasons from DB history; scored in the sweep |
| Reports M10 | `app/api/dashboard.py` | Dashboard tiles, coverage endpoint, 4 reports as JSON/CSV/XLSX |
| Seed | `app/seed.py`, `seed/demo_seed.json` | 5 fictional institutions, accounts for Keycloak dev users, demo obligations, synthetic FDRs through real intake |

### Mock bank — `services/mock-bank` (48 tests)
Separate FastAPI service. The ledger starts empty: the bank records each FDR it issued (operator
page at `/`, `python -m mockbank register` or `POST /fdrs`; insert-only, one `Ledger.insert`;
writes are locked across processes and replaced atomically, so `register` is safe while `serve`
runs).
Per-bank signing keys; `/keys` publishes every code in `MB_BANK_CODES` from the start (empty:
codes appear with their first FDR, then re-pin). `/credentials`, `/status`, `/lien/remove`,
`/simulate/close`. Two tokens: `MB_API_TOKEN` (DepositTrack: `/keys`, `/credentials`, `/status`,
`/lien/remove`) and `MB_OPERATOR_TOKEN` (bank operator: `/fdrs`, `/ledger`, `/simulate/close`);
they must differ. Settings documented in `.env.example`.

### ML — `ml/`
- `ml/synth`: synthetic watermarked FDR generator with word-level labels (22 tests).
- `ml/forgery/train.py` + `tamper.py`; `ml/risk/train.py` + `simulate.py`; `ml/layoutlm/*.ipynb`.
- Trained models go to `models/` (gitignored). Present locally: `models/forgery`, `models/renewal_risk`.
- Synthetic-data results: extraction 100% on 30 pages (3.4 s/page); forgery recall 0.875 at 5.4%
  false alarms (copy-paste weakest, 0.53); renewal-risk AUC 0.780, mean lead time 26 days.
- Not built: discrepancy-risk XGBoost from the plan; officer assistant (skipped).

### Web — `apps/web` (Next.js 16.4, React 19; ESLint, tsc and build pass)
- taste-skill **achromatic-ledger** style (seed 549180210): blue-grey ground `#f2f4f7`, one hue
  `#1d5fbf` on attested coverage / current month; no sidebar, top-bar shell. Signature element:
  **coverage strip** (`components/CoverageStrip.tsx`); **Trust Ladder** steps (`components/ui.tsx`).
- Screens: `/overview`, `/queue`, `/instruments`, `/instruments/[id]`, `/cases`, `/cases/[id]`,
  `/reports`, `/audit`, `/verify`, `/admin` (demo clock, sweep, key pinning, anchoring),
  `/my`, `/my/submit` (scan auto-fill), `/my/request/[id]`, `/bank`, `/auth/callback`.
- i18n: `src/i18n/en.json`, `hi.json` (Hindi written by Claude — **needs a fluent reviewer**).
- Next 16 notes: read `node_modules/next/dist/docs/` first; Cache Components on, so
  `useParams`/`useSearchParams` must be inside `<Suspense>`; React 19 lint forbids setState in effects.
- **Never opened in a browser yet**; taste-skill `inspect.mjs --app` not run.

## 5. How to run locally (once Docker is up)

```bash
cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
# API: apps/api/.env needs DT_DATABASE_URL, DT_STORAGE_ENCRYPTION_KEY (Fernet), DT_S3_ACCESS_KEY/SECRET_KEY
#      (match infra/seaweedfs/s3.json), DT_POLICY_FILE=config/policy.demo.yaml, DT_BANK_API_TOKEN, DT_MODELS_DIR=../../models
cd apps/api && .venv/Scripts/alembic upgrade head && .venv/Scripts/python -m app.seed demo --synthetic ../../data/forgery-src --count 12
.venv/Scripts/uvicorn app.main:app --reload
# Mock bank: cp services/mock-bank/.env.example services/mock-bank/.env (MB_API_TOKEN = DT_BANK_API_TOKEN;
#            MB_OPERATOR_TOKEN is the bank operator's own, different token for the page at http://localhost:8090)
cd services/mock-bank && .venv/Scripts/python -m mockbank serve --port 8090
# The bank ledger starts empty; record each FDR the bank issued on the operator page, or (safe while serve runs):
.venv/Scripts/python -m mockbank register --ifsc <IFSC> --fdr-no <no> --amount <INR> --issue-date <YYYY-MM-DD> --maturity-date <YYYY-MM-DD> --beneficiary "<text>" --depositor "<name>"
# Web
cd apps/web && npm run dev
```
Then: admin → pin bank keys; verifying officer → "Verify with bank". An FDR gets "the bank has no
record of this FDR" until it is registered at the mock bank with its true values.
Virtualenvs already exist in `apps/api/.venv`, `ml/synth/.venv`, `services/mock-bank/.venv`.
Synthetic data in `data/` (gitignored).

## 6. Next steps (in order)

1. User starts Docker Desktop → bring up the stack, write the `.env` files, migrate, seed, start
   API + mock bank + web; log in with each dev user and walk the demo story (plan §12).
2. Run taste-skill checks on every screen: `node <skill>/scripts/lint.mjs --app apps/web/src` and
   `node <skill>/scripts/inspect.mjs --app http://localhost:3000/...`; fix FAILs, look at the
   screenshots at 1440/768/390, up to three rounds.
3. When the user grants the `workflow` scope: add `.github/workflows/ci.yml` to `dreamybear`.
4. User runs the LayoutLMv3 Colab notebook → unzip into `models/layoutlmv3-fdr/`; install
   `transformers` + `torch` in `apps/api/.venv` to enable pass A.
5. Improvement candidates: forgery copy-paste recall; risk AUC (<0.80 target); discrepancy-risk model.
6. Open items needing AICTE answers: plan §14 (amounts, wording, release conditions, approvers,
   reminder days, integrations).
