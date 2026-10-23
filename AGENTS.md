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

- **For now, commit and push directly to `main`.** No feature branches or pull requests are required at this stage. This rule will be revised later; when branches are introduced, name them `name/short-description` (for example `krrish/lifecycle-engine`).
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
- Fill the **Expected outcomes** *Measured* column **only with real measured values**, and say whether they come from synthetic data. Never write a target as if it were a result.
- Keep **Repository structure** and **Work to be done** in line with what exists in the repo.

### 3. No invented AICTE values

The problem statement does not specify deposit amounts, durations, beneficiary/lien wording, release conditions, approval hierarchy or reminder thresholds. These are listed as open questions in plan §14.

- Never hard-code a guessed value for any of these.
- Keep them in configuration (`apps/api/config/policy.example.yaml`) with `null` or clearly labelled placeholder values.
- Demo and test data must be labelled as placeholders or synthetic.
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
workflow, alerts, conformance). Web URLs come from `apps/web/.env.local`. Demo values
live only in `config/policy.demo.yaml`, labelled as placeholders.

### 5. Synthetic data only

- Real FDRs are confidential. Use the generator in `ml/synth/`.
- Synthetic documents use fictional bank names and are watermarked `SYNTHETIC SAMPLE - NOT A REAL INSTRUMENT`. Do not imitate real banks' branding.
- **No hardcoded data lists.** Banks, cities, institution names, wording and value ranges for synthetic data live in `ml/synth/fdrsynth/data/synthetic_lists.json` (or a file passed with `--catalog`), never in Python code.

### 6. Ask, and flag manual work

- When something is unclear or an issue comes up, ask a maintainer instead of assuming.
- When a step needs manual action (an account, an API key, installing software, starting Docker Desktop, GitHub permissions), tell the maintainer exactly what to do; do not do it on your own.

## Stack and tooling

| Area | Choice |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Python packaging | `pip` + `venv`, dependencies in each package's `pyproject.toml` |
| Python lint / format | `ruff check` and `ruff format` |
| Python tests | `pytest` |
| Frontend | Next.js 16 + React 19, TypeScript, plain CSS tokens (taste-skill "achromatic ledger" style), `npm` |
| Frontend lint / types | `npx eslint src`, `npx tsc --noEmit`, `npx next build` |
| ML | scikit-learn, scikit-image, LightGBM (`pip install -e ".[ml]"` in `apps/api`); OCR with RapidOCR |
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
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scriptsctivate
pip install -e ".[dev,ml]"
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

# Synthetic FDR generator (ml/synth)
pip install -e ".[dev]"
python -m fdrsynth --count 20 --out ../../data/synthetic
pytest

# Models (run from the repo root with the API's virtual environment; outputs go to models/, not committed)
apps/api/.venv/Scripts/python ml/forgery/train.py --data data/forgery-src --out models
apps/api/.venv/Scripts/python ml/risk/train.py --out models
# LayoutLMv3: run ml/layoutlm/train_layoutlmv3_fdr.ipynb on a GPU, unzip into models/layoutlmv3-fdr/
```

Run lint and tests before every push. CI is not set up yet, so these local checks are the only gate.

## Repository layout

```
apps/api/        FastAPI backend (modules per plan §8), config/ holds every rule file
apps/web/        Next.js frontend (taste-skill achromatic-ledger style, English + Hindi)
services/mock-bank/  Mock bank: signed FDR credentials and lien status (simulation only)
ml/synth/        Synthetic FDR generator
ml/forgery/      Forgery signal training (tampering generator + classifier)
ml/risk/         Renewal-risk training (event-log simulator + LightGBM)
ml/layoutlm/     LayoutLMv3 fine-tuning notebook (GPU)
models/          Trained model files (generated, not committed)
infra/           Docker Compose and service config (Keycloak realm, etc.)
research/        Papers and research notes
```

## Domain rules agents must respect

- **Lifecycle:** only the transitions in plan §7.1 are legal. Add new states or transitions only by updating the plan and the transition table together, with tests.
- **Audit:** every state change and field edit must produce an audit event. Never write code that updates instrument state without one.
- **AI is advisory:** models may flag, score or draft. They never approve, release or change an instrument's state.
- **Trust Ladder:** keep institution-declared, extracted and bank-confirmed values in separate fields. Never overwrite a declared value with a bank value or the other way round.
