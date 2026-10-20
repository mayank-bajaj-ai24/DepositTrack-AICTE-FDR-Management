# Mayank's Research Notes — SIH 26265 DepositTrack

Oct 20, 2026 · @Mayank_Kathe

## What my 7 papers give us

Krrish's 8 papers cover the trust layer (SSI, blockchain revocation, forgery detection), the intelligence layer (predictive monitoring, SHAP/XGBoost, RAGAS) and the intake pipeline (LayoutLMv3, smart-contract workflow). My 7 papers fill the remaining gaps: **compliance monitoring frameworks**, **financial instrument lifecycle automation**, **intelligent document processing pipelines**, **regulatory dashboards with GenAI**, and **multi-agent review architectures**. Together the two sets cover every SIH capability.

| Paper | Core idea | What we borrow | Module it feeds |
| --- | --- | --- | --- |
| Rawat & Rahman, *Smart Contract Based Approach for Fixed Deposit in Blockchain Networks with Remix IDE*, IJCRT 2023 | Solidity smart contract encodes the entire FD lifecycle — creation, interest accrual, maturity lock, premature withdrawal penalty — and executes it without a bank intermediary | The FD lifecycle state model (deposit → lock → mature → payout) and the penalty/condition-gate pattern; maps 1:1 to our FDR lifecycle engine states | M7 Lifecycle engine, M9 Release workflow |
| Wu, Yao, Liu et al., *Blockchain for Finance: A Survey*, arXiv:2402.17219, 2024 | Survey of 12 blockchain platforms applied to capital raising, securities trading, financial analysis and investment management; analyses DeFi security and financial market infrastructure (FMI) | Taxonomy of consensus mechanisms for choosing our anchoring layer (PoA / BFT for permissioned); the four-category application model validates our use of blockchain for audit and verification only, not for payments; threat model for DeFi bridges warns us about key-management risks | M6 Ledger anchoring, M5 Bank verification, security slide |
| Klessascheck & Pufahl, *Reviewing Uses of Regulatory Compliance Monitoring*, arXiv:2501.10362, 2024 | Systematic literature review of how organisations monitor process compliance with external regulations using IT system execution data; maps conformance-checking, process mining and data-driven techniques | The compliance-monitoring taxonomy: *regulation operationalisation → monitoring technique → result type*; shows that most real systems still rely on manual regulation encoding, validating our approach of policy-as-code (N4); identifies the gap that automated alert generation is under-researched — exactly what our M8 fills | M8 Alerts and escalation, M9 Release workflow (policy-as-code), M10 Dashboard |
| Khanvilkar & Kommuru, *Regulatory Graphs and GenAI for Real-Time Transaction Monitoring and Compliance Explanation in Banking*, arXiv:2506.01093, 2025 | Graph neural network (GNN) over a regulatory knowledge graph + RAG pipeline for real-time transaction monitoring; flags suspicious items and maps each flag to the specific regulatory clause it violates, with a natural-language explanation | The *flag → regulatory clause → natural-language explanation* pipeline is exactly what our discrepancy engine (M4) needs; we reuse the idea of a regulation knowledge graph built from AICTE's Approval Process Handbook to power both M4 flag reasons and M11 officer assistant; the real-time monitoring dashboard design informs our M10 | M4 Discrepancy engine, M10 Dashboard, M11 Officer assistant |
| Multi-agent framework, *Enhancing the Efficiency and Accuracy of Underlying Asset Reviews in Structured Finance*, arXiv:2405.04294, 2024 | Multi-agent AI system where specialised agents (data extraction, cross-validation, anomaly detection, report generation) collaborate to review financial assets in structured finance deals | The agent decomposition pattern: one agent extracts, another validates, another flags, another reports — maps directly to our pipeline (M3 extraction → M4 checks → M5 bank verification → M10 reports); also shows how to measure review efficiency (time per asset, error rate) which gives us our KPI measurement methodology | M3 Extraction, M4 Discrepancy engine, KPI measurement |
| Islam, Salekin, King et al., *IDP Accelerator: Agentic Document Intelligence from Extraction to Compliance Validation*, arXiv:2602.23481, 2026 | End-to-end intelligent document processing (IDP) framework by AWS: ingest → extract (OCR + layout models) → validate against business rules → compliance check; uses agentic orchestration so each step is an autonomous agent that can retry, escalate or ask for human review | The agentic orchestration loop for our intake pipeline: upload triggers extraction agent → extraction output triggers validation agent → validation triggers compliance-check agent → human-in-the-loop if confidence is low; also the evaluation methodology (extraction accuracy, compliance-check precision, end-to-end latency) | M2 Intake, M3 Extraction, M4 Discrepancy engine |
| (Blockchain Audit Trail paper, 2023) | Blockchain-based immutable audit trail for cloud-based payment and financial systems; uses permissioned ledger to guarantee tamper-proof logging of every state change | Hash-chain design for event logs; Merkle-root anchoring pattern for periodic batch integrity proof; the read-only auditor node architecture for regulatory inspection without write access | M6 Ledger anchoring, M1 Access control (auditor role) |

## Notes per paper

### Smart Contract for Fixed Deposits (IJCRT 2023)

This is the only paper in our combined set that is *directly about fixed deposits*. The Remix IDE implementation encodes:
- **Deposit creation**: depositor address, amount, interest rate, maturity date, beneficiary address.
- **Lock period enforcement**: withdrawals blocked until maturity; premature withdrawal triggers a penalty deduction.
- **Maturity payout**: automatic release of principal + accrued interest when `block.timestamp >= maturityDate`.
- **Condition gates**: the contract checks conditions (KYC verified, no pending disputes) before allowing payout.

**What we copy**: the lifecycle state model (`Created → Locked → Mature → PaidOut`) maps directly to our FDR states (`Submitted → Active → Expiring → Released`). The condition-gate pattern (checking all prerequisites before allowing a state transition) is what our release workflow (M9) uses: no release unless all checklist items are green. The penalty/auto-escalation on missed deadlines informs our alert engine (M8).

**What we change**: we don't use a public blockchain or cryptocurrency; the smart-contract logic becomes our policy-as-code engine running as versioned Python rules. The "interest accrual" logic is irrelevant (AICTE doesn't pay interest on deposits it holds as security), but the locked-until-maturity enforcement transfers perfectly.

**Gap this fills**: Krrish's SMTSEC paper (2020) covers smart contracts for *construction payments*; this paper covers smart contracts for *fixed deposits specifically*, giving us a more direct citation for the lifecycle engine.

---

### Blockchain for Finance Survey (arXiv 2024)

A comprehensive survey covering 12 blockchain platforms with deep analysis of 6 platforms relevant to financial services. Key sections we use:

- **Consensus mechanism comparison** (Table 3 in paper): PoW, PoS, BFT, PoA benchmarked on throughput, latency, finality. We pick PoA or BFT (Hyperledger Fabric / immudb) because our network is small (AICTE + banks), trusted nodes, and we need fast finality for audit anchoring.
- **Four application categories**: capital raising, securities trading, financial analysis, investment management. Our use case (regulatory deposit tracking) falls under a new fifth category: *regulatory compliance infrastructure*. This is a gap we explicitly mention in our novelty slide.
- **DeFi security analysis**: the paper warns about key-management attacks, front-running, and oracle manipulation. We apply this to our bank-credential verification: the bank's signing key must be rotated, pinned, and never exposed to the portal's operators.
- **Financial Market Infrastructure (FMI) framework**: the paper maps blockchain adoption to CPMI-IOSCO principles. We cite this to argue that our audit-trail architecture aligns with international standards for financial infrastructure.

**Gap this fills**: Krrish's SSI survey (2022) covers the identity/credential model; this paper covers the *financial infrastructure layer* — consensus, security, and institutional adoption patterns. Together they give a complete blockchain story for judges.

---

### Regulatory Compliance Monitoring Review (arXiv 2024/2025)

This systematic literature review is the most directly relevant paper to our *process* design. Key findings:

- **Taxonomy of compliance monitoring**: the paper identifies four stages: (1) *regulation operationalisation* (turning legal text into checkable rules), (2) *data preparation* (extracting events from IT systems), (3) *monitoring technique* (conformance checking, process mining, rule engines), (4) *result presentation* (dashboards, alerts, reports).
- **Key gap identified**: most systems rely on *manual* regulation operationalisation — a human reads the law and writes the rules. The paper calls for automated regulation-to-rule conversion. Our N4 (policy-as-code) addresses this gap by encoding AICTE's Approval Process Handbook conditions as versioned, testable rule sets.
- **Alert generation is under-researched**: the paper notes that while monitoring *detects* violations, the *notification and escalation* step is usually ad-hoc. Our M8 (configurable reminders at T-90/60/30/7, risk-based early escalation) is a direct response to this gap.
- **Process mining for compliance**: the paper shows how event logs can be mined for compliance patterns. We apply this to our renewal-risk prediction (N3): mining the event log for patterns that predict missed renewals.

**What we borrow for the PPT**: the four-stage taxonomy diagram as a framing slide: "Here is how compliance monitoring works in general. Here is how FDR Guardian implements each stage."

**Gap this fills**: none of Krrish's papers address the *compliance monitoring process* at this architectural level. This paper gives us the theoretical backbone for our alert engine, dashboard, and policy-as-code modules.

---

### Regulatory Graphs + GenAI for Transaction Monitoring (arXiv 2025)

This paper is the closest to our *intelligence layer* design. Key mechanisms we transfer:

- **Regulation knowledge graph**: regulatory text is parsed into a graph where nodes are clauses, obligations, and entities, and edges are relationships (requires, prohibits, triggers). We build the same graph from the AICTE Approval Process Handbook: nodes are clauses like "Clause 4.3.1: minimum FDR amount for engineering college = Rs 25 lakh", edges connect to institution types, deposit requirements, and release conditions.
- **Flag → clause mapping**: when the system flags a transaction, it traces back through the graph to the specific regulation clause. We apply this to discrepancy flags: "This FDR is flagged because the amount (Rs 10,00,000) is below the minimum required by Clause 4.3.1 (Rs 25,00,000) for engineering colleges."
- **Natural-language explanation via RAG**: the system uses Retrieval-Augmented Generation to produce human-readable explanations of why a flag was raised. We use the same pattern for our officer assistant (M11) and for flag reason text in M4.
- **Real-time monitoring dashboard**: the paper's dashboard design shows risk scores, regulatory coverage, and pending actions — very close to our M10 dashboard tiles.

**What we change**: the paper targets banking transactions (AML/KYC); we target FDR lifecycle events (submission, verification, renewal, release). The graph structure is simpler for us (one regulatory body, one handbook) but the pattern is identical.

**Gap this fills**: Krrish's RAGAS paper measures the assistant's faithfulness, but doesn't explain *how to build the regulation knowledge* that feeds it. This paper gives us the methodology for constructing the AICTE regulation graph that powers both M4 flags and M11 assistant.

---

### Multi-agent Asset Review Framework (arXiv 2024)

This paper's architecture maps almost exactly to our pipeline. Its agents:

1. **Data Extraction Agent**: reads financial documents (prospectuses, loan tapes) and extracts structured fields → our M3 (OCR + LayoutLMv3).
2. **Cross-Validation Agent**: checks extracted data against external sources and business rules → our M4 (rule checks) + M5 (bank verification).
3. **Anomaly Detection Agent**: flags outliers and inconsistencies → our M4 (forgery + discrepancy scoring).
4. **Report Generation Agent**: produces review reports with findings and recommendations → our M10 (dashboard + reports).

**What we borrow**: the agent decomposition and the inter-agent communication protocol (each agent's output is the next agent's input, with confidence scores attached). Also the efficiency metrics: *time per asset review*, *error rate*, *human review rate*. We use the same metrics for our KPI measurement.

**Key insight for our design**: the paper shows that the multi-agent approach reduces review time by 60-80% compared to manual review. We cite this when projecting our own KPI improvements (manual FDR processing: 8-10 minutes → portal: under 1 minute).

**Gap this fills**: none of Krrish's papers address the *pipeline architecture* at this level. The multi-agent decomposition validates our modular design (M2 → M3 → M4 → M5 as a chain of specialised agents).

---

### IDP Accelerator (arXiv 2026)

This AWS research paper is the most technically detailed paper in our set for the intake pipeline. Key mechanisms:

- **Agentic orchestration**: each processing step (extraction, validation, compliance check) is an autonomous agent that can retry on failure, escalate to a human reviewer when confidence is below threshold, and log every decision for audit. We apply this to our M2-M3-M4 chain.
- **Multi-modal extraction**: the system handles PDFs, images, and structured forms using a combination of OCR, layout models, and LLMs. This is exactly our extraction stack (docTR/PaddleOCR + LayoutLMv3 + post-processing rules).
- **Compliance validation engine**: extracted fields are checked against configurable business rules. Fields that fail validation are flagged with the specific rule that was violated. This is our M4 rule engine.
- **Human-in-the-loop design**: when the system's confidence is below a threshold (e.g., 0.85), it routes to a human reviewer with the extraction results and the specific fields that need confirmation. This is our OCR auto-fill with highlighted low-confidence fields.
- **Evaluation metrics**: extraction accuracy (field-level F1), compliance-check precision/recall, end-to-end latency, and human-review rate. We use the same metrics in our "What we report to judges" table.

**What we change**: the paper is general-purpose IDP; we specialise it for Indian FDR documents with specific field labels (FDR_NO, BANK, IFSC, AMOUNT, etc.) and Indian formatting rules (Rs. amount format, IFSC regex).

**Gap this fills**: Krrish's plan mentions LayoutLMv3 for extraction but doesn't detail the *end-to-end pipeline orchestration* or the *agentic retry/escalation* pattern. This paper gives us the architecture for a production-quality intake pipeline.

---

### Blockchain Audit Trail (2023)

This paper reinforces Krrish's audit trail design (M6) with additional details:

- **Append-only event store**: every state change is written as an immutable record with timestamp, actor, action, before/after state, and cryptographic hash linking to the previous record.
- **Merkle-root batch anchoring**: periodically, a batch of new records is hashed into a Merkle tree, and the root is anchored on a permissioned ledger. Any tampering in the batch is detectable by recomputing the tree.
- **Read-only auditor node**: regulators and auditors connect to the ledger as read-only nodes, gaining full visibility without the ability to modify records. This is our auditor role (M1) with our verifier page (M6).
- **Performance benchmarks**: the paper measures anchoring latency and storage overhead, showing that the approach is viable even for high-volume transaction systems. Our FDR system has much lower volume (thousands of instruments, not millions of transactions), so performance is not a concern.

**Gap this fills**: Krrish's blockchain revocation paper (2021) focuses on *certificate revocation* specifically; this paper covers the *general audit trail architecture* more broadly, giving us a second citation for our M6 module and the verifier page.

---

## Gap analysis: what our combined papers don't cover vs what FDR Guardian builds

| Gap | Papers don't cover it because | How FDR Guardian fills it | Evidence from papers |
| --- | --- | --- | --- |
| AICTE-specific FDR regulations | No paper studies Indian technical-education regulatory deposits | We encode the Approval Process Handbook as policy-as-code (N4) and build a regulation knowledge graph (from Paper 4) | Paper 3 (compliance monitoring review) explicitly calls for automated regulation operationalisation as an open research challenge |
| Legacy scanned documents + modern digital verification in one system | Papers assume either all-digital (smart contracts) or all-paper; none bridge both | Our intake pipeline (M2-M3) handles scanned legacy FDRs with OCR, while the bank verification gateway (M5) handles digital credentials; the Trust Ladder (N1) shows the provenance level of each field | Paper 6 (IDP Accelerator) handles multi-format documents but doesn't bridge to bank-side digital credentials |
| Lifecycle tracking with configurable renewal alerts | Smart contract papers (Paper 1) track maturity but don't have configurable reminder schedules | Our lifecycle engine (M7) with T-90/60/30/7 configurable alerts (M8) and risk-based early escalation (N3) | Paper 3 (compliance monitoring) identifies alert generation as under-researched |
| Regulator's multi-step release workflow | No paper models a multi-approver, condition-gated release process for government deposits | Our release workflow (M9) with policy-as-code checklist, time-boxed auto-escalation, and competent-authority approval | Paper 1 (smart contract FD) has condition gates for payout; Paper 3 (compliance review) has the regulation-to-rule pattern |
| Duplicate/double-pledge detection across institutions | No paper addresses the specific fraud pattern of one FDR backing two institutions | Our N8 (duplicate detection via normalised key: IFSC + FDR number + fuzzy matching) | Paper 5 (multi-agent review) has anomaly detection agents but for general financial anomalies |
| India-specific integration (DigiLocker, Account Aggregator, NeSL) | Papers are jurisdiction-agnostic | We design adapter patterns for Indian financial infrastructure | Paper 2 (blockchain finance survey) covers international FMI standards that Indian systems follow |

## How my papers + Krrish's papers together cover all 10 SIH capabilities

| # | SIH Capability | Krrish's papers | My papers | Combined coverage |
|---|---|---|---|---|
| 1 | Centralized repository | — | Paper 5 (multi-agent review: data model), Paper 6 (IDP: document store) | Architecture for institution-wise and instrument-wise records |
| 2 | Digital document management | LayoutLMv3 (2022) | Paper 6 (IDP Accelerator: end-to-end pipeline), Paper 5 (multi-agent: extraction agent) | Complete intake pipeline from upload to structured data |
| 3 | Verification and discrepancy detection | SSI survey (2022), RGB-GLCM forgery (2022) | Paper 4 (regulatory graphs: flag-to-clause mapping), Paper 5 (multi-agent: cross-validation agent) | Bank verification + forgery detection + regulatory-clause-linked flags |
| 4 | Validity and maturity tracking | — | Paper 1 (smart contract FD: maturity lock/payout), Paper 3 (compliance monitoring: monitoring techniques) | Lifecycle engine with configurable monitoring |
| 5 | Renewal and replacement monitoring | Bloom-filter revocation (2021) | Paper 1 (smart contract FD: renewal logic), Paper 3 (compliance monitoring: alert generation gap) | Linked instrument chain + configurable alerts |
| 6 | Release and refund workflow | SMTSEC (2020) | Paper 1 (smart contract FD: condition-gated payout), Paper 3 (compliance monitoring: regulation operationalisation) | Policy-as-code release with condition gates and time boxes |
| 7 | Alerts and escalation | Predictive monitoring (2023) | Paper 3 (compliance monitoring: identifies alert gap), Paper 4 (regulatory graphs: real-time monitoring) | Risk-based early escalation + regulatory-clause-aware alerts |
| 8 | Dashboard and reports | — | Paper 4 (regulatory graphs: compliance dashboard), Paper 5 (multi-agent: report generation agent) | Risk heatmap, regulatory coverage, pending actions |
| 9 | Audit trail and access control | Bloom-filter revocation (2021) | Paper 2 (blockchain finance survey: consensus + security), Paper 7 (blockchain audit trail: Merkle anchoring) | Hash-chained audit log + ledger anchoring + auditor role |
| 10 | Integration and data security | SSI survey (2022) | Paper 2 (blockchain finance survey: FMI standards, DeFi security), Paper 6 (IDP: agentic orchestration) | Adapter layer + encryption + key management |

## References

Papers in my `research/Mayank_Kathe/` folder:

1. Rawat, A., Rahman, H. U. (2023). Smart Contract Based Approach for Fixed Deposit in Blockchain Networks with Remix IDE. *International Journal of Creative Research Thoughts (IJCRT)*, 11(5). https://ijcrt.org/papers/IJCRT2305558.pdf
2. Wu, H., Yao, Q., Liu, Z. et al. (2024). Blockchain for Finance: A Survey. *arXiv:2402.17219*. https://arxiv.org/abs/2402.17219
3. Klessascheck, F., Pufahl, L. (2024). Reviewing Uses of Regulatory Compliance Monitoring. *arXiv:2501.10362* / *Software and Systems Modeling* (2025). https://arxiv.org/abs/2501.10362
4. Khanvilkar, K., Kommuru, K. (2025). Regulatory Graphs and GenAI for Real-Time Transaction Monitoring and Compliance Explanation in Banking. *arXiv:2506.01093*. https://arxiv.org/abs/2506.01093
5. (2024). Enhancing the Efficiency and Accuracy of Underlying Asset Reviews in Structured Finance: The Application of Multi-agent Framework. *arXiv:2405.04294*. https://arxiv.org/abs/2405.04294
6. Islam, M. M., Salekin, M. S., King, J. et al. (2026). IDP Accelerator: Agentic Document Intelligence from Extraction to Compliance Validation. *arXiv:2602.23481*. https://arxiv.org/abs/2602.23481
7. Blockchain-Based Audit Trail for Cloud-Based Payment Systems (2023). *(see Blockchain Audit Trail.pdf in folder)*
