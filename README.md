# DepositTrack — AICTE Security Deposit / FDR Management

Secure, centralized portal to streamline AICTE security deposit and FDR management: digital document submission, bank verification and discrepancy flagging, maturity and renewal tracking with automated alerts, release/refund workflow, dashboards and audit trails.

**Smart India Hackathon 2026 · Problem Statement [SIH26265](https://www.sih.gov.in/sih2026PS)** — *Streamline of security deposit/ FDR portal* · AICTE, Regulation Bureau · Software · Smart Automation

> **Status:** planning. The full design is in **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)**. No application code has been written yet.

---

## The problem

AICTE may require technical institutions to keep security deposits or Fixed Deposit Receipts (FDRs) as part of approval and compliance. Today these are tracked through fragmented records, manual correspondence and multiple trackers. That makes it hard to see, at any moment, which deposits are valid, which are about to lapse, which have been verified by the bank, and which cases need action.

## What DepositTrack does

All ten capabilities required by the problem statement:

| # | Capability | How DepositTrack delivers it |
| --- | --- | --- |
| 1 | Centralized repository | Institution-, obligation- and instrument-wise records with full status |
| 2 | Digital document management | Encrypted, versioned uploads; dual-pass OCR + LayoutLMv3 auto-fill |
| 3 | Verification and discrepancy detection | Bank-signed credential check, rule engine, forgery signals, duplicate detection, clause-linked reasons |
| 4 | Validity and maturity tracking | Lifecycle state machine with daily sweep and coverage forecasting |
| 5 | Renewal and replacement monitoring | Linked instrument chain with a continuity check (no gaps between old and new) |
| 6 | Release and refund workflow | Policy-as-code checklist, time boxes, competent-authority approval, release letter |
| 7 | Alerts and escalation | Configurable reminders, overdue escalation, risk-based early escalation |
| 8 | Dashboard and reports | Active / expiring / matured / renewed / released / pending, plus coverage gaps and scheduled reports |
| 9 | Audit trail and access control | Hash-chained audit log, Merkle anchoring, public file verifier, RBAC + ABAC |
| 10 | Integration and data security | Adapter layer for AICTE and bank systems (authorised channels only), encryption, key pinning |

## What is novel

- **Trust Ladder:** every field records who vouches for it: *Declared → Machine-checked → Officer-verified → Bank-attested → Live-confirmed*. Trust decays automatically when a confirmation goes stale.
- **Obligation–Coverage model:** the system tracks whether each institution's *requirement* is actually covered day by day. It forecasts coverage gaps before they open and reports **verification exposure**, the rupees relied on but not yet confirmed by a bank.
- **Bank-signed e-FDR credential:** an issuer–holder–verifier model in which banks sign FDR details and revoke the credential on release. This is a proposal; the prototype simulates the bank.
- **Verifiable audit:** hash chain, Merkle anchoring, and a verifier that proves a file is unchanged.
- **Double-pledge detection with IFSC lineage:** catches the same FDR backing two institutions, even across bank mergers.
- **Explainable risk:** grey-area discrepancy scoring and renewal-risk forecasting, each with human-readable reasons and linked regulation clauses.
- **Procedural conformance replay:** checks the Bureau's own procedure against the event log.

AI is advisory only. A named officer makes every decision, and that decision is logged.

## Planned tech stack

Next.js · FastAPI · Keycloak · PostgreSQL + pgvector · MinIO · Redis/Celery · immudb · docTR/PaddleOCR + LayoutLMv3 · XGBoost/LightGBM + SHAP · Docker Compose

## Repository

| Path | Contents |
| --- | --- |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Consolidated plan: traceability matrix, novelty, architecture, data model, modules, ML, security, tests, KPIs, roadmap, open questions |
| [`research/krrish/`](research/krrish/) | 8 papers + earlier implementation plan (FDR Guardian) |
| [`research/Mayank_Kathe/`](research/Mayank_Kathe/) | 7 papers + research notes |

Planned code layout (`apps/`, `ml/`, `services/`, `infra/`, `tests/`) is described in [§15 of the plan](IMPLEMENTATION_PLAN.md#15-repository-layout).

## Open questions

AICTE's actual deposit amounts, release conditions, approval hierarchy and integration channels are not specified in the problem statement. The plan keeps them configurable and lists them in [§14](IMPLEMENTATION_PLAN.md#14-open-questions-for-aicte-not-assumed).

## License

[MIT](LICENSE)
