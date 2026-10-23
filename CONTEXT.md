# CONTEXT.md — where the work stands

Hand-over notes so a new Claude session (or a teammate) can continue without re-reading the
whole history. Last updated: 23 Oct 2026. Read together with [AGENTS.md](AGENTS.md) (rules),
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (design) and [README.md](README.md) (overview).
**Update this file at the end of every working session.**

## 1. Project in one paragraph

DepositTrack is the team's prototype for **SIH 2026 problem statement SIH26265** (AICTE Regulation
Bureau: "Streamline of security deposit/ FDR portal"). It manages security deposits / FDRs from
submission to release: OCR auto-fill, discrepancy flags, bank verification, maturity/renewal
tracking with reminders, release workflow, dashboard/reports and a tamper-evident audit trail.
Prototype deadline: **before 28 Oct 2026**. Maintainer: Krrish (GitHub account `dreamybear66`,
commits authored as `dreamybear66@gmail.com`). Repo: `mayank-bajaj-ai24/DepositTrack-AICTE-FDR-Management`.

## 2. Git state and workflow

- **Workflow (AGENTS.md rule 1):** one branch per piece of work, named after the work; a PR to
  `main` with a description; the maintainer approves every merge. Branches are stacked when work
  depends on an open PR.
- **Merged into `main` (23 Oct):** #1 (all earlier work), #2 AICTE institution + RBI IFSC master
  data import, #3 mock bank records its own FDRs, #4 Next.js 16.4.3 security patch (squash),
  #5 officer coverage includes institutions with no deposit, #6 mock bank operator page,
  #7 immudb anchoring (receipt verified, `anchor_event` membership).
- **Open PRs:** #8 open-dataset catalog + download helper; #9 LayoutLMv3 FUNSD proxy notebook and
  removal of the synthetic generator; #10 renewal-risk proxy on BPI 2017 (stacked on #8); the
  docs PR that added this file. A forgery-model PR (Find it again!) follows when its training ends.
- **CI:** not set up. Pushing `.github/workflows/` needs the `workflow` scope on the `dreamybear66`
  gh token (user runs in PowerShell: `gh auth refresh -h github.com -s workflow`). The old CI file
  is kept on the local branch `main-local-with-ci` (`git show main-local-with-ci:.github/workflows/ci.yml`).
- Local clone: the main checkout runs the live stack from a local-only branch
  `local-integration`; feature work happens in sibling worktrees (`../wt-*`). Never use bare
  `git stash` across worktrees.

## 3. User rules and preferences (follow strictly)

- **Never assume — ask**; any plan change is agreed first. Tell the user about every manual step
  (installs, accounts, keys, Docker, GitHub permissions, Colab runs) instead of doing it.
- **No synthetic data and no hardcoded fake values** (decided 23 Oct 2026). Master data from public
  sources (AICTE dashboard, RBI IFSC master); models trained on open datasets as **labelled proxies**.
- **No step that costs money**; free tiers only (free Colab T4, free Kaggle). Ask before anything paid.
- **Usage:** stop and warn at 80% of the session token budget; continue only if the user agrees.
- **No invented AICTE values**: `policy.example.yaml` stays all-`null`; demo values only in
  `policy.demo.yaml`, each labelled "DEMO PLACEHOLDER - not an AICTE rule".
- **Many small Conventional Commits**; **no AI attribution** in commits or PRs.
- **Update README** progress in the same push as the work.
- **UI work uses the taste-skill plugin** (`~/.claude/plugins/marketplaces/taste-skill`; read its
  SKILL.md and run `lint.mjs` / `inspect.mjs --app`). 21st.dev only on its free plan.
- Decisions: no officer assistant (LLM) for now; OCR = RapidOCR; object storage = SeaweedFS; UI =
  English + Hindi, DepositTrack brand only (no AICTE logo); deck (SIH PPT) on hold.
- Proxy-model decisions: renewal risk and LayoutLMv3 pass A are **proxy only, live off**; the
  forgery model may run **live, labelled "trained on receipts (proxy)"**.
- The demo institution user is linked to **R.V. College of Engineering, AICTE ID `1-43655541828`**
  (the ID as AICTE's public dashboard lists it; the user gave the permanent ID 1-10906981, which the
  dashboard does not show). Passed with `--institution-user-aicte-id`; nothing is committed about it.
- The mock-bank operator form lives in the mock bank's own page, not in DepositTrack, so AICTE's
  system never writes bank data.

## 4. What is implemented (on `main`)

### Infrastructure — `infra/`
Docker Compose: PostgreSQL 16 + pgvector, Redis, SeaweedFS (S3), Keycloak 26.8 (realm import with
7 roles and one dev user per role, e.g. `scrutiny.demo` / `dev-only-scrutiny`), immudb. **Run end
to end on 23 Oct** with Docker Desktop: migrations, master-data import, Keycloak login, immudb anchor.

### Backend — `apps/api` (FastAPI, SQLAlchemy 2, Alembic; 377 tests pass, ruff clean)
| Area | Where | Notes |
| --- | --- | --- |
| Auth M1 | `app/core/security.py`, `permissions.py`, `access.py` | Keycloak JWT (JWKS), role matrix, ABAC via one `visible_institution_ids(scope)` used by instrument and institution scoping |
| Data model | `app/models/`, migrations `0001`–`0005` | 21 tables incl. `bank`, `bank_merger`, `anchor_event` |
| Master data M12 | `app/masterdata.py`, `modules/masterdata/`, `config/master_data.yaml`, `config/bank_mergers.yaml` | AICTE institutions (13,088 for 2024-25; snapshot refused unless state lists add up), RBI IFSC banks + sublet IFSCs, 9 RBI-cited mergers; re-keys stored instruments; audited |
| Intake M2 | `modules/instruments/intake.py`, `modules/storage/store.py` | Fernet-encrypted docs (local or S3), versioned, SHA-256 |
| Extraction M3/N6 | `modules/extraction/` + `config/extraction.yaml` | RapidOCR; pass B = config rules; pass A plugs in only if a model trained on labelled FDRs exists (none) |
| Checks M4/N7/N8 | `modules/checks/`, `config/checks.yaml` | Flags with fact/rule/clause/reason; double pledge via issuing + canonical bank (cross-merger needs same issue date and amount), near-duplicate, amount-in-words, continuity gap |
| Forgery N6 | `modules/forgery/` | RGB-GLCM + ELA + ink + copy-move per OCR line; SVM; grey/suspicious bands; model being retrained on Find it again! |
| Bank M5/N3/N4 | `modules/bank/` | Pinned Ed25519 keys, credential verify, field compare → Trust L3/L4, freshness decay |
| Lifecycle M7/N2 | `modules/lifecycle/` + `config/workflow.yaml` | State machine, coverage curves + first-gap forecast (bulk `coverage.reports()`), daily sweep with demo clock |
| Alerts M8 | `modules/alerts/`, `config/alerts.yaml` | One notification per threshold/audience; overdue, coverage gap, risk, time boxes |
| Release M9/N5 | `modules/release/` | Policy checklist, blockers, mandatory reason, release letter PDF (marked PROTOTYPE), lien removal |
| Audit M6/N10 | `modules/audit/` + `config/conformance.yaml` | Hash chains; Merkle anchors stored first, immudb receipt (`[anchoring]` extra, `immudb-py==1.5.0`) read back on verify; `store_error` kept when immudb is down; conformance replay |
| Risk N9 | `modules/risk/` | Live scoring only from `models/renewal_risk/` (none; off by decision) |
| Reports M10 | `app/api/dashboard.py` | Tiles, `/coverage` (needs REPORT_VIEW or INSTRUMENT_READ_OWN; bank accounts get 403), 4 reports as JSON/CSV/XLSX |
| Seed | `app/seed.py`, `seed/demo_seed.json` | Dev accounts only; `--institution-user-aicte-id` links the institution user; no instruments |

### Mock bank — `services/mock-bank` (48 tests)
Simulation of an issuing bank. Ledger starts empty; the operator records each FDR it issued (page at
`http://localhost:8090`, `python -m mockbank register`, or `POST /fdrs`; insert-only, locked across
processes, atomic writes). Amount is a Decimal (paise allowed). Two tokens that must differ:
`MB_API_TOKEN` (DepositTrack: `/keys`, `/credentials`, `/status`, `/lien/remove`) and
`MB_OPERATOR_TOKEN` (operator: `/fdrs`, `/ledger`, `/simulate/close`). `MB_BANK_CODES` (empty by
default) lists bank codes whose keys are published before any FDR. Settings in `.env.example`.

### ML — `ml/`
- On `main`: `ml/synth`, `ml/forgery/{train,tamper}.py`, `ml/risk/{train,simulate}.py` and
  `ml/layoutlm/train_layoutlmv3_fdr.ipynb` are the **old synthetic-data code, being replaced**:
  - PR #9: `ml/layoutlm/train_layoutlmv3_funsd_proxy.ipynb` (FUNSD, free Colab T4), removes `ml/synth`.
  - PR #10: `ml/risk/train.py` on BPI Challenge 2017 → `models/renewal_risk_proxy/` (not loaded live).
    Measured (proxy): AUC 0.821, 80.1% of missed deadlines caught at 12.0% false alarms,
    mean/median lead 14.6/16.6 days, regressor MAE 6.16 days.
  - Forgery branch `forgery-model-on-find-it-again` (worktree `../wt-forgery`): `ml/forgery/train.py`
    on Find it again! (train/val/test split), removes `tamper.py`; training was still running.
- The old synthetic-trained models were moved out of `models/` to `../retired-synthetic-models/`.
- Datasets live in the kagglehub cache (`~/.cache/kagglehub`); the Kaggle token is in
  `~/.kaggle/access_token` (user's, never commit it).
- Not built: discrepancy-risk XGBoost from the plan; officer assistant (skipped).

### Web — `apps/web` (Next.js 16.4.3, React 19; ESLint, tsc and build pass; npm pinned 11.6.2)
- taste-skill **achromatic-ledger** style (seed 549180210): blue-grey ground `#f2f4f7`, one hue
  `#1d5fbf`; top-bar shell; coverage strip and Trust Ladder components.
- Screens: `/overview`, `/queue`, `/instruments`, `/instruments/[id]`, `/cases`, `/cases/[id]`,
  `/reports`, `/audit`, `/verify`, `/admin`, `/my`, `/my/submit`, `/my/request/[id]`, `/bank`,
  `/auth/callback`.
- **Opened in a browser on 23 Oct** (Chrome DevTools): sign-in, `/my`, `/admin`, `/overview`,
  `/reports`, `/audit` load without console errors. taste-skill `inspect.mjs --app` not yet run on
  the web app (only on the mock bank page). Admin/audit pages do not yet show `store_error`,
  `receipt` or `immudb_problem` from PR #7.
- i18n: `src/i18n/en.json`, `hi.json` (Hindi written by Claude — **needs a fluent reviewer**).
- Next 16 notes: read `node_modules/next/dist/docs/` first; Cache Components on, so
  `useParams`/`useSearchParams` must be inside `<Suspense>`; React 19 lint forbids setState in effects.

## 5. How to run locally

```bash
cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
# API: apps/api/.env (gitignored) with DT_DATABASE_URL, DT_STORAGE_ENCRYPTION_KEY (Fernet),
#      DT_S3_ACCESS_KEY/SECRET_KEY (infra/seaweedfs/s3.json), DT_POLICY_FILE=config/policy.demo.yaml,
#      DT_BANK_API_TOKEN, DT_MODELS_DIR=../../models, DT_IMMUDB_ENABLED=true, DT_IMMUDB_PASSWORD
cd apps/api && .venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.masterdata fetch-institutions && .venv/Scripts/python -m app.masterdata import-institutions
.venv/Scripts/python -m app.masterdata fetch-banks && .venv/Scripts/python -m app.masterdata import-banks
.venv/Scripts/python -m app.seed demo --institution-user-aicte-id 1-43655541828
.venv/Scripts/uvicorn app.main:app --port 8000
# Mock bank: cp services/mock-bank/.env.example services/mock-bank/.env (MB_API_TOKEN = DT_BANK_API_TOKEN,
#            MB_OPERATOR_TOKEN different)
cd services/mock-bank && .venv/Scripts/python -m mockbank serve --port 8090   # operator page on /
# Web
cd apps/web && npm run dev
```
Then: admin → pin bank keys; institution uploads an FDR scan; bank operator records the same FDR
on the mock bank page; verifying officer → "Verify with bank". A dev DB seeded by the old fictional
seed must be reset first (`alembic downgrade base && alembic upgrade head`). The live DB in the main
checkout is still at migration 0004: run `alembic upgrade head` when switching it to `main`.
Port note: a Wondershare app listens on `0.0.0.0:8090`; the mock bank binds `127.0.0.1:8090`.

## 6. Next steps (in order)

1. **User (manual):** provide an FDR scan (real, with consent, personal details redacted) so the
   upload → extraction → bank verification story can be tested; run the PR #9 notebook on free
   Colab (T4) and share `metrics.json`.
2. Review and merge #8, #10, #9; open and merge the forgery PR when training finishes; then remove
   the remaining synthetic mentions from the plan and README.
3. Security follow-up found in review of #5: `GET /instruments/{id}` has no permission check, and
   unusual role mixes (e.g. institution + bank_service) match no scoping rule.
4. Walk the demo story (plan §12) on the live stack; run taste-skill `inspect.mjs --app` on every
   screen (1440/768/390) and fix FAILs; show PR #7's anchor fields in the admin/audit UI.
5. When the user grants the `workflow` scope: add the CI workflow.
6. Open items needing AICTE answers: plan §14 (amounts, wording, release conditions, approvers,
   reminder days, integrations, state → regional office mapping).
