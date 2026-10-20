FDR Guardian — SIH 26265 Implementation Plan
Oct 20, 2026 · @Krrish
Executive summary
We will build FDR Guardian, a web portal where every AICTE security deposit / FDR is read by AI, checked for tampering, confirmed by the issuing bank's digital signature, anchored on a permissioned ledger, and tracked by a lifecycle engine that predicts missed renewals before they happen.
One-line pitch for judges: "Every FDR in one place, every rupee verified by the bank, every action provable, and every renewal risk flagged 30 days early."
The plan has three layers. The core (must work end to end in the demo) is the repository, upload, OCR extraction, maturity tracking, alerts, release workflow, dashboard and audit trail. The trust layer (our main differentiator) is bank-signed verification, the two-level Institution-declared vs Bank-verified badge, forgery scoring and ledger anchoring. The intelligence layer (our wow factor) is renewal-risk prediction and a regulation-grounded assistant for officers.
#
SIH expected capability
Where it lives in FDR Guardian
Research basis
1
Centralized repository
Institution → Instrument → Event data model, PostgreSQL
—
2
Digital document management
Upload service, MinIO encrypted storage, LayoutLMv3/OCR auto-fill
LayoutLMv3 (2022)
3
Verification and discrepancy detection
Bank-signed credential check, rule engine, forgery score, trust badge
SSI survey (2022), RGB-GLCM forgery (2022)
4
Validity and maturity tracking
Lifecycle engine with scheduler, T-90/60/30/7 reminders
—
5
Renewal and replacement monitoring
Linked instrument chain (old FDR → renewed FDR), status history
Bloom-filter revocation (2021)
6
Release and refund workflow
Condition-gated, multi-approver workflow with time-boxed auto-escalation
SMTSEC smart contract (2020)
7
Alerts and escalation
Notification service (email, SMS, in-app) + predicted-risk escalation
Predictive process monitoring benchmark (2023)
8
Dashboard and reports
Officer dashboard, risk heatmap, scheduled PDF/Excel reports
—
9
Audit trail and access control
Hash-chained audit log, ledger anchoring, RBAC + ABAC
Bloom-filter revocation (2021)
10
Integration and data security
Adapter layer (AICTE portal, bank API, DigiLocker-style pull), encryption
SSI survey (2022)
The officer assistant (RAG over the Approval Process Handbook) and its RAGAS-based evaluation sit across capabilities 3, 6 and 8.
Problem understanding
The core problem is not storage: it is that AICTE cannot tell, at any moment, which deposits are genuine, which are about to lapse, and which cases are stuck. Today that view is spread across scanned PDFs, emails, spreadsheets and bank letters.
The lifecycle of one FDR
1. Submission: the institution creates an FDR at a bank (often jointly in favour of AICTE or with a lien marked), scans it and uploads it during approval.
2. Scrutiny: an officer checks amount, beneficiary name, lien marking, tenure and bank details against the requirement for that institution type.
3. Verification: the officer confirms with the bank that the FDR exists and is not encumbered elsewhere. This is the slowest step today because it is done by letter or email.
4. Active monitoring: the deposit sits for years. Maturity dates and auto-renewal status must be tracked.
5. Renewal / replacement: before maturity the institution must renew or replace the FDR, and AICTE must receive the new instrument.
6. Release / refund: on closure, change of status or completion of conditions, the institution requests release. The competent authority checks conditions and approves; the bank removes the lien.
7. Archive: the full history stays available for audit and RTI.
Pain points we will measure
Pain point
Today (assumed baseline, to validate with officials)
Target with FDR Guardian
Manual data entry per FDR
8–10 minutes typing fields
Under 1 minute (OCR auto-fill + confirm)
Bank verification turnaround
Days to weeks (letters / email)
Seconds where bank API exists; tracked SLA otherwise
Missed maturities
Found only when someone checks
Zero silent lapses; alerts at T-90/60/30/7 days
Forged or edited scans
Caught only by eye
Automatic forgery score + mismatch flags
Who did what, when
Scattered in email
One hash-chained audit trail per instrument
Pending-case visibility
Spreadsheet counts
Live dashboard with ageing and risk
The baseline numbers are our assumptions. Before the demo, interview at least one AICTE or college accounts official to replace them with real figures; judges reward measured baselines.
Actors and roles
Role
What they do in the portal
Institution user
Uploads FDRs, sees status, responds to discrepancies, requests renewal or release
Scrutiny officer (Regulation Bureau)
Reviews submissions, records observations, raises discrepancies
Verifying officer / Finance
Triggers and records bank verification
Competent authority
Approves release / refund, overrides with recorded reason
Bank (integration actor)
Issues signed confirmation, confirms lien marking and lien removal
Auditor (read-only)
Views full history and ledger proofs
System admin
Manages users, roles, rule configuration, reminder schedules
What the research papers give us
Each of the 8 papers you uploaded contributes one concrete mechanism; none of them is about FDRs, so the novelty is the transfer. The table is the quick map, and the notes under it say exactly what we copy and what we change.
Paper
Core idea
What we borrow
Module
Ahmadisheykhsarmast & Sonmez, A smart contract system for security of payment of construction contracts, Automation in Construction 120 (2020)
SMTSEC blocks the next payment in a smart contract; release only on approval; auto-release if no action within a fixed period
Condition-gated release, time-boxed periods (PeriBloc / PeriPay), parameterised contract terms
Release workflow
Elloh Adja et al., A blockchain-based certificate revocation management and status verification system, Computers & Security 104 (2021)
Revoked certificates stored in Bloom filters on a ledger; signed status records chained by next/last-update pointers; Merkle root signed by the CA
Signed, chained status records; Merkle-root anchoring; fast "is this FDR still valid?" lookup
Ledger anchoring, status check
Huang et al., LayoutLMv3, ACM MM 2022
One Transformer over text + layout + image patches; 92.08 F1 on FUNSD forms
Key-field extraction from scanned FDRs (token classification)
Intake / OCR
Gornale, Patil & Benne, Document Image Forgery Detection Using RGB Color Channel, TMLAI 10(5) 2022
GLCM contrast, homogeneity, energy on R, G, B channels + SVM; 93.11% on printed forgeries across 10 forgery classes
9-feature RGB-GLCM vector per region, cheap SVM baseline, the 10-class forgery taxonomy for our synthetic data
Forgery check
Rama-Maneiro, Vidal & Lama, Deep Learning for Predictive Business Process Monitoring: Review and Benchmark, IEEE TSC 2023
Benchmark of 10 deep models on 12 event logs
Event-log design (case id, activity, timestamp, resource); direct remaining-time prediction beats recursive; LSTM baseline
Renewal-risk prediction
Thanathamathee et al., SHAP-Instance Weighted and Anchor Explainable AI: Enhancing XGBoost for Financial Fraud Detection, Emerging Science Journal 8(6) 2024 (your 16.pdf)
XGBoost with SHAP-based instance weights + Anchor if-then rules; three classes: genuine, fraudulent, grey area
Three-class risk output and human-readable if-then reasons for each flag
Discrepancy risk score
Ahmed et al., Blockchain-Based Identity Management System and Self-Sovereign Identity Ecosystem, IEEE Access 2022
W3C Verifiable Credentials: issuer signs, holder stores, verifier checks signature via the issuer's DID without contacting the issuer; five pillars: authentication, integrity, privacy, trust, simplicity
Bank as issuer, institution as holder, AICTE as verifier; revocation registry for released FDRs
Bank verification, trust badge
Es et al., RAGAS: Automated Evaluation of Retrieval Augmented Generation, EACL 2024 demo
Reference-free metrics: faithfulness, answer relevance, context relevance; 0.95 agreement with humans on faithfulness
Score our officer assistant before every demo; publish the score
Regulation assistant
Notes per paper
SMTSEC (2020). Their contract has explicit parameters (contingency %, blocking period, payment period) and a release rule that stops funds being locked forever in a dispute. We copy the shape, not the cryptocurrency: our release workflow is a state machine with configurable periods per case type, and the transition rules are written as versioned, testable code (a "policy contract"). The interviews in their Table 4 also warn us that legal backing and loss of authority worry officials, so final approval always stays with a named human.
Blockchain revocation (2021). Two ideas transfer directly. First, every status record carries last update and next update fields, so a missing record is detectable (their Fig. 4). Second, the record is hashed in two parts, combined in a Merkle root and signed (their Fig. 5). We apply this to FDR status: when an FDR is released, it goes into the "released" set, and anyone holding a copy can check in milliseconds that it is no longer active. A Bloom filter is optional at our scale (thousands, not millions, of FDRs), but showing it with the false-positive formula below is a nice technical touch in the PPT.
P_{fp} = \left(1 - e^{-kn/m}\right)^{k}
LayoutLMv3 (2022). It removes the CNN backbone (133M parameters for base) and works on scanned forms out of the box. We fine-tune microsoft/layoutlmv3-base for token classification with our labels (FDR_NO, BANK, BRANCH, IFSC, AMOUNT, DEPOSIT_DATE, MATURITY_DATE, BENEFICIARY, DEPOSITOR, LIEN_TEXT). Its ablation (Table 3) shows text + layout alone already gets 88.64 F1 on FUNSD, so a cheaper fallback is a text-only extractor plus regex rules.
RGB-GLCM forgery (2022). Simple, explainable and fast enough to run on every upload. Weaknesses we must admit: tiny custom dataset (950 images), images resized to 100×100, and a fixed similarity threshold of 40. We use it as one signal among several (metadata, font consistency, error-level analysis), never as a verdict.
Predictive monitoring benchmark (2023). Key findings we act on: a direct remaining-time model (Navarin et al.) beats recursive suffix prediction; simple LSTM (Tax et al.) is a strong default; attributes help only when data is sufficient. Our event logs will be small, so we start with gradient boosting on hand-made features and keep an LSTM as an experiment.
SHAP + Anchor XGBoost (2024). The "grey area" class is exactly what officers need: not just genuine vs suspicious, but needs a human look. Anchor rules give a reason like "IF amount < required slab AND bank not on verified list THEN suspicious (precision 0.96)".
SSI survey (2022). Gives the vocabulary judges recognise: issuer, holder, verifier, DID, verifiable credential, revocation registry, selective disclosure. It also lists five design pillars we will use as section headings in our security slide.
RAGAS (2024). Its faithfulness metric (supported statements ÷ total statements) is the number we put on screen to prove the assistant does not invent rules.
F = \frac{|V|}{|S|}
Existing solutions and how we relate to them
No open-source project manages FDR / security-deposit lifecycles for a regulator, but nine nearby systems each solve one slice; we reuse their patterns and integrate the ones that are libraries. The closest real-world analogue is India's electronic bank guarantee ecosystem, which already proves banks will sign and share instrument data digitally.
The Chrome connection timed out during this session, so this section is written from prior knowledge, not freshly opened pages. Open each repository and site before citing it in your PPT; details such as maintainers and licences can change.
Indian government and banking systems
System
What it does
Similarity to FDR Guardian
What we do differently
NeSL e-Bank Guarantee (National E-Governance Services Ltd, launched around 2021)
Banks issue bank guarantees electronically on NeSL; beneficiary sees and verifies them online; no paper
Same core idea: the bank, not the applicant, is the source of truth for the instrument
We cover FDRs and deposits (not only BGs), add lifecycle tracking, forgery checks on legacy scans and release workflow for a regulator
SFMS bank-guarantee advice (IFN 760COV / 767COV messages between banks)
Issuing bank sends BG details over the banks' SFMS network so the beneficiary's bank can confirm them
Bank-to-bank confirmation instead of trusting a scan
We model the same "advice" as a signed verifiable credential AICTE can check directly, and show it as a trust badge
RBI Account Aggregator framework (Sahamati ecosystem)
Consent-based, encrypted sharing of financial data; term deposits are a supported data type
Lets AICTE pull FDR status (balance, maturity, closure) with the institution's consent
We propose AA as a future integration; it needs AICTE or a partner to be a registered information user, so the demo uses a simulator
DigiLocker issuer / requester APIs
Issuers push signed documents; requesters pull them with user consent
Pattern for "pull the document from the issuer" rather than accept an upload
We reuse the issuer-signed pull pattern for bank confirmations
Open-source building blocks
Project (GitHub)
What it is
Similarity
How we use it
OpenAttestation / OpenCerts (Singapore GovTech)
Documents hashed into a Merkle root anchored on a ledger; anyone verifies a file against the root
Same "anchor the hash, verify the file later" idea as our document anchoring
Copy the Merkle-batch anchoring and the verifier UX (drag a file in, see valid / tampered)
Blockcerts
Open standard and tools for blockchain-anchored certificates
Credential issuance + verification with revocation
Reference for the JSON credential shape and revocation list
ACA-Py, Aries Cloud Agent Python
Agent that issues, holds and verifies W3C / AnonCreds verifiable credentials, with revocation registries
Exactly the issuer–holder–verifier model in the SSI survey
Run a "mock bank" issuer agent and an AICTE verifier agent for the demo
Hyperledger Fabric
Permissioned ledger with chaincode and private data
Permissioned, government-friendly ledger
Optional stretch; default demo uses immudb for speed
immudb
Tamper-evident database with cryptographic proofs of inclusion and consistency
Our audit log needs exactly this property
Store audit events and document hashes; show proofs in the UI
docTR / PaddleOCR
Open OCR engines with layout output
Front end of the extraction pipeline
Produce words + boxes that feed LayoutLMv3
LayoutLMv3 (microsoft/unilm)
Pre-trained document model from the paper
Key-field extraction
Fine-tune on our FDR samples
Camunda / Flowable
BPMN workflow engines with timers, escalations and human tasks
Release and renewal are long-running approval processes
We keep a lighter custom state machine for the hackathon, but design states in BPMN terms so a ministry IT team could port it
ragas
Evaluation library from the RAGAS paper
Measures our assistant's faithfulness
Run in CI on a fixed question set
The gap we fill
Every system above is either bank-side (e-BG, SFMS, AA), document-side (OpenAttestation, Blockcerts) or a generic engine (Camunda, immudb). None of them joins legacy scanned FDRs, bank confirmation, lifecycle deadlines, prediction and a regulator's release workflow in one place. That join is our product.
Novelty stack
We lead with three headline novelties and keep five supporting ones ready for questions; each one is demo-able in under 60 seconds.
Headline novelties (put these on the title slide)
N1. Trust Ladder instead of a yes/no status. Every field of every FDR carries a provenance level, directly answering the problem statement's line about separating institution-submitted from bank-confirmed data.
Level
Meaning
How it is reached
L0 Declared
Typed or uploaded by the institution
Default
L1 Machine-checked
OCR value matches typed value; rules pass; forgery score low
Intake pipeline
L2 Officer-verified
A named officer confirmed after scrutiny
Officer action, logged
L3 Bank-attested
Bank-signed credential matches every key field
Signature verified against the bank's public key
L4 Live-confirmed
Bank or Account Aggregator confirms current status (not closed, lien intact)
Periodic re-check, timestamped
The dashboard shows the ladder as a coloured badge per instrument and per field. Judges understand it instantly.
N2. Bank-signed FDR credential ("e-FDR advice"). We define a small JSON verifiable credential a bank can issue for each FDR: number, amount, dates, beneficiary, lien status, signed by the bank. AICTE verifies it offline with the bank's public key, and a revocation registry tells AICTE when the lien is removed. This extends NeSL's e-BG idea to FDRs and uses the issuer–holder–verifier model from the SSI survey. In the demo a mock bank issuer runs on ACA-Py or a simple Ed25519 signer.
N3. Renewal-risk forecasting with reasons. Instead of only sending reminders, the system predicts the probability that an institution will miss a renewal or response deadline, from its event history (past delays, response times, number of discrepancies, bank, instrument size). High-risk cases are escalated 30 days early, with Anchor-style reasons ("IF last two renewals were late AND discrepancy still open THEN high risk"). This combines the predictive process monitoring benchmark with the SHAP/Anchor paper.
Supporting novelties (ready for Q&A or as stretch goals)
N4. Policy-as-code release contract. Release conditions (closure order, no pending dues, approvals) are encoded as versioned rules with time-boxed states, inspired by SMTSEC's PeriBloc / PeriPay. Officers see a checklist that ticks itself as evidence arrives, and the rule version used is recorded in the audit trail.
N5. Verifiable audit trail with public proof. Each event is hash-chained; every hour a Merkle root of new events is anchored in immudb (or Fabric). An auditor can upload any FDR scan and get "this exact file was submitted on 12 Mar 2026 by user X" with a cryptographic proof, borrowing the OpenAttestation verifier pattern and the signed, chained status records of the 2021 revocation paper.
N6. Multi-signal forgery score. RGB-GLCM texture features (2022 paper) + error-level analysis + PDF metadata checks + font-consistency on the amount and date fields + cross-check against the bank credential. Output is genuine / grey area / suspicious with the strongest signals named.
N7. Regulation-grounded officer assistant with a published faithfulness score. RAG over the Approval Process Handbook and circulars answers "Is this institution eligible for release?" with clause citations. We show the RAGAS faithfulness and context-relevance scores on our evaluation set, so judges see a measured, not claimed, reliability.
N8. Duplicate and double-pledge detection. A normalised key (bank IFSC + FDR number) and fuzzy matching across all institutions flag the same FDR being submitted twice, or one FDR backing two institutions. This is cheap to build and catches a real fraud pattern.
All eight are framed as proposals where they depend on banks or AICTE systems: in the prototype the bank and the Account Aggregator are simulators, and we say so openly.
System architecture
A modular monolith in Python behind one gateway is the right size for a hackathon team: one repository, one Docker Compose file, services split by folder so they can become microservices later.
Every actor, including the bank, enters through the same gateway and its role checks; bank verification is highlighted because it is what moves an FDR up the Trust Ladder.
Data flow for one upload
1. Institution uploads the scan; the gateway checks the role; Intake stores the file in MinIO and its SHA-256 in PostgreSQL.
2. A Celery job runs OCR + LayoutLMv3 and saves extracted fields with confidence.
3. Forgery + rules runs and stores flags with reasons; Trust Ladder moves to L1 if clean.
4. Bank verification requests or receives the signed credential and compares fields; L3 if it matches.
5. Every step writes an audit event; the hourly job anchors a Merkle root in immudb.
6. Lifecycle engine sets the maturity schedule; Alert engine plans reminders; the dashboard updates.
Tech stack and why
Layer
Choice
Why this one
Frontend
Next.js + React, Tailwind, shadcn/ui, Recharts
Fast to build polished dashboards; good accessibility defaults
API
FastAPI (Python 3.11), Pydantic
Same language as the ML code; auto OpenAPI docs for judges
Auth
Keycloak
Roles, OTP, SSO-ready; production can link to government SSO
Jobs
Celery + Redis, Celery beat for schedules
Retries for OCR and bank calls; daily lifecycle scan
Database
PostgreSQL 16 + pgvector
Relational core plus vector search for the assistant in one place
Files
MinIO (S3-compatible), server-side encryption
Runs locally; same API as cloud object storage
Tamper evidence
immudb (stretch: Hyperledger Fabric)
Proofs out of the box; Docker up in minutes
OCR / doc AI
docTR or PaddleOCR + Hugging Face LayoutLMv3
Open source, CPU inference is acceptable
ML
scikit-learn, scikit-image, XGBoost, LightGBM, SHAP, alibi (Anchors), Optuna
Matches the papers' methods
Credentials
Ed25519 JSON signatures (stretch: ACA-Py)
Simple to show; standard-aligned path exists
Assistant
LangChain or LlamaIndex, local open LLM or API, ragas
Retrieval with citations; measured faithfulness
Reports
WeasyPrint (PDF), openpyxl (Excel)
Release letters and scheduled reports
DevOps
Docker Compose, GitHub Actions, pytest, Playwright
One-command demo; tests run on every push
Data model
Ten tables carry everything; five are core (institution, instrument, document, event, task) and the rest support trust, flags and policy. Every screen is a view over them.
The lifecycle engine allows only these transitions; a Rejected exit from Scrutiny and Archived after Released also exist but are left out of the picture. Overdue is the only state that triggers automatic escalation to the competent authority.
Core entities
Table
Key fields
Notes
institution
id, aicte_id, name, type, state, region, contact_user_id, required_deposit_amount
Imported from AICTE master data; region drives officer access
instrument
id, institution_id, kind (FDR / BG / DD / other), bank_ifsc, bank_name, instrument_no, amount, issue_date, maturity_date, auto_renew, lien_marked, beneficiary_text, status, trust_level, replaces_id, risk_score
unique(bank_ifsc, instrument_no) catches double pledges; replaces_id builds the renewal chain
field_value
instrument_id, field, declared_value, extracted_value, bank_value, confidence, trust_level
One row per field so the UI can badge each field separately
document
id, instrument_id, version, kind (scan / bank credential / release letter / evidence), sha256, storage_key, uploaded_by, uploaded_at, forgery_score
Files never overwritten
attestation
id, instrument_id, issuer (bank key id), payload_json, signature, verified_at, revoked_at
Bank credential and its revocation
flag
id, instrument_id, type, severity, reason_text, evidence_ref, status, raised_by, resolved_by
Rules, forgery, duplicate, AI risk
task
id, instrument_id, type (scrutiny / renewal / release / query), assignee_role, due_at, state, escalation_level
Drives alerts and SLAs
event (audit)
id, instrument_id, actor_id, role, action, before_json, after_json, reason, ts, prev_hash, hash
Append-only; hash-chained per instrument
anchor
id, batch_start, batch_end, merkle_root, immudb_tx, ts
Hourly anchoring receipts
policy_version
id, case_type, rules_json, valid_from
Release and renewal rules as data, versioned
Example bank credential (N2)
{
  "type": "FDRAttestation",
  "issuer": "bank:SBIN:key-2026-01",
  "issued_at": "2026-03-12T10:41:00+05:30",
  "subject": {
    "instrument_no": "FDR0045671234",
    "ifsc": "SBIN0001234",
    "amount_inr": 500000,
    "deposit_date": "2026-03-10",
    "maturity_date": "2031-03-10",
    "beneficiary": "AICTE, New Delhi (lien marked)",
    "lien_status": "MARKED"
  },
  "revocation": {"registry": "bank:SBIN:fdr-revocations", "index": 1187},
  "signature": "ed25519:..."
}
Illustrative values only. Depositor PAN, phone and account numbers are deliberately absent (data minimisation).
Module-by-module build specs
Eleven modules, each with an owner, an API surface and a definition of done; build them in the order listed, because each one feeds the next.
M1. Identity, roles and access (RBAC + ABAC)
• Keycloak for login, OTP and roles (institution, scrutiny officer, verifying officer, competent authority, auditor, admin, bank-service).
• Attribute rules on top of roles: a regional officer sees only their region; an institution sees only its own instruments; a bank service account can only post attestations for its own IFSC prefix.
• Every API call checks role + attribute in one middleware; denials are logged.
• Done when: a Postman suite proves 20 allow/deny cases.
M2. Intake and document management
• Upload API accepts PDF / JPG / PNG up to 10 MB; virus scan (ClamAV); SHA-256 computed on arrival; file stored encrypted in MinIO under a random key.
• Institution also types key fields (or accepts OCR suggestions) so we can compare declared vs extracted.
• Versioning: a re-upload creates a new version, never overwrites.
• Done when: upload → stored → hash shown → downloadable by authorised roles only.
M3. Extraction (OCR + LayoutLMv3)
1. Pre-process: deskew, denoise, 300 dpi render for PDFs.
2. OCR with docTR or PaddleOCR → words + bounding boxes.
3. LayoutLMv3 token classification → fields with confidence.
4. Post-process with rules: Indian amount formats ("Rs. 10,00,000/-"), amount in words vs digits cross-check, date normalisation, IFSC regex ^[A-Z]{4}0[A-Z0-9]{6}$.
5. Fields with confidence < 0.85 are highlighted for the user to confirm.
• Fallback if fine-tuning is late: OCR + regex + a small LLM prompt for key-value extraction.
• Done when: ≥ 90% field-level accuracy on 50 held-out synthetic FDRs, < 5 s per page on CPU.
M4. Discrepancy and forgery engine
• Rule checks (deterministic, explainable): amount ≥ required slab for the institution type; beneficiary name contains "AICTE" / required wording; maturity date after required validity; lien text present; declared vs OCR mismatch; IFSC valid and bank on the allowed list; duplicate key (IFSC + FDR no.) across the database (N8).
• Forgery signals: RGB-GLCM 9-feature vector per 10×10 block (paper), error-level analysis, PDF producer / modification-date metadata, font and stroke consistency around amount and date regions.
• Risk model: XGBoost over rule results + forgery signals → genuine / grey area / suspicious, with SHAP values and Anchor rules as the reason text (16.pdf).
• Done when: each flag in the UI shows a reason sentence and the evidence crop.
M5. Bank verification gateway
• Adapter interface verify(instrument) → Attestation | Pending | Rejected with three implementations:
    1. Signed credential (demo default): mock bank issues a JSON credential signed with Ed25519 (or via ACA-Py); we verify signature and compare every field.
    2. Bank API simulator: REST endpoint that answers "exists / amount / maturity / lien / closed".
    3. Manual letter: officer uploads the bank's reply; tracked with an SLA timer.
• Result raises the Trust Ladder level (N1) and is written to the audit log.
• A periodic job re-checks L3 instruments for L4 "live" status.
• Done when: a tampered amount in the uploaded scan is caught because it disagrees with the bank credential.
M6. Ledger anchoring and verifiable audit
• Every state change writes an audit event: {id, instrument_id, actor, role, action, before, after, reason, ts, prev_hash, hash}.
• Hash chain per instrument (hash = SHA256(prev_hash ∥ canonical_json(event))).
• Hourly batch: Merkle root of new events + document hashes written to immudb (stretch: Hyperledger Fabric chaincode).
• Public verifier page: drop a file → "submitted on <date> by <institution>, unchanged" or "no match".
• Done when: editing a row directly in PostgreSQL is detected by the verifier.
M7. Lifecycle engine
• Explicit state machine (see Data model) implemented with a transitions table; illegal transitions are rejected.
• Scheduler (Celery beat or APScheduler) runs daily: computes days to maturity, moves instruments to Expiring / Matured / Overdue, opens renewal tasks.
• Renewal links the new instrument to the old one (replaces_id), so history is a chain.
• Done when: fast-forwarding the clock in the demo moves an FDR through Active → Expiring → Renewal requested → Renewed.
M8. Alerts and escalation
• Configurable rules per case type: reminders at T-90, T-60, T-30, T-7 days; escalation to the next role if a task is untouched for N days.
• Channels: in-app, email (SMTP / SendGrid sandbox), SMS (stubbed; mention NIC SMS gateway as production path).
• Predicted-risk escalation (N3): if risk > 0.7, escalate at T-30 instead of waiting for T-7.
• Digest mode for officers: one daily email, not 50.
• Done when: every alert sent is listed on the instrument's timeline.
M9. Release / refund workflow
• Request form → auto-built checklist from the policy version (N4) → evidence upload → scrutiny → competent-authority approval with mandatory reason → system generates a release letter PDF to the bank → bank confirms lien removal (credential revocation in M5) → instrument Released.
• Time boxes: if the institution does not respond to a query in X days, the request auto-closes with notice; if an officer does not act in Y days, it escalates.
• Done when: a release cannot be approved while any checklist item is red.
M10. Dashboard, search and reports
• Tiles: active, expiring in 30/60/90 days, matured, renewed, released, pending verification, flagged.
• Views: Trust Ladder distribution, ageing of pending cases, risk heatmap by region and institution type, bank-wise verification turnaround.
• Global search by institution, AICTE ID, FDR number, bank, amount range.
• Scheduled reports as PDF and Excel; one-click "pending interventions" list.
• Done when: every number on the dashboard drills down to the instruments behind it.
M11. Officer assistant (stretch, high wow)
• Ingest the Approval Process Handbook and circulars (PDF) → chunk by clause → embeddings (bge-small or similar) → pgvector.
• Ask: "Can institution X get its FDR released?" → the assistant pulls the instrument's facts from the database plus the relevant clauses and answers with citations.
• Evaluate with ragas on 40 hand-written questions; show faithfulness on a slide.
• Guardrail: the assistant never changes state; it only drafts notes.
ML and AI details
Real FDR scans are confidential, so we generate a labelled synthetic dataset first and validate on a small set of real, redacted FDRs from our own college's accounts office if they agree.
Datasets
Dataset
Size target
How we get it
Used by
Synthetic FDR images
2,000 pages, 8 bank templates
HTML/CSS templates of FDR receipts rendered with random but valid values (Faker-IN, real IFSC format), printed-scan effects with Augraphy (blur, noise, skew, stamps, folds)
LayoutLMv3 fine-tune
Real redacted FDRs
20–50 pages
College accounts office, with written permission, personal data blacked out
Final validation only
Forgery set
2,000 genuine + 2,000 forged regions
Apply the 2022 paper's 10 classes to amount, date and name fields: copy-paste, insertion, noise, blur and combinations
Forgery classifier
Public document sets
—
FUNSD and CORD for pre-fine-tuning sanity checks; DocTamper-style tampered-text data if licence allows
Baselines
Synthetic event logs
300 institutions × 5 years
Simulator with institution "personas" (punctual, slow, chronic late, fraud-prone) generating submit / query / respond / renew / release events
Renewal-risk model
Regulation corpus
Handbook + circulars
Public AICTE PDFs
Assistant
Assistant eval set
40 Q&A pairs
Written by the team from the handbook
RAGAS
Models
Field extraction. microsoft/layoutlmv3-base, token classification, BIO labels for 10 fields. Train 1,000–2,000 steps, learning rate 1e-5 to 5e-5, batch 8–16 (paper used 1e-5 / 16 on FUNSD). One free GPU (Colab or Kaggle T4) is enough. Metric: entity-level F1 per field, plus field exact-match after post-processing.
Forgery. Baseline = paper's 9 RGB-GLCM features + SVM (scikit-image graycomatrix, graycoprops). Upgrade = add error-level-analysis statistics and a small CNN on 64×64 crops. Metric: per-class precision / recall and, more important for officers, the false-alarm rate on genuine documents.
Discrepancy risk. XGBoost on ~25 features (rule outcomes, forgery score, OCR confidence, declared-vs-OCR distance, bank-attestation status, institution history). Class imbalance handled with SHAP-based instance weights as in 16.pdf, hyperparameters with Optuna. Outputs three classes with Anchor rules as explanations. Metric: recall on suspicious (target ≥ 0.95), precision on suspicious, size of grey area.
Renewal risk (N3). Prefix-based features from the event log: days since last action, past lateness count, median response time, open discrepancies, days to maturity, bank, amount. Two models, per the 2023 benchmark's advice: (a) LightGBM classifier for P(miss deadline); (b) direct remaining-time regressor (not recursive suffix prediction). Optional LSTM over event sequences as a research comparison. Metrics: AUC, lead time gained (days of warning before a miss), MAE on remaining time.
Assistant. Small open LLM served locally (or an API in the demo) + pgvector retrieval + citation formatting. Metrics: RAGAS faithfulness, answer relevance, context relevance.
What we report to judges
Metric
Target
Field extraction F1 (synthetic test)
≥ 0.90
Field exact-match after rules
≥ 95% on amount and dates
Forgery recall on tampered amount / date
≥ 0.90
False alarm rate on genuine scans
≤ 5%
Renewal-risk AUC
≥ 0.80 on simulator data
Average warning lead time
≥ 21 days
RAGAS faithfulness
≥ 0.85
All synthetic-data numbers must be labelled as synthetic on slides.
Security, privacy and compliance
We organise security under the SSI survey's five pillars (authentication, integrity, privacy, trust, simplicity) so the slide maps to a published framework, and we keep all personal and financial data on Indian infrastructure.
Pillar
Controls in FDR Guardian
Authentication
Keycloak with OTP / MFA for officers; short-lived JWTs; bank services use mutual TLS + signed requests; no shared accounts
Integrity
SHA-256 of every file at upload; hash-chained audit events; hourly Merkle root in immudb; bank credentials verified by signature; database edits outside the API detected by the verifier
Privacy
Encryption at rest (MinIO SSE, PostgreSQL column encryption for account-like fields); TLS 1.3 in transit; field-level masking (show last 4 digits of FDR number to roles that don't need all); data minimisation in bank credentials (no depositor PAN or phone)
Trust
Trust Ladder levels per field; every officer action needs a reason; competent-authority overrides are flagged on the dashboard
Simplicity
Institution flow is three screens: upload, confirm fields, submit; officers get one daily digest instead of many emails
Compliance points to mention
• Digital Personal Data Protection Act, 2023: consent and purpose limitation for institution contact persons' data; a retention schedule; a named grievance contact.
• IT Act, 2000 and e-sign: release letters can be e-signed by the competent authority (Aadhaar e-Sign or DSC) in production.
• Government hosting: production deployment on NIC / MeghRaj cloud; CERT-In incident reporting; GIGW accessibility guidelines for the UI.
• Bank integration: only through formally authorised channels (bank API agreement, SFMS-style advice, or Account Aggregator with consent). The prototype never logs into bank portals or scrapes them.
Threats we test against
Threat
Defence
Edited scan (amount or date changed)
Forgery score + mismatch with bank credential
Same FDR pledged twice
Global duplicate key check (N8)
FDR closed early after submission
Periodic live re-check (L4) and lien status in credential
Insider edits a record quietly
Hash chain + Merkle anchor; verifier shows break
Fake bank credential
Signature check against a pinned bank public-key registry
Prompt injection into the assistant via uploaded PDFs
Assistant reads only the curated regulation corpus and structured DB fields, never raw uploads; it cannot change state
Team, timeline and repository
Eight weeks, five sprints, six people, with one hard gate: the core lifecycle must run end to end by the end of week 5 before anyone spends time on stretch AI.
Weeks are counted from your kickoff; shift the plan to match your college's internal hackathon and the SIH submission deadline once dates are announced.
Team split (6 members)
Role
Owns
Also helps with
Team lead / backend
M1 auth, M7 lifecycle, M9 release, API design
Demo script, judge Q&A
Backend 2
M2 intake, M5 bank gateway + mock bank, M6 audit + immudb
DevOps, Docker, CI
Frontend
Institution portal, officer console, verifier page
UX, accessibility
Frontend + data viz
M10 dashboard, reports, Trust Ladder badges
PPT visuals
ML 1
M3 extraction (OCR + LayoutLMv3), synthetic FDR generator
Dataset documentation
ML 2
M4 forgery + risk model, N3 renewal-risk model, M11 assistant + ragas
Metrics slide
Definition of done per sprint
[ ] Sprint 0: repo and CI green; 200 synthetic FDRs rendered; one interview with an accounts or AICTE official; Figma wireframes for 8 screens.
[ ] Sprint 1: login with 6 roles; upload stores file + hash; instrument CRUD; state machine with tests for every transition.
[ ] Sprint 2: OCR auto-fill on upload; rule flags with reasons; reminders at T-90/60/30/7; dashboard tiles drill down. Gate: full story from upload to maturity reminder works.
[ ] Sprint 3: signed bank credential + Trust Ladder L3; hash chain + immudb anchoring + verifier page; release workflow with checklist and PDF letter; forgery baseline. Gate: feature freeze.
[ ] Sprint 4: renewal-risk model with reasons; assistant with RAGAS score; manual-vs-portal timing runs; three full demo rehearsals, one with a recorded backup video.
Repository layout
fdr-guardian/
  apps/
    web/                 # Next.js: institution, officer, auditor UIs
    api/                 # FastAPI app
      modules/
        auth/  intake/  extraction/  checks/  bank/
        audit/  lifecycle/  alerts/  release/  reports/  assistant/
      workers/           # Celery tasks and beat schedules
  ml/
    synth/               # FDR template renderer + Augraphy pipeline
    layoutlm/            # fine-tune and inference
    forgery/             # GLCM features, SVM / XGBoost
    risk/                # event-log simulator, LightGBM, SHAP, Anchors
    rag/                 # ingestion, retrieval, ragas eval
  services/
    mock-bank/           # issuer that signs FDR credentials
  infra/
    docker-compose.yml   # postgres, minio, redis, immudb, keycloak
  docs/                  # this plan, ADRs, API spec, dataset cards
  tests/                 # pytest + Playwright, SIH scenario suite
Demo script, test scenarios and KPIs
The demo is a 6-minute story of one institution, covering every testing scenario SIH lists, followed by the dashboard and the numbers.
6-minute demo story
1. 0:00 New submission. "ABC Institute" uploads a scanned FDR. Fields auto-fill in about 3 seconds; one low-confidence field is highlighted; the user confirms. Badge: L1 Machine-checked.
2. 0:45 Bank attestation. Mock bank issues its signed credential. Badge jumps to L3 Bank-attested in green.
3. 1:30 Discrepancy. Second institution uploads an FDR whose amount was edited from 5,00,000 to 15,00,000. Forgery score: suspicious; the bank credential says 5,00,000; the system shows both side by side with the reason sentence.
4. 2:15 Double pledge. Third upload reuses ABC's FDR number. Duplicate flag fires instantly.
5. 2:45 Approaching maturity. Time-travel control moves the clock forward 300 days. ABC's FDR turns amber; reminders appear on the timeline; the risk model marks it high risk with a reason, so escalation happens at T-30.
6. 3:30 Renewal. Renewed FDR uploaded and attested; the chain shows old → new.
7. 4:15 Release. Release request; checklist ticks as evidence arrives; competent authority approves; release letter PDF generated; bank revokes the credential; status Released.
8. 5:00 Audit proof. Auditor drags the original scan into the verifier: "submitted on …, unchanged". Then we edit a database row live; the verifier shows the chain break.
9. 5:30 Assistant + dashboard. Officer asks the assistant about release eligibility and gets a cited answer; dashboard tiles and heatmap close the demo.
SIH testing scenarios → our test cases
SIH scenario
Automated test
Pass condition
New FDR submission
Upload 50 synthetic FDRs via API
All stored, hashed, fields extracted, L1 reached when clean
Validity tracking
Scheduler run over seeded dates
Every instrument in the correct status bucket
Approaching maturity
Clock set to T-90, T-60, T-30, T-7
Exactly one reminder per threshold, no duplicates
Renewal
Renew 10 instruments
Old and new linked; old marked Renewed; history intact
Discrepancy identification
30 tampered + 30 clean uploads
Tampered recall ≥ 0.90; false alarms ≤ 5%
Authorised release
Release with one checklist item missing, then complete
Blocked first, approved second; lien revoked; audit entries present
Access control
20 allow/deny cases
All pass
Audit integrity
Direct DB edit
Verifier reports break
KPIs for "measurable improvement"
The problem statement asks for measured gains in five areas; we time a manual baseline (a teammate doing the task with spreadsheet + email) against the portal on the same 20 cases.
SIH KPI
How we measure
Expected result to show
Record accuracy
Field errors per 100 FDRs, manual typing vs OCR + confirm
Fewer errors with portal
Verification turnaround
Time from upload to L3
Seconds (simulated bank) vs days (letter)
Timely renewal monitoring
% of maturities with a reminder sent ≥ 30 days ahead
100% vs ad hoc
Manual tracking effort
Minutes per case per month
Large reduction, measured on 20 cases
Visibility into pending cases
Time to answer "which cases need action today?"
One click vs spreadsheet search
Use the timed results, not guesses, on the final slide.
Risks, judge Q&A and references
The biggest risk is over-building the ML and under-building the workflow; the core lifecycle must be demo-ready before any stretch model is touched.
Risks and fallbacks
Risk
Likelihood
Fallback
LayoutLMv3 fine-tune underperforms
Medium
OCR + regex + LLM key-value extraction; keep user confirmation step
No real FDR samples
High
Synthetic set with Augraphy; say so openly; ask college accounts office early
Ledger setup eats time
Medium
immudb only (Docker, minutes); Fabric only as slide
Bank integration questioned as unrealistic
High
Show NeSL e-BG / SFMS / Account Aggregator as existing precedents; prototype uses simulators
Assistant hallucinates on stage
Medium
Pre-tested question list; RAGAS score shown; assistant cannot change state
Scope creep
High
Freeze features at end of Sprint 3; anything new goes to a "Future scope" slide
Likely judge questions
• "Why blockchain? Isn't a database enough?" We do not need a cryptocurrency. We need tamper evidence an auditor can verify without trusting our admins. immudb / Merkle anchoring gives that cheaply; a permissioned ledger like Fabric is the production path if AICTE wants banks to co-sign.
• "Will banks really sign credentials?" They already exchange signed BG advice over SFMS and issue e-BGs on NeSL; we propose the same for FDRs, and the Account Aggregator rails already carry term-deposit data with consent.
• "How accurate is your forgery detection?" Give the measured recall and false-alarm rate on our synthetic set, and stress that the bank cross-check, not the image model, is the final word.
• "What if the AI is wrong?" Every AI output is a suggestion with a reason; a named officer makes every decision, and that decision is logged.
• "How does it integrate with AICTE's portal?" Institution IDs and approval case IDs are foreign keys; an adapter can pull institution master data via API or CSV import.
• "Cost to run?" Fully open-source stack; runs on a single 8-core, 32 GB VM for thousands of institutions; GPU needed only for training.
References
Papers you uploaded:
1. Ahmadisheykhsarmast, S., Sonmez, R. (2020). A smart contract system for security of payment of construction contracts. Automation in Construction, 120, 103401. https://doi.org/10.1016/j.autcon.2020.103401
2. Elloh Adja, Y. C., Hammi, B., Serhrouchni, A., Zeadally, S. (2021). A blockchain-based certificate revocation management and status verification system. Computers & Security, 104, 102209. https://doi.org/10.1016/j.cose.2021.102209
3. Huang, Y., Lv, T., Cui, L., Lu, Y., Wei, F. (2022). LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking. ACM MM '22. https://doi.org/10.1145/3503161.3548112
4. Gornale, S. S., Patil, G., Benne, R. (2022). Document Image Forgery Detection Using RGB Color Channel. TMLAI, 10(5). https://doi.org/10.14738/tmlai.105.13126
5. Rama-Maneiro, E., Vidal, J. C., Lama, M. (2023). Deep Learning for Predictive Business Process Monitoring: Review and Benchmark. IEEE TSC. https://doi.org/10.1109/TSC.2021.3139807
6. Thanathamathee, P., Sawangarreerak, S., Chantamunee, S., Mohd Nizam, D. N. (2024). SHAP-Instance Weighted and Anchor Explainable AI: Enhancing XGBoost for Financial Fraud Detection. Emerging Science Journal, 8(6). https://doi.org/10.28991/esj-2024-08-06-016
7. Ahmed, M. R., Islam, A. K. M. M., Shatabda, S., Islam, S. (2022). Blockchain-Based Identity Management System and Self-Sovereign Identity Ecosystem: A Comprehensive Survey. IEEE Access. https://doi.org/10.1109/ACCESS.2022.3216643
8. Es, S., James, J., Espinosa-Anke, L., Schockaert, S. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. EACL 2024 System Demonstrations, 150–158. https://aclanthology.org/2024.eacl-demo.16
Open-source projects and Indian systems are linked in the "Existing solutions" section; verify those links in a browser before final submission.
