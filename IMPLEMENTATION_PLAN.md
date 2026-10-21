# DepositTrack — Implementation Plan (SIH 2026 · PS SIH26265)

**Problem statement:** SIH26265 · *Streamline of security deposit/ FDR portal* · AICTE, Regulation Bureau · Software · Smart Automation
**Source:** https://www.sih.gov.in/sih2026PS (read 21 Oct 2026; idea submission deadline listed as 28 Oct 2026)
**Inputs consolidated:** `research/krrish/FDR-Guardian-SIH-26265-Implementation-Plan.md`, `research/Mayank_Kathe/Mayank-Research-Notes-SIH-26265.md`, and the 15 papers in `research/`. Every paper claim below was re-checked against the paper text; corrections to the earlier notes are listed in [§4.3](#43-corrections-to-earlier-research-notes).

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [The problem, in AICTE's own words](#2-the-problem-in-aictes-own-words)
3. [Objective traceability matrix](#3-objective-traceability-matrix)
4. [Research basis](#4-research-basis)
5. [Novel solution](#5-novel-solution)
6. [System architecture](#6-system-architecture)
7. [Data model and lifecycle](#7-data-model-and-lifecycle)
8. [Module-by-module build specification](#8-module-by-module-build-specification)
9. [AI / ML components](#9-ai--ml-components)
10. [Security, privacy and compliance](#10-security-privacy-and-compliance)
11. [Testing: SIH scenarios and KPIs](#11-testing-sih-scenarios-and-kpis)
12. [Roadmap](#12-roadmap)
13. [Risks and fallbacks](#13-risks-and-fallbacks)
14. [Open questions for AICTE (not assumed)](#14-open-questions-for-aicte-not-assumed)
15. [Repository layout](#15-repository-layout)
16. [References](#16-references)

---

## 1. Executive summary

**DepositTrack** is a secure, centralized portal for the AICTE Regulation Bureau that manages every security deposit and Fixed Deposit Receipt (FDR) from submission to release.

It does four things that a plain records portal does not:

1. **It knows who vouches for every field.** Each value (amount, maturity date, lien status…) carries a provenance level, from *institution-declared* up to *bank-attested* and *live-confirmed*. This directly answers the PS line: *"distinguish between information submitted by an institution and information independently confirmed by an authorized bank or financial source."*
2. **It tracks obligations, not just documents.** An institution owes a requirement (amount × time window). DepositTrack computes, day by day, whether that requirement is actually covered by valid instruments, and shows the **coverage gap** before it happens.
3. **Every action is provable.** Hash-chained audit events, periodic Merkle anchoring and a public file verifier let an auditor prove what was submitted, when, and by whom, without trusting the database admins.
4. **It warns early, with reasons.** Configurable T-minus reminders, plus a renewal-risk model that escalates likely misses earlier, with human-readable reasons. AI only suggests; a named officer always decides.

**One-line pitch:** *Every deposit in one place, every rupee checked against the bank, every action provable, and every coverage gap flagged before it opens.*

The build has three layers:

| Layer | Contents | Demo priority |
| --- | --- | --- |
| **Core** | Repository, upload, extraction, lifecycle engine, reminders, release workflow, dashboard, reports, audit trail, RBAC | Must work end to end |
| **Trust** | Trust Ladder, bank-signed e-FDR credential, freshness and decay, duplicate/double-pledge detection, forgery signals, Merkle anchoring | Main differentiator |
| **Intelligence** | Coverage forecasting, renewal-risk model with reasons, procedural conformance replay, clause-linked explanations, officer assistant | Wow factor, built after the core gate |

---

