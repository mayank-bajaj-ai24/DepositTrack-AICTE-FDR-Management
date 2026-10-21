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

## 2. The problem, in AICTE's own words

### 2.1 Background (summarised from the PS)

AICTE may require technical institutions to submit or maintain security deposits / FDRs as part of approval and compliance. The work involves:

- keeping institution-wise records;
- verifying the submitted instruments;
- monitoring validity and maturity;
- tracking renewal or replacement;
- recording release and refund requests;
- keeping documents available for regulatory verification.

Today this runs on fragmented records, manual correspondence and multiple trackers. As a result, nobody has an accurate, current view of deposit status, pending actions and deadlines.

### 2.2 Every requirement stated in the PS

The ten numbered capabilities are listed in §3. The *Detailed Description* also asks for the following, which are easy to miss and are tracked as explicit requirements here:

| ID | Requirement (PS wording, condensed) |
| --- | --- |
| R-a | Records include reference numbers, issuing bank details, amount, issue date, maturity date, validity status, supporting documents, current administrative status |
| R-b | Verify through *legitimate bank-issued verification mechanisms wherever supported* |
| R-c | Identify **incomplete records** and flag discrepancies |
| R-d | **Distinguish institution-submitted vs bank/financial-source-confirmed** information |
| R-e | Track maturity, validity, renewal/replacement and *other prescribed timelines* |
| R-f | **Configurable** reminders; overdue/unresolved cases flagged for follow-up |
| R-g | Release, **discharge** or refund, subject to regulations, prescribed conditions and **competent-authority authorization** |
| R-h | Dashboard: active, expiring, matured, renewed, released, pending |
| R-i | Users can **search records, review document histories, update permitted fields, record scrutiny observations, monitor case status** |
| R-j | Automated reports: pending verifications, upcoming maturities, **missing documents**, cases requiring intervention |
| R-k | Role-based access, secure storage, encryption, audit trails, controlled access |
| R-l | Integration with AICTE systems and bank verification *where technically feasible and formally authorized*, to reduce duplicate entry |

### 2.3 Evaluation criteria in the PS

- **Measurable improvements** in five areas:
  - record accuracy;
  - verification turnaround time;
  - timely renewal monitoring;
  - reduction in manual tracking effort;
  - visibility into pending cases.
- **Test scenarios:** new FDR submission, validity tracking, approaching maturity, renewal, discrepancy identification, authorized release processing.

§11 maps every one of these to an automated test and a measured KPI.

### 2.4 Actors

| Actor | Role in DepositTrack |
| --- | --- |
| Institution user | Submits instruments, confirms extracted fields, responds to queries, requests renewal/release, sees own status |
| Scrutiny officer (Regulation Bureau) | Reviews submissions, records scrutiny observations, raises/clears discrepancies |
| Verifying officer / Finance | Triggers and records bank verification |
| Competent authority | Approves release/discharge/refund; any override needs a recorded reason |
| Bank (integration actor) | Issues signed confirmation; confirms lien marking and lien removal |
| Auditor | Read-only access to full history and integrity proofs |
| System admin | Users, roles, rule configuration, reminder schedules, master data |

The exact officer hierarchy and delegation levels are **not** stated in the PS (see §14).

---

## 3. Objective traceability matrix

This matrix is the contract for the build. Every PS capability maps to modules, a novel element where one applies, a research basis and an acceptance test.

| # | PS capability | Modules (§8) | Novel element (§5) | Research basis (§4) | Acceptance test (§11) |
| --- | --- | --- | --- | --- | --- |
| 1 | Centralized repository | M1, M2, M10 | N2 Obligation–Coverage model | — | T-01, T-02 |
| 2 | Digital document management | M2, M3 | N6 Dual-pass extraction | P3 LayoutLMv3, P13 IDP Accelerator, P12 Multi-agent review | T-01 |
| 3 | Verification and discrepancy detection | M4, M5 | N1 Trust Ladder, N3 e-FDR credential, N7 Double-pledge, N8 Clause-linked flags | P7 SSI survey, P4 RGB forgery, P6 SHAP/Anchor, P14 Regulatory graphs | T-05, T-06, T-07 |
| 4 | Validity and maturity tracking | M7, M8 | N2 Coverage gap forecast | P10 Smart-contract FD | T-03, T-04 |
| 5 | Renewal and replacement monitoring | M7 | N2 continuity check, instrument chain | P2 Revocation (chained status records) | T-08 |
| 6 | Release and refund workflow | M9 | N5 Policy-as-code with time boxes | P1 SMTSEC, P15 Audit-trail compliance rules | T-09 |
| 7 | Alerts and escalation | M8 | N9 Renewal-risk with reasons | P5 Predictive monitoring benchmark, P6 SHAP/Anchor | T-04, T-10 |
| 8 | Dashboard and reports | M10 | N2 Coverage strip, verification exposure | P11 Compliance monitoring review (result types) | T-11 |
| 9 | Audit trail and access control | M1, M6 | N4 Verifiable audit + freshness, N10 Conformance replay | P2 Revocation, P15 Audit trail, P11 Compliance review | T-12, T-13 |
| 10 | Integration and data security | M5, M12, §10 | N3 e-FDR credential, IFSC lineage | P7 SSI survey, P9 Blockchain finance survey | T-12, T-14 |

**Additional requirements → modules:**

| ID | Modules |
| --- | --- |
| R-a | M2 schema |
| R-b | M5 |
| R-c | M4 completeness rules |
| R-d | N1 |
| R-e | M7 configurable timelines |
| R-f | M8 |
| R-g | M9 with discharge as a case type |
| R-h | M10 |
| R-i | M10 search, M2 versions, M1 field-level edit permissions, M4 observations |
| R-j | M10 reports |
| R-k | M1, M6, §10 |
| R-l | M12 |

---

## 4. Research basis

### 4.1 Paper map (verified against the PDFs)

**Key:** P1–P8 are in `research/krrish/`; P9–P15 are in `research/Mayank_Kathe/`.

| ID | Paper | What it actually contributes | Used in |
| --- | --- | --- | --- |
| P1 | Ahmadisheykhsarmast & Sonmez, *A smart contract system for security of payment of construction contracts*, Autom. Constr. 120 (2020) | SMTSEC contract with explicit parameters (contingency %, PeriBloc blocking period — 30 days in their example, PeriPay payment period); funds transfer automatically once a payment is approved; interviews (Table 4) flag lack of legal infrastructure as a disadvantage | M9 time-boxed, parameterised release (N5); final approval always human |
| P2 | Elloh Adja, Hammi, Serhrouchni, Zeadally, *A blockchain-based certificate revocation management and status verification system*, Comput. Secur. 104 (2021) | Revoked certificates held in Bloom filters per distribution point; status records carry *last update* / *next update* freshness fields (Fig. 4); Merkle root over record fields, signed (Fig. 5) | N4 freshness + decay, M5 revocation of released FDRs, M6 anchoring |
| P3 | Huang et al., *LayoutLMv3*, ACM MM 2022 | Unified text + layout + image Transformer; base = 133M params; 92.08 F1 on FUNSD (fine-tuned at lr 1e-5, batch 16); ablation: a 125M text+layout-only model gets 88.64 F1 | M3 key-field extraction |
| P4 | Gornale, Patil, Benne, *Document Image Forgery Detection Using RGB Color Channel*, TMLAI 10(5) 2022 | 9 GLCM features (contrast, homogeneity, energy × R, G, B); block-wise comparison; 93.11% on printed, 95.8% on handwritten; 950 images, resized to 100×100, threshold 40; 10 forgery types | M4 forgery signal (one of several, never a verdict) |
| P5 | Rama-Maneiro, Vidal, Lama, *Deep Learning for Predictive Business Process Monitoring: Review and Benchmark*, IEEE TSC 2023 | 10 approaches on 12 event logs; Navarin et al.'s direct remaining-time approach ranked best for remaining time; Tax et al. LSTM top for next activity; reusable preprocessing / split protocol | N9 event-log design and evaluation protocol |
| P6 | Thanathamathee et al., *SHAP-Instance Weighted and Anchor Explainable AI: Enhancing XGBoost for Financial Fraud Detection*, Emerging Sci. J. 8(6) 2024 | XGBoost with SHAP-based instance weights; Anchor if-then explanations; three classes (non-fraudulent / grey area / fraudulent) derived from score bands; compares SMOTE and K-CGAN oversampling | M4 risk score with grey band; N9 reasons |
| P7 | Ahmed, Islam, Shatabda, Islam, *Blockchain-Based Identity Management System and Self-Sovereign Identity Ecosystem: A Comprehensive Survey*, IEEE Access 2022 | Issuer–holder–verifier model, verifiable credentials, DIDs, revocation; five IDMS properties: authentication, integrity, privacy, trust, simplicity | N3 e-FDR credential; §10 security framing |
| P8 | Es, James, Espinosa-Anke, Schockaert, *RAGAS*, EACL 2024 demo | Reference-free faithfulness, answer relevance and context relevance; agreement with humans 0.95 / 0.78 / 0.70 | M11 assistant evaluation |
| P9 | Wu, Yao, Liu et al., *Blockchain for Finance: A Survey*, arXiv:2402.17219 (2024) | 12 platforms (6 finance-related detailed); 4 application categories; Table 2: permissioned/alliance chains with PoA/BFT reach millisecond-order processing vs minutes for public chains; DeFi attack factors (code bugs, third-party protocol abuse, flash loans, frontend hijacking) | M6 choice of permissioned anchoring; §10 key and code-audit controls |
| P10 | Rawat & Rahman, *Smart Contract Based Approach for Fixed Deposit in Blockchain Networks with Remix IDE*, IJCRT 11(5) 2023 | Ethereum contract with User / Bank / Financial-service-provider roles; automatic payout at maturity; early break allowed after an authentication step, with interest forfeited and a charge deducted. Mostly qualitative, with no quantitative results | M7 lifecycle framing; M9 authenticated early-release path |
| P11 | Klessascheck & Pufahl, *Reviewing Uses of Regulatory Compliance Monitoring*, arXiv:2501.10362 (v5, 2025) | SLR of 41 conformance-checking + 17 compliance-checking studies; preparation → action → reflection phases; result types: qualify, quantify, break down/compare, explain, localize; *all studies rely on manual creation of the prescriptive model*; real-time alerting found in only one study | N10 conformance replay; M10 result types; policy-as-code validated by experts |
| P12 | Wan, Deng, Zou, Xu, *Enhancing the Efficiency and Accuracy of Underlying Asset Reviews in Structured Finance: The Application of Multi-agent Framework*, arXiv:2405.04294 (2024) | LLM reader → extraction → evaluation agents cross-check loan applications vs bank statements (synthetic, 49 + 49 docs); GPT-4 accuracy 0.99; dual-agent cross-verification reached 100% on their set; multi-line addresses are a weak spot (0.67 for open models); cost per document reported | N6 dual-pass extraction; cost-per-document KPI |
| P13 | Islam, Salekin, King et al. (AWS), *IDP Accelerator: Agentic Document Intelligence from Extraction to Compliance Validation*, arXiv:2602.23481 (2026) | Packet splitting (DocSplit), configurable multimodal extraction, rule validation that first gathers facts then returns determination + evidence + recommendation; human review below a configurable confidence threshold (default 0.8); OCR + image input beat image-only | M3 pipeline and HITL; M4 fact-then-rule validation |
| P14 | Khanvilkar & Kommuru, *Regulatory Graphs and GenAI for Real-Time Transaction Monitoring and Compliance Explanation in Banking*, arXiv:2506.01093 (2025) | GCN over a *transaction* graph with temporal decay; flagged items get top-k regulatory clauses retrieved from a FAISS index and a GPT-4 explanation; F1 98.2% on Elliptic; notes generated justifications are sometimes inconsistent | N8 clause-linked flag explanations; temporal decay in N9 features |
| P15 | Keating, *Blockchain-Enabled Audit Trails for Compliance and Security in Cloud-Based Payment Systems* (preprint, 2024) | Conceptual: hash-chained logs on a permissioned ledger (PBFT/PoA), compliance rules as smart contracts, *initiate → verify → log → notify → audit* flow, least-privilege access. No experimental results | M6 hash chain; M9 verify-log-notify flow |

### 4.2 What no paper covers (our contribution)

| Gap | Why it matters for AICTE | DepositTrack answer |
| --- | --- | --- |
| Obligation coverage over time | A deposit is a *requirement over a time window*, not a single document; renewals must be continuous | N2 Obligation–Coverage model |
| Provenance per field, with freshness | The PS explicitly demands institution-vs-bank distinction | N1 Trust Ladder + N4 freshness decay |
| Bank-signed FDR confirmation | Today's slowest step is letter/email verification | N3 e-FDR credential (proposal; simulated in prototype) |
| Same FDR used twice, and bank mergers renaming IFSCs | Real fraud and data-quality risks specific to Indian FDRs | N7 canonical instrument key with IFSC lineage |
| Regulator's multi-step release with prescribed conditions | Not modelled in any paper | N5 policy-as-code release |
| Process-conformance audit of the regulator's own procedure | P11 shows prescriptive models are manual and rarely validated | N10 conformance replay with expert-validated constraints |

### 4.3 Corrections to earlier research notes

These were found during verification and are **not** carried into this plan. The paper PDFs remain the source of truth.

**Mayank's notes, P9–P15:**

- **P14 (Regulatory Graphs):** the GNN runs over a *transaction* graph. Regulations are stored as a flat FAISS clause index, not a regulatory knowledge graph, and the paper has no dashboard design.
- **P12 (Multi-agent):**
  - The agents are reader / extraction / evaluation (plus data generation), not "extraction / cross-validation / anomaly / report".
  - There is no "60–80% review-time reduction" figure; the paper reports no time measurements.
- **P13 (IDP Accelerator):**
  - The default confidence threshold is **0.8**, not 0.85.
  - Retries come from the orchestration layer; only the analytics module is described as agentic.
- **P15 (Audit trail):**
  - The paper is from 2024 and the author is Layla Keating.
  - It has no Merkle anchoring, no read-only auditor node and no measured benchmarks.
- **P9 (Blockchain finance):**
  - Table 3 compares IPO/ICO/STO; the consensus comparison is the qualitative Table 2.
  - The paper has no CPMI-IOSCO mapping.
  - Oracle manipulation and front-running are not among its attack factors.
- **P11 (Compliance review):**
  - It uses three phases, not four stages.
  - It does not claim "alert generation is under-researched" (it notes real-time alerting in only one study).
  - It covers conformance checking, not prediction.
- **P10 (Smart-contract FD):**
  - The paper defines no state machine, no KYC/dispute gates and no renewal logic.
  - It has no code-level details such as `block.timestamp`.

**Krrish's plan, P1–P8:**

- **P1:** "auto-release if no action" overstates SMTSEC. Payment is automatic after approval, and PeriPay governs requests.
- **P3:** the 88.64 F1 ablation is a 125M text+layout model, not the 133M base.
- **P5:** say "Navarin's direct approach ranked best", not a general "direct beats recursive" finding.
- **P6:** the "precision 0.96" Anchor rule was illustrative, not from the paper.

---

## 5. Novel solution

Ten novel elements, grouped by layer. Headline novelties N1–N3 lead the pitch; each one can be demoed in under 60 seconds.

### N1. Trust Ladder — per-field provenance (headline)

Every field of every instrument stores up to three values (declared, extracted, bank) plus a provenance level:

| Level | Name | Reached when |
| --- | --- | --- |
| L0 | Declared | Typed or uploaded by the institution |
| L1 | Machine-checked | Extraction agrees with the declared value; rules pass; forgery signals low |
| L2 | Officer-verified | A named officer confirmed it during scrutiny (logged with reason) |
| L3 | Bank-attested | A bank-signed credential (N3) or authorised bank channel matches the field |
| L4 | Live-confirmed | The bank/authorised source confirms *current* status (not closed, lien intact) within its freshness window |

- **Instrument trust** = the minimum trust over its key fields (amount, instrument number, IFSC, maturity date, lien status). The weakest field decides.
- **UI:** a coloured badge on every field and every instrument. The dashboard can filter by trust level.
- **Covers:** R-d directly, and capability #3.

### N2. Obligation–Coverage model with gap forecasting (headline)

The core modelling idea. Existing tools track *documents*; AICTE actually cares whether an *obligation* is covered.

- **Obligation:** what an institution owes. `institution, basis (approval case / rule reference), required_amount, required_from, required_until, conditions (e.g. beneficiary wording, lien)`. Obligations are generated from configurable rules; the actual amounts and durations come from AICTE (see §14).
- **Coverage:** an allocation of an instrument (or part of one) to an obligation, valid from its issue date to its maturity/validity date.
- **Coverage function:** for each obligation and day *t*, sum the amounts allocated from instruments valid on day *t*:

```math
C(t) = \sum_{i \in \text{valid}(t)} a_i \qquad \text{gap}(t) = \max\big(0,\ R(t) - C(t)\big)
```

- The system computes two curves:
  - **Declared coverage** C₀(t) counts all instruments at trust level L0 or above.
  - **Attested coverage** C₃(t) counts only instruments at L3 or above.
  - **Verification exposure** = C₀(t) − C₃(t): rupees that AICTE is relying on but no bank has confirmed. This one number joins N1 and N2.
- **Gap forecasting:** an interval sweep over future dates finds the first day each obligation becomes under-covered (maturity without renewal, amount shortfall, partial release). That date becomes a task and drives reminders.
- **Renewal continuity check:** a replacement must start on or before the old instrument's maturity, and its amount must be at least the requirement. Otherwise a *continuity gap* flag is raised. This makes PS capability #5 checkable rather than just recordable.
- **UI:** a "coverage strip" timeline per institution (green = covered and attested, amber = covered but only declared, red = gap).

### N3. Bank-signed e-FDR credential (headline; proposal, simulated in the prototype)

- **Model:** the issuer–holder–verifier model from P7.
  - The **bank** issues a small signed JSON credential per FDR.
  - The **institution** holds it and submits it.
  - **AICTE** verifies it offline using the bank's pinned public key.
- **Release:** when the lien is removed on release, the bank revokes the credential. Its status record carries last/next-update fields (P2), so a stale status is detectable.
- **Precedent:** this extends the idea behind India's electronic bank guarantee and bank-to-bank BG advice to FDRs. The prototype uses a mock bank with Ed25519 signatures. Production would need a formal bank agreement (§14).
- **No personal data:** the credential carries no depositor PAN, phone or account numbers.

```json
{
  "type": "FDRAttestation",
  "issuer": "bank:<BANKCODE>:key-2026-01",
  "issued_at": "2026-03-12T10:41:00+05:30",
  "subject": {
    "instrument_no": "<FDR number>",
    "ifsc": "<IFSC>",
    "amount_inr": 0,
    "issue_date": "YYYY-MM-DD",
    "maturity_date": "YYYY-MM-DD",
    "beneficiary": "<as printed>",
    "lien_status": "MARKED"
  },
  "status": {"registry": "bank:<BANKCODE>:fdr-status", "index": 0,
             "last_update": "…", "next_update": "…"},
  "signature": "ed25519:…"
}
```

### N4. Verifiable audit trail with trust freshness

- **Hash chain:** every event is chained per instrument: `hash = SHA256(prev_hash ‖ canonical_json(event))`.
- **Anchoring:** periodically, a Merkle root over new events and document hashes is written to a tamper-evident store (immudb in the prototype; a permissioned ledger is the production option, per P9 Table 2).
- **Public verifier:** drop in any file and get either *"submitted on ⟨date⟩ by ⟨institution⟩, unchanged"* or *"no match"*.
- **Freshness and decay (from P2's next-update idea):** every L3/L4 confirmation carries `next_update`.
  - Once it passes without a re-check, L4 automatically drops to L3.
  - If the credential is revoked or the bank reports closure, the instrument drops to L0 and is flagged *critical*.
  - Trust is therefore time-bound, never permanent.

### N5. Policy-as-code release, discharge and refund (from P1, P10, P15)

- Release conditions are versioned, testable rule sets per case type: release / discharge / refund / early break.
  - Each rule cites the regulation clause it implements.
  - The rule version used is recorded in the audit trail.
- **Time boxes (the SMTSEC parameter idea):**
  - The institution has X days to answer a query, then the request auto-closes with notice.
  - Officers have Y days to act, then the case escalates.
  - X and Y are configured per case type.
- **Flow:** verify → log → notify at every step (P15).
- **Approval:** final approval is always a named competent authority with a mandatory reason.
- **Early release** (before the end of the prescribed period) requires an extra authenticated approval step, mirroring P10's authenticated early break.

### N6. Dual-pass extraction with disagreement routing (from P12, P13)

- **Two independent passes:** (a) OCR + LayoutLMv3 token classification and (b) OCR + rules/LLM key-value extraction.
  - Fields where the passes disagree, or where confidence is below the threshold (default 0.8, as in P13), are forced to human confirmation.
  - Known weak fields, such as multi-line addresses (P12), always go to a human.
- **Amount check:** the amount in figures is cross-checked against the amount in words.

### N7. Canonical instrument key, double-pledge and IFSC lineage

- **Canonical key:** `canonical_bank(IFSC) + normalised instrument number`, unique across all institutions.
  - A duplicate means the same FDR has been submitted twice or is backing two institutions, and raises a *critical* flag instantly.
  - Fuzzy matching (edit distance on the instrument number within the same bank) catches typos and deliberate near-duplicates.
- **IFSC lineage:** a lineage table maps old IFSC codes to current ones, because Indian bank mergers change IFSC codes. An old FDR from a merged bank still matches its current identity, and the bank's verification key is resolved correctly.
  - Lineage is seeded from the public RBI IFSC master. The exact source is to be confirmed (§14).

### N8. Clause-linked discrepancy explanations (from P14, P6, P13)

- **Every flag has three parts:**
  1. the **fact** gathered (P13's facts-then-rules);
  2. the **rule** that failed, with its clause reference from N5;
  3. a **plain-language reason**.
- **Retrieval:** when a rule has no direct clause mapping, the top-k clauses are retrieved from a vector index of the AICTE handbook/circulars (P14's FAISS-retrieval pattern). An LLM may draft the sentence, but the decision comes from the deterministic rule, never the LLM (P14 itself reports inconsistent generated justifications).
- **Risk classes:** the risk model outputs *genuine / grey area / suspicious* from configurable score bands (P6), with SHAP and Anchor-style reasons.

### N9. Renewal-risk forecasting with reasons (from P5, P6, P14)

- **Prediction:** the probability that an institution misses a renewal or response deadline, from its event history:
  - past lateness;
  - median response time;
  - open discrepancies;
  - days to maturity;
  - bank;
  - amount;
  - recency-weighted activity, using temporal decay (P14).
- **Escalation:** high-risk cases escalate earlier (e.g. at T-30 instead of T-7). Every escalation shows its reasons.
- **Evaluation:** follows P5's protocol (prefix encoding, chronological split). A direct remaining-time regressor is used because Navarin's direct approach ranked best in P5.

### N10. Procedural conformance replay (from P11)

- **Prescriptive constraints:** the Regulation Bureau's own procedure is written as constraints over the event log. Examples:
  - *"release approved ⇒ checklist complete before approval"*;
  - *"lien-removal confirmation within N days after release letter"*;
  - *"scrutiny observation recorded before discrepancy closed"*.
- **Nightly replay:** a job replays every case against the constraints and reports the result types identified in P11: quantify (conformance %), qualify (violated / not), localize (which event), explain (why).
- **Validation:** P11 found that prescriptive models are always built manually and rarely validated. Our constraints are therefore reviewed by an AICTE official and versioned (§14).
- **UI:** a "procedural compliance" panel for auditors.

---

