# pending.md: what is left, and how the models measure up

State on `main` as of 24 Oct 2026, after PR #12, plus the T-06 work in PR #18 (26 Oct). The prototype deadline is before 28 Oct 2026.
The numbers below come from [README.md → Expected outcomes](README.md#expected-outcomes) and [CONTEXT.md](CONTEXT.md). Nothing here is estimated.

> **Rule change (25 Oct 2026):** a labelled synthetic FDR dataset is now allowed; see section 3. The results below predate it.
>
> **Every model result is a proxy.** No public FDR dataset exists, so each model was measured on the closest open dataset. A result shows how the method performs on that dataset, not on FDRs. FDR-level numbers need labelled real FDRs. Earlier results measured on synthetic data were withdrawn on 23 Oct 2026.

## 1. Model metrics against targets

"Reached?" compares the measured value with the plan's target. **Not measured** means no result exists yet. **No target** means the plan sets none for that metric.

### Field extraction (M3): RapidOCR + rules (pass B), LayoutLMv3 (pass A)

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| Field exact-match after rules, overall | ≥ 90% | **99.4%** | 300 synthetic FDRs (seed 2027) | **Yes, on synthetic** (upper bound: known captions). Real FDRs: not measured |
| Exact-match on amount and dates | ≥ 95% | **99.3%** | Same | **Yes, on synthetic**. Real FDRs: not measured |
| Processing time per page (CPU) | < 5 s | **0.66 s** mean, 0.75 s p95 | Same | **Yes, on synthetic**. To be timed on real scans |
| LayoutLMv3 entity F1 | No target | **0.906** (answer 0.928, question 0.917, header 0.649) | FUNSD test split, 50 forms (proxy) | **No target**. The LayoutLMv3 paper reports 90.29 on FUNSD; ours is close but slightly optimistic, because the best checkpoint was picked on the test split. To be re-run with the merged protocol (fixed 1,000 steps, one evaluation) |

Pass A stays **off** live (`pass_a_enabled: false`), and the API refuses a model whose labels are not FDR fields.

### Forgery signals (N6): RGB-GLCM + ELA + ink + copy-move features, SVM

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| Recall on tampered pages | ≥ 0.90 | **0.114** | Find it again! test split, 218 receipts (35 forged), proxy | **No**: far below target, close to chance |
| False-alarm rate on genuine scans | ≤ 5% | **6.6%** | Same split | **No**: above the limit |
| Page-level AUC | No target | **0.534** | Same split | **No target**. Close to 0.5, which is chance |

The texture and ELA features miss these hand-made edits. The retrain is not committed yet (uncommitted edits in the maintainer's worktree; see section 3), and **not live**.

**Retrained on synthetic FDRs (26 Oct 2026):** 600 generated FDRs, half of them tampered by `ml/forgery/tamper.py` (copy-paste, insertion, noise, blur and combinations). Train 330 / validation 90 (sets the bands) / test 180 (reported).

| Metric | Target | Measured | Dataset | Reached? |
| --- | --- | --- | --- | --- |
| Recall on tampered pages | ≥ 0.90 | **0.67** | 180 synthetic FDRs (held out, 95 tampered) | **No**. By edit: blur 0.89, copy+blur 0.93, insert+blur 0.92, noise 0.72, insertion 0.67, insert+noise 0.57, copy-paste **0.08** |
| False-alarm rate on genuine scans | ≤ 5% | **5.9%** | Same | **No**, just above. The bands are set on a separate validation split, so this is not tuned on the test pages |

Better than the receipt proxy (0.114), but below target, and a synthetic result. Live stays **off**: the API refuses a forgery model unless its `meta.json` has `"live_scoring": true`, a training-data name and both bands. The bands now come from a separate validation split (review of PR #16). Next idea, if wanted: a copy-move detector that compares patches across the page (copy-paste is the miss).

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
| Access control | Allow/deny test cases passing | 100% of ≥ 20 cases | 100% of 28 role cases, plus scoping tests for institution, region, bank and mixed roles; 464 API tests pass, ruff clean | **Yes** |

### Summary

- **Reached:** 1 target (access control).
- **Missed:** 5 targets.
  - Forgery recall: 0.114 against ≥ 0.90 (proxy); 0.67 on synthetic FDRs.
  - Forgery false alarms: 6.6% against ≤ 5% (proxy); 5.9% on synthetic FDRs.
  - Renewal-risk AUC: 0.789 against ≥ 0.80.
  - Renewal-risk lead time: 14.1 days against ≥ 21 days.
  - Field extraction: met on synthetic FDRs only (99.4%, 99.3% on amount and dates, 0.66 s/page), not measured on real FDRs, so it stays counted as missed.
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

- API: **412 passed**, ruff clean. A bare `pytest` failed to import `tests.flow_support` (`apps/api/tests/` has no `__init__.py`); `pythonpath = ["."]` in `apps/api/pyproject.toml` now fixes that.
- Mock bank: **48 passed**. `ml/tests`: **18 passed**, but only with the `data` extra installed (`pip install -e "apps/api[data,ml]"`); without it one test fails on `kagglehub`.
- Web: ESLint, `tsc --noEmit` and `next build` pass.
- Confirmed in code: `GET /institutions` still uses `len(roles) == 1` (`apps/api/app/api/admin.py`); the web app shows none of `store_error`, `receipt` or `immudb_problem`; there is no `.github/`.
- Not on GitHub: the branch `main-local-with-ci` and `../retired-synthetic-models/` exist only on the maintainer's machine. The branch `forgery-model-on-find-it-again` has no commits beyond `main` (its tip `0e38de0` is an ancestor of `main`): the Find it again! retrain behind the 0.114 / 6.6% / 0.534 numbers exists only as **uncommitted edits in the maintainer's `../wt-forgery` worktree**. Those edits also delete `ml/forgery/tamper.py`, which item 2 still needs. **Maintainer:** commit them to that branch, keeping `tamper.py`, before removing or resetting that worktree.
- **Gap not listed above:** `ml/forgery/train.py` on `main` still trains on FDRs from the removed `ml/synth` generator (`fdrsynth`), so it cannot run on `main`. PR #14 brings the generator back as `ml/synthetic_fdr/` and points `train.py` at it.

The 25 Oct rule (AGENTS.md rule 5) allows a labelled synthetic dataset for FDR documents, so items 1, 2, 4 and 5 below now use generated FDRs. A real scan is still wanted for final validation.

1. ~~**Generate synthetic FDRs**~~ — done in PR #14 (the walk itself is item 5). The AICTE dashboard was unreachable from this network, so the runs so far used the 3-institution excerpt in the test fixtures; re-run `fetch-institutions` from a network that reaches AICTE. Restore the generator from history (`git checkout a6e1efc~1 -- ml/synth && git mv ml/synth ml/synthetic_fdr`). Then:
   - replace its fictional banks, IFSCs and institutions with ones from the imported master data;
   - replace its `SYNTHETIC SAMPLE - NOT A REAL INSTRUMENT` mark with `SYNTHETIC - NOT A REAL DEPOSIT`, and register the new mark in `apps/api/config/extraction.yaml` (`ignore_lines_containing: ["NOT A REAL DEPOSIT"]`, plus `ignore_lines_equal` entries for fragments OCR reads alone, such as `SYNTHETIC`), so it is not read as the bank or scored as a text region;
   - write PNG pages only (the app cannot read a PDF), clean pages only (tampered copies are made by `ml/forgery/train.py`), and default the output to the repo-root `data/synthetic_fdr/`.
   - **Real scan (manual, maintainer), for final validation:** one FDR with the owner's consent and personal details redacted. Record the same FDR on the mock bank's operator page before "Verify with bank".
2. **Retrain the forgery signal on synthetic FDRs.** `ml/forgery/train.py` takes clean generated pages and tampers half of them with `tamper.py`; update its docstring to the new generator paths. Report the result as synthetic. Add the forgery loader's approval gate first (`"live_scoring": true` and `"training_data"` in `meta.json`); until then, write the output outside `models/`. If it still misses the targets, the options are other features or methods, or keeping the signal off and relying on the bank cross-check.
3. **Re-run the LayoutLMv3 notebook (manual, free Colab T4)** with the merged protocol, then record the score in README.
4. ~~**Measure field extraction on synthetic FDRs**~~ — done in PR #15 (section 1): 99.4% overall, 99.3% on amount and dates, 0.66 s/page, synthetic. Keep the real-FDR row open until labelled real FDRs exist.
   - **Pass A on synthetic FDRs: out of scope for the prototype.** The FDR LayoutLMv3 notebook was removed in `a309ab7` and is not restored. A synthetic-trained pass A could go live only with the maintainer's approval, recorded as `"live_extraction": true` and a `"training_data"` name in its `metrics.json` (the loader now checks both).
5. **Demo story walk-through** (plan §12) on the live stack, with generated FDRs, on a demo database that is reset afterwards. Restart the API, mock bank and web first; they were stopped because memory was low. Run taste-skill `inspect.mjs --app` on every screen (1440/768/390) and fix the FAILs. Show PR #7's anchor fields (`store_error`, `receipt`, `immudb_problem`) in the admin and audit screens.
6. **Manual-vs-portal timing runs** for section 2, then fill in the Expected outcomes table.
7. **Recorded backup demo video.**
8. **CI workflow (manual permission first).** Run `gh auth refresh -h github.com -s workflow` in PowerShell; after that the workflow can be added. The old file is on the local branch `main-local-with-ci`.
9. **Hindi translations:** `apps/web/src/i18n/hi.json` was written by Claude and needs a fluent reviewer.
10. **Idea submission** for the PS deadline (on hold).

### Small follow-ups from the PR #12 review

All three were fixed on 26 Oct in PR #17 (API side):

- ~~`GET /institutions` scopes by `len(roles) == 1` and region.~~ It now uses the action-aware rule (`scope_institutions`). An institution with a bank role sees only its own institution, and a bank account sees none.
- ~~`next_states` and `editable_fields` come from all of the caller's roles.~~ They now come from the roles that can reach the instrument, and `next_states` also leaves out moves that policy (bank attestation before *Active*) or an open critical flag blocks, the same checks the endpoints apply. Editing a visible instrument without an editor role now returns 403 instead of 404.
- ~~**Still open, web UI:**~~ Done on `web-ui-redesign`: the detail offers only the moves and field checks in the API's hints, `/my` reads the caller's institution from `GET /me`, and System labels each model with its training data. Was: `apps/web/src/components/InstrumentView.tsx` shows the Verify-field, Verify-with-bank, observation and resolve-flag controls by `auth.has(role)` and never reads `editable_fields` / `next_states`, so it can still offer actions the API refuses (e.g. an institution-plus-West-officer account opening its own East FDR). `apps/web/src/app/my/page.tsx` treats `items[0]` of `/institutions` as the caller's own institution, which is wrong for an account that also holds an officer role; it should identify the caller's institution explicitly.
- ~~`CONTEXT.md` and README list #11/#12 as open.~~ Corrected.

### Unfinished test scenarios and gates

- **T-05:** the forgery part (recall ≥ 0.90, false alarms ≤ 5%) is not met; see section 1.
- ~~**T-06:** the missing-documents report endpoint is built but not separately tested.~~ API tests added in PR #18. The review of that PR also fixed the report: filling in a missing field now resolves its flag, released/renewed/rejected/archived records leave the report, flags are filtered in SQL in a stable order, and an unknown export format returns 422.
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
