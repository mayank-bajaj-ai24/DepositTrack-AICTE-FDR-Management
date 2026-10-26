# AGENTS.md

Instructions for AI coding agents (Claude, Gemini and others) and human contributors working on **DepositTrack**, the AICTE Security Deposit / FDR management portal for SIH 2026 problem statement SIH26265.

Read this file fully before making changes. These rules apply to everyone.

## Project context

- **What we are building:** a secure, centralized portal for the AICTE Regulation Bureau that manages security deposits and Fixed Deposit Receipts (FDRs) from submission to release.
- **Source of truth for design:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Module IDs (M1–M13), novelty IDs (N1–N10) and test IDs (T-01–T-14) used in code, commits and docs refer to that plan.
- **Project overview and progress:** [README.md](README.md).
- **Research:** papers and notes are in `research/`. Plan §4.3 lists claims from earlier notes that the papers do not support; do not reuse those.

## Rules

### 1. Git workflow

- **One branch per piece of work, then a pull request to `main`.** Name the branch after the work it implements, in lowercase words joined by hyphens (for example `aicte-institution-and-ifsc-master-data-import`, `mock-bank-operator-page`). Branch from an up-to-date `main`; when work depends on an open PR, stack it on that PR's branch and say so in the description.
- **Every PR has a description:** what changed and why, how it was tested (commands and counts), what is still open, and any manual step for the maintainer.
- **The maintainer approves every merge.** Do not merge your own PR without explicit approval. Before merging, bring the branch up to date with `main`, resolve conflicts and re-run the checks.
- **Make many small commits.** One logical change per commit (one module, one config file, one test file, one doc section). Do not bundle unrelated changes into a single commit.
- **Pull before you start** (`git pull --ff-only`) and before you push, so you never overwrite a teammate's work. Never force-push to `main`.
- **Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):** `type(scope): summary`.
  - Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `build`, `perf`, `style`.
  - Scope is the module or area, e.g. `feat(lifecycle): add state transition table`, `docs(readme): update progress`, `ci: add backend test job`.
- **No AI attribution** in commits or pull requests: no `Co-Authored-By` lines naming an AI tool, and no "Generated with …" footers.
- Never commit secrets, real credentials, real FDR scans or personal data. Development-only defaults must be clearly marked as such.

### 2. Keep the README up to date

Update [README.md](README.md) in the same push as the change that makes progress:

- Tick items in the **Progress** checklist when they are actually done.
- Update the **Test scenarios** status column when a test is implemented or passing.
- Fill the **Expected outcomes** *Measured* column **only with real measured values**, and name the dataset they come from: a result on an open dataset is labelled **proxy**, a result on generated FDRs is labelled **synthetic** (rule 5), and neither is presented as an FDR result. Never write a target as if it were a result.
- Keep **Repository structure** and **Work to be done** in line with what exists in the repo.

### 3. No invented AICTE values

The problem statement does not specify deposit amounts, durations, beneficiary/lien wording, release conditions, approval hierarchy or reminder thresholds. These are listed as open questions in plan §14.

- Never hard-code a guessed value for any of these.
- Keep them in configuration (`apps/api/config/policy.example.yaml`) with `null` or clearly labelled placeholder values.
- Demo values must be labelled as placeholders (`DEMO PLACEHOLDER - not an AICTE rule`).
- When a real value is confirmed by AICTE, record its source in the config comment.

### 4. UI work

- All frontend / UI work uses the **taste-skill** plugin. Install it in Claude Code with:
  ```
  /plugin marketplace add Leonxlnx/taste-skill
  /plugin install taste-skill@taste-skill
  ```
- Contributors using other tools should follow the design guidance from that plugin's repository (https://github.com/Leonxlnx/taste-skill).
- [21st.dev](https://21st.dev/) may be used only within its free plan. Its free tier allows 2 component copies per day, and unlimited Magic MCP access needs a paid plan, so taste-skill is the primary tool. Never sign up for or use a paid plan on the project's behalf.

### 4a. Next.js 16

`apps/web` uses Next.js 16, which changed APIs. Before writing frontend code, read the
relevant guide in `apps/web/node_modules/next/dist/docs/` (see `apps/web/AGENTS.md`).
Cache Components are on: client hooks that read the URL (`useParams`, `useSearchParams`)
must sit inside `<Suspense>`.

### 4b. Configuration, not code

Rules and thresholds live in `apps/api/config/*.yaml` (policy, extraction, checks,
workflow, alerts, conformance, master_data, bank_mergers). Web URLs come from `apps/web/.env.local`. Demo values
live only in `config/policy.demo.yaml`, labelled as placeholders.

### 5. Real and open data, plus a labelled synthetic FDR dataset

Decided on 25 Oct 2026; it replaces the 23 Oct "no synthetic data" rule. No public FDR dataset exists and real FDRs are confidential, so the FDR documents themselves may be synthetic. Everything else stays real or open.

- **Synthetic data is allowed only for FDR documents:** generated FDR images (PNG or JPEG; the app cannot read a PDF until a PDF renderer is added) and their field labels, used to build, train and evaluate the FDR models (extraction pass A, forgery signal, discrepancy checks) and to walk the demo story. The generator will live in `ml/synthetic_fdr/` (PR #14); the generated files go to the git-ignored `data/synthetic_fdr/` and are never committed. The generator writes clean pages only: tampered copies for forgery training are made by `ml/forgery/train.py` with `tamper.py`, so that every "tampered" label comes from the edit that made it.
- **Synthetic FDRs are always labelled.** Every generated page carries the visible mark `SYNTHETIC - NOT A REAL DEPOSIT`, exactly this text; it replaces the old generator's `SYNTHETIC SAMPLE - NOT A REAL INSTRUMENT`. Extraction and the forgery signal must not read the mark as data, so it is registered in `apps/api/config/extraction.yaml`: the full line under `ignore_lines_containing` and the fragments OCR reads on their own (such as `SYNTHETIC`) under `ignore_lines_equal`. Never add a bare `DEPOSIT` to `ignore_lines_containing`, because it would drop captions like "Deposit Amount". Results measured on generated FDRs are **synthetic results**, labelled "synthetic" in README Expected outcomes and kept apart from proxy results; they are never presented as results on real FDRs.
- **A synthetic FDR uses real public master data and invents nothing else that could be mistaken for a real record.** Banks, branches, IFSCs and institutions come from the imported public master data. FDR numbers, amounts and dates are generated from the ranges in the generator's config (placeholders, not AICTE rules). Layouts imitate the common structure of an FDR and never copy a real bank's logo or branding.
- **Synthetic FDRs stay in a demo database.** A generated FDR names a real institution, bank and IFSC, and the records made from it (instrument, flags, bank attestation, audit events, report rows) carry no synthetic marker. Walk them only on a development or demo database that is reset afterwards (`alembic downgrade base && alembic upgrade head`), never on one that holds real deposits, and never pass its reports or exports off as real.
- **No hardcoded fake values** in application code, config, seeds or the UI. Synthetic FDRs come from the generator, not from values written into the app's code, config or seeds. Typing a generated FDR's values into the submit form or the mock bank's operator page during a demo walk is fine.
- **Master data comes from public sources:** AICTE's approved-institutions dashboard and the RBI IFSC master (Razorpay IFSC dataset), imported with `python -m app.masterdata` (sources in `apps/api/config/master_data.yaml`). Bank mergers are listed in `apps/api/config/bank_mergers.yaml`, each with its RBI press release.
- **Models are trained on synthetic FDRs or on open datasets as proxies.** Results on the closest open dataset are reported as *proxy results on that dataset*; results on synthetic FDRs as *synthetic results*. Neither is an FDR result. Results on real FDRs need labelled real FDRs. Datasets (with pinned versions), licences and citations are listed in `ml/open_datasets.json` and downloaded with `ml/download_open_data.py` into the git-ignored `data/<name>/`; a dataset whose licence is not confirmed needs `--accept-unconfirmed-licence`. Check a dataset's licence before using it and never commit downloaded data (`data/` is not in git).
- **No model runs live without the maintainer's approval, and a live model is labelled with its training data** in the UI (for example "trained on synthetic FDRs"). A proxy that cannot speak for AICTE institutions (renewal risk on BPI 2017, LayoutLMv3 on FUNSD) stays off. The approval is recorded on the model's files, and the loaders refuse a model without it:
  - renewal risk: `"live_scoring": true` in `models/renewal_risk/meta.json`;
  - extraction pass A: `pass_a_enabled: true` in `extraction.yaml`, plus `"live_extraction": true` and a `"training_data"` name in `models/layoutlmv3-fdr/metrics.json`; FDR labels alone are not enough, because a model trained on synthetic FDRs has them too;
  - forgery signal: the same gate (`"live_scoring": true` and `"training_data"` in `models/forgery/meta.json`) arrives with PR #16. Until it is merged, the forgery loader uses any model in `models/forgery/`, so write forgery training output outside `models/`.

  Ask the maintainer before switching any model on.
- **Real FDRs are confidential.** A real FDR is used only with the owner's consent and personal details redacted, and is never committed.
- **The mock bank is a simulation**, clearly labelled as one. Its ledger starts empty; the bank operator records each FDR. Real bank names and IFSC codes may appear there, but never a bank's branding.
- **Test fixtures** use excerpts of the real public data (for example `apps/api/tests/fixtures/masterdata`), minimal values that a test needs to exercise a rule, or small synthetic FDRs from the generator. They are never presented as real records.

### 6. Ask, and flag manual work

- When something is unclear or an issue comes up, ask a maintainer instead of assuming. Any change to the plan is agreed with the maintainer before it is built.
- When a step needs manual action (an account, an API key, installing software, starting Docker Desktop, GitHub permissions, running a notebook on Colab), tell the maintainer exactly what to do; do not do it on your own.

### 7. No cost

- Never take a step that costs money: no paid plans, paid APIs, paid GPUs (Colab Pro or compute units) or paid hosting. Free tiers only (for example the free Colab T4 GPU, a free Kaggle account).
- If a task seems to need something paid, stop and ask the maintainer, and offer a free alternative.

## Stack and tooling

| Area | Choice |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Python packaging | `pip` + `venv`, dependencies in each package's `pyproject.toml` |
| Python lint / format | `ruff check` and `ruff format` |
| Python tests | `pytest` |
| Frontend | Next.js 16 + React 19, TypeScript, plain CSS tokens (taste-skill "achromatic ledger" style), `npm` |
| Frontend lint / types | `npx eslint src`, `npx tsc --noEmit`, `npx next build` |
| ML | scikit-learn, scikit-image, LightGBM (`ml` extra in `apps/api`); open datasets via `kagglehub` (`data` extra); OCR with RapidOCR |
| Audit anchoring | immudb receipts via `immudb-py==1.5.0` (`anchoring` extra in `apps/api`; pinned because of its large dependency tree) |
| Mock bank | `services/mock-bank` (FastAPI), simulation of a bank's signed confirmation channel |
| Infrastructure | Docker Compose: PostgreSQL 16 + pgvector, SeaweedFS (S3), Redis, Keycloak, immudb |
| CI | GitHub Actions — pending: adding `.github/workflows/` needs a token with the `workflow` scope |

MinIO from the original plan was replaced by SeaweedFS because MinIO no longer publishes Docker images. The app uses the plain S3 API, so the store can be swapped.

## Common commands

```bash
# Infrastructure (Docker Desktop must be running)
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d

# Backend (apps/api)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,ml,anchoring]"                # anchoring = immudb client
ruff check . && ruff format --check .
pytest
alembic upgrade head
uvicorn app.main:app --reload                        # http://localhost:8000/docs
python -m app.masterdata fetch-institutions && python -m app.masterdata import-institutions  # AICTE public list
python -m app.masterdata fetch-banks && python -m app.masterdata import-banks                # RBI IFSC master + mergers
python -m app.seed demo --institution-user-aicte-id <AICTE ID>   # dev accounts (no instruments)

# Mock bank (services/mock-bank)
pip install -e ".[dev]"
cp .env.example .env                                 # development-only placeholders
python -m mockbank register --ifsc <IFSC> --fdr-no <no> --amount <INR> --issue-date <YYYY-MM-DD> --maturity-date <YYYY-MM-DD> --beneficiary "<text>" --depositor "<name>"   # the bank records an FDR it issued
python -m mockbank serve --port 8090                 # operator page at http://localhost:8090 (needs MB_OPERATOR_TOKEN in .env)

# Web (apps/web)
cp .env.example .env.local
npm install
npm run dev                                          # http://localhost:3000
npx eslint src && npx tsc --noEmit && npx next build

# Models on open data (repo root, API's virtual environment; outputs go to models/, not committed)
pip install -e "apps/api[data,ml]"                                     # kagglehub + model libraries
apps/api/.venv/Scripts/python ml/download_open_data.py bpi-2017        # Kaggle token needed (free)
apps/api/.venv/Scripts/python ml/risk/train.py --out models            # proxy, writes renewal_risk_proxy/, live off
apps/api/.venv/Scripts/python -m pytest ml/tests
# LayoutLMv3: run ml/layoutlm/train_layoutlmv3_funsd_proxy.ipynb on the free Colab T4 GPU (proxy, live off)
# Forgery (Find it again!): the retrain is uncommitted in the maintainer's local worktree, not on any branch (result near chance)
```

Run lint and tests before every push. CI is not set up yet, so these local checks are the only gate.

## Repository layout

```
apps/api/        FastAPI backend (modules per plan §8), config/ holds every rule file
apps/web/        Next.js frontend (taste-skill achromatic-ledger style, English + Hindi)
services/mock-bank/  Mock bank (simulation): the operator records issued FDRs; signed credentials, lien status
ml/open_datasets.json, ml/download_open_data.py  Open-dataset catalog and download helper
ml/forgery/      Forgery signal training (Find it again! retrain not committed yet)
ml/risk/         Renewal-risk proxy training (BPI Challenge 2017)
ml/layoutlm/     LayoutLMv3 FUNSD proxy notebook
ml/tests/        Tests for the ml scripts
data/open/       Downloaded public master data (not committed)
models/          Trained model files (generated, not committed)
infra/           Docker Compose and service config (Keycloak realm, etc.)
research/        Papers and research notes
```

## Domain rules agents must respect

- **Lifecycle:** only the transitions in plan §7.1 are legal. Add new states or transitions only by updating the plan and the transition table together, with tests.
- **Audit:** every state change and field edit must produce an audit event. Never write code that updates instrument state without one.
- **AI is advisory:** models may flag, score or draft. They never approve, release or change an instrument's state.
- **Trust Ladder:** keep institution-declared, extracted and bank-confirmed values in separate fields. Never overwrite a declared value with a bank value or the other way round.
