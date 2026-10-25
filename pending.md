# pending.md: what is left, and how the models measure up

State on `main` as of 24 Oct 2026, after PR #12. The prototype deadline is before 28 Oct 2026.
The numbers below come from [README.md → Expected outcomes](README.md#expected-outcomes) and [CONTEXT.md](CONTEXT.md). Nothing here is estimated.

> **Rule change (25 Oct 2026):** a labelled synthetic FDR dataset is now allowed; see section 3. The results below predate it.
>
> **Every model result is a proxy.** No public FDR dataset exists, so each model was measured on the closest open dataset. A result shows how the method performs on that dataset, not on FDRs. FDR-level numbers need labelled real FDRs. Earlier results measured on synthetic data were withdrawn on 23 Oct 2026.

## 1. Model metrics against targets

"Reached?" compares the measured value with the plan's target. **Not measured** means no result exists yet. **No target** means the plan sets none for that metric.

### Field extraction (M3): RapidOCR + rules (pass B), LayoutLMv3 (pass A)

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| Field exact-match after rules, overall | ≥ 90% | — | — | **Not measured**: needs labelled real FDRs |
| Exact-match on amount and dates | ≥ 95% | — | — | **Not measured**: needs labelled real FDRs |
| Processing time per page (CPU) | < 5 s | — | — | **Not measured**: to be timed on real scans |
| LayoutLMv3 entity F1 | No target | **0.906** (answer 0.928, question 0.917, header 0.649) | FUNSD test split, 50 forms (proxy) | **No target**. The LayoutLMv3 paper reports 90.29 on FUNSD; ours is close but slightly optimistic, because the best checkpoint was picked on the test split. To be re-run with the merged protocol (fixed 1,000 steps, one evaluation) |

Pass A stays **off** live (`pass_a_enabled: false`), and the API refuses a model whose labels are not FDR fields.

### Forgery signals (N6): RGB-GLCM + ELA + ink + copy-move features, SVM

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| Recall on tampered pages | ≥ 0.90 | **0.114** | Find it again! test split, 218 receipts (35 forged), proxy | **No**: far below target, close to chance |
| False-alarm rate on genuine scans | ≤ 5% | **6.6%** | Same split | **No**: above the limit |
| Page-level AUC | No target | **0.534** | Same split | **No target**. Close to 0.5, which is chance |

The texture and ELA features miss these hand-made edits. The retrain is on the branch `forgery-model-on-find-it-again`, **not merged and not live**.

### Renewal risk (N9): LightGBM + SHAP reasons

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| AUC | ≥ 0.80 | **0.789** pooled | BPI Challenge 2017, 6,197 later applications held out by time (proxy) | **No**: 0.011 short of target |
| AUC by week since the offer | No target | 0.588 / 0.599 / 0.640 / 0.691 / 0.833 | Same | **No target**. Early-week warning is weak; only week 5 clears 0.80 |
| Baseline AUC (one feature: days since last event) | No target | 0.767 pooled | Same | **No target**. The model beats this baseline by 0.022 |
| Mean warning lead time | ≥ 21 days | **14.1 days** mean, 16.5 median | Same | **No**. The proxy's deadline is only about 30 days after the offer, which caps the lead time |
| Missed deadlines caught | No target | 99.8% at 12.0% false alarms | Same | **No target** |
| Days-to-deadline error (MAE) | No target | 6.70 days | Same | **No target** |

Live scoring is **off**: the API loads a model only if its `meta.json` has `"live_scoring": true`. It stays off until DepositTrack has its own renewal history.

### Components not built

| Component | Metric | Target | Reached? |
| --- | --- | --- | --- |
| Discrepancy risk (XGBoost) | Recall on the suspicious class | ≥ 0.95 | **Not built**: the prototype uses explained rule flags plus the forgery bands instead |
| Officer assistant (RAG) | RAGAS faithfulness | ≥ 0.85 | **Not built**: skipped for the prototype by decision |

### Non-model target that is met

| Component | Metric | Target | Measured | Reached? |
| --- | --- | --- | --- | --- |
| Access control | Allow/deny test cases passing | 100% of ≥ 20 cases | 100% of 28 role cases, plus scoping tests for institution, region, bank and mixed roles; 412 API tests pass, ruff clean | **Yes** |

### Summary

- **Reached:** 1 target (access control).
- **Missed:** 5 targets.
  - Forgery recall: 0.114 against ≥ 0.90.
  - Forgery false alarms: 6.6% against ≤ 5%.
  - Renewal-risk AUC: 0.789 against ≥ 0.80.
  - Renewal-risk lead time: 14.1 days against ≥ 21 days.
  - Field extraction: both accuracy targets and the speed target are unmeasured, so they are not reached yet.
- **Not built:** 2 (discrepancy risk, officer assistant).

## 2. PS improvement areas: baseline vs portal (all pending)

No baseline or portal numbers exist yet. Each needs manual-vs-portal timing runs on the same cases.

| PS improvement area | How it will be measured | Baseline | Result | Status |
| --- | --- | --- | --- | --- |
| Record accuracy | Field errors per 100 instruments | — | — | Pending |
| Verification turnaround time | Time from submission to bank-attested | — | — | Pending |
| Timely renewal monitoring | % of maturities with reminders ≥ 30 days ahead; coverage gaps forecast before they occur | — | — | Pending |
| Manual tracking effort | Officer minutes per case per month | — | — | Pending |
| Visibility into pending cases | Time to answer "which cases need action today?" | — | — | Pending |

## 3. Pending work, in order

### Check on 25 Oct 2026 and the new data rule

Checked on a fresh clone of `main` (macOS, Python 3.11, Node 22):

- API: **412 passed**, ruff clean. Run as `python -m pytest`; a bare `pytest` fails to import `tests.flow_support`.
- Mock bank: **48 passed**. `ml/tests`: **18 passed**, but only with the `data` extra installed (`pip install -e "apps/api[data,ml]"`); without it one test fails on `kagglehub`.
- Web: ESLint, `tsc --noEmit` and `next build` pass.
- Confirmed in code: `GET /institutions` still uses `len(roles) == 1` (`apps/api/app/api/admin.py`); the web app shows none of `store_error`, `receipt` or `immudb_problem`; there is no `.github/`.
- Not on GitHub: the branches `forgery-model-on-find-it-again` and `main-local-with-ci`, and `../retired-synthetic-models/`, exist only on the maintainer's machine.
- **Gap not listed above:** `ml/forgery/train.py` on `main` still trains on FDRs from the removed `ml/synth` generator (`fdrsynth`), so it cannot run on `main`.

**New rule (25 Oct 2026, AGENTS.md rule 5):** a labelled synthetic dataset is allowed for FDR documents. This changes items 1, 2 and 4 below:

- **1 → generate synthetic FDRs.** Bring back the generator from history (`git show a6e1efc~1:ml/synth`) as `ml/synthetic_fdr/`. Use real banks and IFSCs from the master data, add a `SYNTHETIC - NOT A REAL DEPOSIT` mark and tampered variants. Then walk upload → extraction → bank verification with a generated FDR. A real scan is still wanted for final validation.
- **2 → retrain the forgery signal on synthetic tampered FDRs** (`ml/forgery/train.py` + `tamper.py` already expect this) and report the result as synthetic.
- **4 → measure field extraction on synthetic FDRs** (exact-match overall, on amount and dates, seconds per page). Report the numbers as synthetic, and keep the real-FDR row open.

The original list follows.

1. **Real FDR scan (manual, maintainer).** Provide one with the owner's consent and personal details redacted. It is needed to walk the upload → extraction → bank verification story on the live stack. Record the same FDR on the mock bank's operator page before "Verify with bank". Until then, any real document with typed values tests everything except extraction accuracy.
2. **Forgery signal: decision needed.** The Find it again! result is near chance. The options are other features or methods, or keeping the signal off and relying on the bank cross-check.
3. **Re-run the LayoutLMv3 notebook (manual, free Colab T4)** with the merged protocol, then record the score in README.
4. **Measure field extraction on labelled real FDRs:** exact-match overall, on amount and dates, and seconds per page.
5. **Demo story walk-through** (plan §12) on the live stack. Restart the API, mock bank and web first; they were stopped because memory was low. Run taste-skill `inspect.mjs --app` on every screen (1440/768/390) and fix the FAILs. Show PR #7's anchor fields (`store_error`, `receipt`, `immudb_problem`) in the admin and audit screens.
6. **Manual-vs-portal timing runs** for section 2, then fill in the Expected outcomes table.
7. **Recorded backup demo video.**
8. **CI workflow (manual permission first).** Run `gh auth refresh -h github.com -s workflow` in PowerShell; after that the workflow can be added. The old file is on the local branch `main-local-with-ci`.
9. **Hindi translations:** `apps/web/src/i18n/hi.json` was written by Claude and needs a fluent reviewer.
10. **Idea submission** for the PS deadline (on hold).

### Small follow-ups from the PR #12 review

- `GET /institutions` (`apps/api/app/api/admin.py`) still scopes by `len(roles) == 1` and region instead of the action-aware rule. It serves public master data, so it is low risk.
- In the instrument detail, `next_states` and `editable_fields` are UI hints computed from all of the caller's roles, so they can offer a move that the endpoint then refuses. The endpoints themselves enforce the role scope.
- `CONTEXT.md` still lists #11 and #12 as open PRs, and README "Work to be done" still lists PR #12. Both are merged.

### Unfinished test scenarios and gates

- **T-05:** the forgery part (recall ≥ 0.90, false alarms ≤ 5%) is not met; see section 1.
- **T-06:** the missing-documents report endpoint is built but not separately tested.
- **T-11:** drill-down clicks have not been walked in the browser.
- **Phase 2 gate:** the full story from upload to maturity reminder passes in API tests; on the live stack it waits for a real FDR scan.
- **Phase 3 gate:** feature freeze, not declared yet.

## 4. Open questions for AICTE (not assumed)

From [plan §14](IMPLEMENTATION_PLAN.md#14-open-questions-for-aicte-not-assumed). Each stays configurable, with `null` in `policy.example.yaml`, until an AICTE or institution accounts official answers it.

1. Required deposit / FDR amounts and durations by institution type and approval case, with the governing handbook clauses.
2. In whose name the FDR is made out, and the exact beneficiary/lien wording.
3. Accepted instrument kinds (FDR only, or also security deposit by transfer, bank guarantee, DD).
4. Conditions for release, discharge and refund, and the competent authority at each level.
5. Reminder thresholds and the escalation chain.
6. Whether bank attestation is required before *Active*, or officer verification (L2) is enough when no bank channel exists.
7. AICTE systems and APIs available for integration, and how integration is authorised.
8. Which banks hold most AICTE FDRs, and whether any already offer a verification API or signed confirmations.
9. Record retention period and RTI/audit access requirements.
10. Hosting requirements (NIC / MeghRaj or other) and any mandated SSO.
11. The mapping from each state to its AICTE regional office.
