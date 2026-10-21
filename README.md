<h1 align="center">DepositTrack</h1>

<p align="center">
  <b>Secure, centralized Security Deposit / FDR management portal for the AICTE Regulation Bureau</b><br/>
  Smart India Hackathon 2026 · Problem Statement <a href="https://www.sih.gov.in/sih2026PS">SIH26265</a>
</p>

<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-planning-orange">
  <img alt="SIH" src="https://img.shields.io/badge/SIH%202026-SIH26265-blue">
  <img alt="Theme" src="https://img.shields.io/badge/theme-Smart%20Automation-6f42c1">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

> **Current status:** research and design are complete; no application code has been written yet. The full design is in **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)**. All numbers in this README are **targets**, not measured results.

---

## Table of contents

1. [Problem statement](#problem-statement)
2. [Objectives](#objectives)
3. [Solution overview](#solution-overview)
4. [Architecture](#architecture)
5. [Instrument lifecycle](#instrument-lifecycle)
6. [Key concepts](#key-concepts)
7. [Modules](#modules)
8. [Tech stack](#tech-stack)
9. [Expected outcomes](#expected-outcomes)
10. [Test scenarios](#test-scenarios)
11. [Progress](#progress)
12. [Work to be done](#work-to-be-done)
13. [Repository structure](#repository-structure)
14. [Research basis](#research-basis)
15. [Open questions](#open-questions)
16. [License](#license)

---

## Problem statement

| Field | Value |
| --- | --- |
| PS ID | SIH26265 |
| Title | Streamline of security deposit/ FDR portal |
| Organization | AICTE (All India Council for Technical Education) |
| Department | Regulation Bureau |
| Category | Software |
| Theme | Smart Automation |

**Background.** AICTE may require technical institutions to submit or maintain security deposits or Fixed Deposit Receipts (FDRs) as part of approval and compliance. Managing them means:

- keeping institution-wise records;
- verifying the instruments;
- monitoring validity and maturity;
- tracking renewal or replacement;
- recording release or refund requests;
- keeping documents available for regulatory verification.

**Current pain.** Fragmented records, manual correspondence and multiple trackers make it hard to keep an accurate, current view of deposit status, pending actions and time-sensitive requirements.

**What the PS asks for:**

- A secure, centralized portal that tracks every deposit across its lifecycle.
- The portal must distinguish what an institution *submitted* from what a bank or financial source has *independently confirmed*.
- The prototype must show measurable improvement in:
  - record accuracy;
  - verification turnaround time;
  - timely renewal monitoring;
  - manual tracking effort;
  - visibility into pending cases.

---

## Objectives

The ten capabilities required by the PS, and how DepositTrack covers each:

| # | PS capability | DepositTrack implementation | Modules |
| --- | --- | --- | --- |
| 1 | Centralized Security Deposit/FDR Repository | Institution-, obligation- and instrument-wise records with documents and status | M1, M2, M10 |
| 2 | Digital Document Management | Encrypted, versioned uploads; bundle splitting; dual-pass OCR + LayoutLMv3 auto-fill | M2, M3 |
| 3 | Verification and Discrepancy Detection | Bank-signed credential check, completeness and policy rules, forgery signals, duplicate detection, clause-linked reasons | M4, M5 |
| 4 | Automated Validity and Maturity Tracking | Lifecycle state machine, daily sweep, coverage-gap forecasting | M7, M8 |
| 5 | Renewal and Replacement Monitoring | Linked instrument chain with a continuity check between old and new | M7 |
| 6 | Release and Refund Workflow | Policy-as-code checklist, time boxes, competent-authority approval, release letter | M9 |
| 7 | Automated Alerts and Escalation | Configurable reminders, overdue escalation, risk-based early escalation | M8 |
| 8 | Dashboard and Management Reports | Status tiles, coverage gaps, verification exposure, scheduled PDF/Excel reports | M10 |
| 9 | Audit Trail and Access Control | Hash-chained audit log, Merkle anchoring, public file verifier, RBAC + ABAC | M1, M6 |
| 10 | System Integration and Data Security | Adapters for AICTE and bank systems (authorised channels only), encryption, key pinning | M5, M12 |

The PS's detailed description also asks for the following, all of which are covered in the plan:

- discharge requests;
- updating permitted fields;
- recording scrutiny observations;
- reviewing document histories;
- missing-document reports;
- flagging incomplete records.

See the [traceability matrix](IMPLEMENTATION_PLAN.md#3-objective-traceability-matrix).

---

## Solution overview

DepositTrack has three layers. The core must work end to end before the other two are built.

| Layer | What it contains | Priority |
| --- | --- | --- |
| **Core** | Repository, upload, extraction, lifecycle engine, reminders, release workflow, dashboard, reports, audit trail, access control | Must work end to end |
| **Trust** | Trust Ladder, bank-signed e-FDR credential, freshness decay, double-pledge detection, forgery signals, Merkle anchoring | Main differentiator |
| **Intelligence** | Coverage forecasting, renewal-risk model with reasons, procedural conformance replay, clause-linked explanations, officer assistant | Built after the core gate |

**Guiding rule:** AI is advisory only. A named officer makes every decision, and every decision is logged with a reason.

---

