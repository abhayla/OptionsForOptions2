# GC-ICLIVE Part F report: the owner's answers Q2 to Q8 and two screen-check FAILs (25 Nov 2026)

Scope (owner in chat, 25 Nov): ask Q7 and Q8 one at a time; build the Q2 to Q6 answers (ADR-326); fix the screen-check
FAILs D-18 and D-44. Not in scope: D-01, D-05, D-41, D-60, S-20 (owned by the modular clean-up on
`refactor/modular-doors`, plan `docs/design/modular-doors-2026-11-25/PLAN.md`; its D-01 rule is ADR-327 there).
- Branch `fix/ic-live-test-1123`, draft pull request #722 (still a draft, not merged). Cloud session; no screen opened.
- No Part F contract file exists; the run followed the owner's message and the common rules.
- Origin had moved to 874c751 (the orchestrating session's 5-point ADR-326 with the same Q2 to Q6 answers);
  merged without rebase, keeping this run's 7-point ADR-326 (Q2 to Q8) as the orchestrating session asked.
- **D-44, for the owner to keep or undo:** no spec text requires the Stops form and list to sit side by side
  (searched "side by side", "two column", "beside", "next to", "Stops panel", "stop list"; REQ-109 says nothing
  about layout). The layout was built because the owner's chat message said to fix the screen-check FAIL; the
  orchestrating session's launch text had said to record it as not a defect. Undo = revert the PaperStops.vue
  grid lines of b8740410.
- Ledger: `docs/process/ic-live-test-2026-11-23-status.md`. Chain report: `docs/process/GC-ICLIVE-final-report-2026-11-24.md`.

## Owner answers

- Q2 to Q6: recorded in `spec/decisions/ADR-326.md` (accepted). No ADR-326 file existed before this part; it was
  written from the answers as the plan's "Who owns what" table states them.
- Q7 (D-68) and Q8 (D-47), asked one at a time with the question tool: "Keep as built" each (ADR-326 (6), (7)).
- One more question during the build (D-67): the app cannot tell "true at entry" from "became true just after
  entry" when its first check comes late. Answer: a rule first found true within 5 minutes of entry and never seen
  false waits until entry + 5 minutes (ADR-326 (5), refined).

## Per issue

| Id | Status | What was wrong | What changed | Test (red, then green) | Rounds |
|---|---|---|---|---|---|
| D-25 | Fixed, not tested | Take profit offered at an after-charges loss (162: -223) | Refused with "Not in profit after charges: {after}" (own reasons when charges or a two-expiry result cannot be worked out); Exit stays offered; the approach id travels from Compare to the paper place POST, which refuses it the same way | test_take_profit_basis_d25.py: 8 failed, then 21 passed; roll-basis call sites; D-36 golden | 2 |
| D-57 | Fixed, not tested | The disconnect sentence kept a 12-hour time | One 24-hour IST clock: "Last updated: 10:42:17 IST", "Prices are from 15:30:00 IST."; ADR-015 Q182 amended; the 12-hour scan has no exception | test_no_12_hour_clock_d57 + marketdata + errors: 5 failed, then 1146 passed | 1 |
| D-67 | Fixed, not tested | Pop-ups 1-3 min after opening for rules already true (C10, C11) | Server `popup_due`: quiet while the rule was never seen false, its record opened within 5 min of entry and now is before entry + 5 min; record and bell count at once; scenario clock used | test_popup_quiet_d67 (domain 11, app 8 passed); playbook_store 51 passed | 3 + owner answer |
| D-18 | Fixed, not tested | Screen FAIL: tracking panel and Positions Paper row showed no per-leg quote time; Escape did not close the depth popover | Each leg price shows its own `price_at` on both; "time not available" when a live leg has none; Escape closes the popover | screen-fail-d18-d44: 4 failed, then 5 passed | 1 |
| D-44 | Fixed, not tested | Screen FAIL: Stops form and list stacked at 1536 px | Side by side from lg; Save-into-view kept | same file | 1 |

Review findings fixed in round 2: D-25 (two red repo-scan gates; the place-side refusal never ran from the screen),
D-67 (entry state judged by `seen_clear` alone, then by a 60 s first-check window that would not have quieted the real
case; the owner chose the rule).

Residue (MINOR, recorded): the Live card's leg prices show no quote time (D-41 area, modular branch); chain rows carry
one banner time (by design, D-19); the depth popover's Escape listener does not stop propagation; the backend 12-hour
scan reads `.py` files only (frontend has its own scan); a Take profit placed by a direct API call without an
approach id is not checked as one.

## Overlap with `refactor/modular-doors` (additive changes only; expect merge conflicts there)

`backend/ofo_app/routes/paper.py`, `backend/ofo_app/routes/adjustment.py`, `frontend/src/lib/tracking.js`,
`frontend/src/components/strategy/TrackingPanel.vue` (per-leg time), `frontend/src/components/strategy/PaperStrategies.vue`,
`frontend/src/pages/StrategyBuilderPage.vue`, `frontend/src/components/strategy/AdjustCompare.vue`. No price reader was
merged or moved; nothing of D-01, D-05, D-41, D-60 or S-20 was changed.

## Gates of section 6b

| Gate | Command | Result |
|---|---|---|
| Generated files | reply inventory (`popup_due`), `openapi.json`, digest, ADR-326 coverage stage: inside 625df8d9 (a helper's staged files were swept into the ledger commit); register a0252519; digest and register regenerated again in the merge of origin 874c751 | committed |
| Reply inventory | `python scripts/reply_inventory.py --check` | exit 0 |
| OpenAPI drift | `pytest -c pytest-app.ini tests_app/test_openapi_drift.py` | 1 passed |
| Coverage map | `python scripts/orchestrator/coverage.py . --check` | OK: every discovered id has a valid stage (issue compare skipped: `gh` not signed in) |
| Spec digest | `python tools/build_spec_digest.py . --check` | current (after the merge) |
| Repo scans (merged branch) | `pytest tests -m repo_scan`; `pytest -c pytest-app.ini tests_app -m repo_scan` | 1471 passed; 483 passed, 9 skipped |
| Front end, whole | `npx vitest run` | 222 files, 2605 tests passed |
| DB files touched, each alone | 10 files under `/root/ofo-db-fresh.sh` | 108, 18, 40, 51, 8, 15, 40, 75, 21, 9 passed (0 failed) |
| App suite without DB | `pytest -c pytest-app.ini tests_app -m "not full_chain"` | 5457 passed, 1702 skipped, 23 deselected |
| ci_local | `python tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped |
| prepush | `python scripts/orchestrator/prepush.py` | run on the report commit; result line in the PR #722 comment |

## DONE / PENDING / BLOCKED / PARKED / NEXT

- **DONE:** Q2 to Q8 answered and built or kept (ADR-326); D-25, D-57, D-67, D-18, D-44 Fixed, not tested. The ledger
  has 71 rows: 59 Fixed, not tested; 5 Could not reproduce; 5 Feature request (parked); 2 Parked; 0 Needs owner
  decision.
- **PENDING:** screen re-checks of D-18, D-25, D-44, D-57, D-67 on the owner's PC; the modular branch's D-01, D-05,
  D-41, D-60, S-20.
- **BLOCKED:** none.
- **PARKED:** none new.
- **NEXT:** the owner's screen checks; the modular branch merges this branch's head before its final push.
