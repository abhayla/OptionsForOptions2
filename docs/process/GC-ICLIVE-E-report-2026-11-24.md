# GC-ICLIVE Part E report: labels, wording, layout and the six small features (25 Nov 2026)

Contract: `docs/process/goal-contract-GC-ICLIVE-E-2026-11-24.md`.
- Branch `fix/ic-live-test-1123`, draft pull request abhayla/OptionsForOptions2#722 (still a draft, not merged).
- Cloud session, owner away. No screen was opened, so the highest status is **Fixed, not tested**.
- Ledger: `docs/process/ic-live-test-2026-11-23-status.md`. Decisions: `spec/decisions/ADR-325.md` (PENDING OWNER READ).
- Owner questions: `docs/process/owner-questions-2026-11-24.md`, Q5 to Q8.
- The chain's final report: `docs/process/GC-ICLIVE-final-report-2026-11-24.md`.

## Start of the part

- **Part D's checks on PR #722, read once:** `coverage` was RED: "issues: #723 is open on GitHub and has no stage"
  (the follow-up Part D filed). Fixed first in 63b2794 (stage row S6.7). `api` was still running at the read; the rest
  were green or skipped.
- **Branch:** the container's local branch ref was stale (an older history); the remote head ef419cc was checked out
  and the stale ref kept as `backup/stale-local-c7cb6d7` (local only). No merge from main: `git log HEAD..origin/main`
  was empty.
- **Database:** local PostgreSQL 16, migrations at head, a fresh clone per DB run (`/root/ofo-db-fresh.sh`). Proof:
  `test_paper_duplicate_leg_d60.py` 2 passed in 4.72 s (re-run by the main session); `test_paper_triggers_routes.py`
  64 passed in 63.83 s.
- **Skipped (already done):** none; no Part E issue had been started.
- **Screen-check results:** `docs/process/screen-checks-2026-11-25.md` did not appear on the branch during the run.
- **Lanes:** six parallel lanes in worktrees created from 63b2794, each cherry-picked onto the branch after its
  review. Two conflicts, both in `MyStrategiesPage.vue` imports and columns, resolved by keeping both sides.

## Per issue

Every row below has a failing-first test (red line recorded in the commit message or the ledger) and an independent
fresh-context review. "Rounds" counts review rounds.

| Id | Status | What was wrong | What changed | Test (red, then green) | Rounds |
|---|---|---|---|---|---|
| D-54 | Fixed, not tested | Delete had no confirm; Test did nothing | "Delete this playbook?" first; Test removed; the out-of-V1 line where it was (fixed sentence when the labels read fails) | playbook-delete-and-test-button: 5 failed, then 7 passed | 2 |
| D-61 | Fixed, not tested | No word after a buy-back left a lone long | The owner's sentence, decided on the server from the resulting legs, for every approach (A-27 too) | test_d61_lone_long_line: 6 failed, then 10 passed | 2 |
| D-68 | Fixed, not tested | No day figure | "Today (after charges)" on the Paper tab header, current trading day, scenario left out, REQ-109 AC-5 paused rule | test_d68_today_total: 7 failed, then 9 passed; vitest 4 failed, then 5 passed | 2 |
| D-41 | Fixed, not tested | Cards had no P&L and could stay on Loading | Positions paper-list figure with the Positions paused rule; failed read and 25 s no-answer lines; late answer replaces it; Health not built | pnl-cards-d41: 7 failed, then 9 passed | 2 |
| D-56 | Fixed, not tested | Home showed only indices | Running count, the bell number, total P&L, each from its page's function | home-figures-d56: 12 failed, then 12 passed | 2 |
| D-55 | Fixed, not tested | Filters late; Change / OI Change blank | Filters sent 300 ms after typing, rows kept; Min OI per shown side; Change from previous close, else "not available" | chain-filters-d55: 6 failed, then 7 passed; test_chain_live: 5 failed, then 104 passed | 2 |
| D-57 | Needs owner decision | US dates at six places | One formatter ("23 Nov 2026", 24-hour IST) with frontend and backend scans; the two ADR-015 Q182 sentences left 12-hour (clash, Q5) | one-date-formatter-d57: 4 failed, then 7 passed | 2 |
| D-58 | Fixed, not tested | Zero-price, quotes, side, time-exit and raw-key wording | Each fixed at its wording module; live T-01 line names the tested side; one rule-label reader | test_tested_side_d58: 8 failed, then 9 passed | 3 |
| D-44 | Fixed, not tested | Stop list raw names; below the fold | One leg-label map for form and list; saved row scrolled into view | wording-d44-d49-d58: 5 failed, then 8 passed | 2 |
| D-49 | Fixed, not tested | Header fixed word | Header follows Lots/Quantity | same file | 1 |
| D-52 | Fixed, not tested | Hint named a missing tab | Tab named only when listed; nothing shown until the read answers | d52-no-legs-hint: 3 failed, then green | 2 |
| D-53 | Fixed, not tested | Silent 20-character limit | One limit line per box, pinned equal to the server limit; title stays a heading (REQ-134) | d53-name-limit: 3 failed, then green | 2 |
| D-43 | Fixed, not tested | Names cut to ~8 characters | 9.5rem name floor (one shared class) on three surfaces | d43-strategy-name-width: 1 failed, then 2 passed | 2 |
| D-46 | Fixed, not tested | Small Greeks shown as 0.00 | Two significant digits for a near-zero Greek; max profit/loss pinned half-up whole rupees (the "4,773" not reproduced) | test_display_number_small_values: 5 failed, then 13 passed | 2 |
| D-42 | Fixed, not tested | Original legs; closed strategies missing | Current legs from the paper book; closed listed; one bad book degrades only its row | test_strategy_tracking: 2 failed, then 29 passed | 2 |
| D-65 | Fixed, not tested | Rename 422 (no revision) | Shared rename reads the revision first; the route still refuses a missing or stale one | rename-paper-d65: 4 failed, then 6 passed | 1 |
| D-66 | Fixed, not tested | Last save shown | "Closed" column: the last exit, stop or settlement time | backend 2 failed, then 3 passed; vitest 3 failed, then green | 1 |
| D-64 | Fixed, not tested | Raw errors and raw ids after 15:30 | The owner's sentence on builder, Positions and tracking from one clock function; payoff refusal names the leg; priced legs keep figures | test_problem_leg_named_d64 5 passed (raw-id scan); after-close-line-d64 4 failed, then green | 2 |
| D-39 | Fixed, not tested | Message contradicted prices | One decision from per-quote health; a missing leg quote counts as not live | test_feed_message_one_source_d39: 1 failed, then green | 2 |
| D-45 | Fixed, not tested | Labels interleaved; unlabelled rows | Leader chip apart from value; column names per group; right-aligned numbers | adjust-compare-readability: 3 failed, then green | 1 |
| D-47 | Fixed, not tested | "0 legs selected" beside a 4-leg draft; hover-only B/S | B/S always drawn; "N already in the draft"; lots box unchanged (Q8) | leg-picker: 3 failed, then 120 passed | 1 |
| D-67 | Fixed, not tested | Toasts covered buttons | Host inside the sticky header block; aria-live always present; no invented quiet period (Q6) | toast-bottom-right: red, then 8 passed | 2 |
| D-50 | Could not reproduce | Seen once | Hover and arrows pass on the real fixture; nothing built | payoff-hover.test.js passes | - |
| D-48 | Feature request (parked) | - | Not built (owner 24 Nov) | - | - |
| D-51 | Feature request (parked) | - | Not built (owner 24 Nov) | - | - |

Screen checks owed: one per issue, in the ledger's last column and in the final report's PC list.

Not tested here and why: no screen, no live market and no e2e run with a live API. The Live and My Strategies e2e
specs skip without their environment; `home.spec.ts` AC-4 and `chain-selection.spec.ts` need a live socket and API.

## Review findings fixed in round 2 (each was a real miss)

- D-61 covered only A-26; A-27 can also leave a lone long. Now decided from resulting legs for every approach.
- D-68 used the calendar day, not the trading day. Now the newest snapshot's India date.
- D-55 sent a request and blanked the table on every keystroke. Now debounced, rows kept.
- D-42 one unresolvable contract made the whole list a 500. Now only that row degrades.
- D-39 a leg with no quote hid the disconnected message; two callers bypassed the one decision. Both fixed.
- D-67 an in-flow host scrolled out of view. Now in the sticky header block.
- D-57 the guard was frontend-only. Now a backend scan too, with the two ADR-015 sites as named exceptions.

Residue (MINOR, recorded, not fixed): the builder's sticky left column (top 72 px) can sit under a shown pop-up, and
a pop-up is behind an open drawer (D-67); lots are not compared for a lone long (D-61); stored rule records show no
tested side (D-58); `test_d36_adjustment_counts.py` fails only inside combined DB runs (ADR-058 cross-file
interference, as Part D recorded; alone it passes).

## Decisions taken pending the owner's read

ADR-325 points (1) to (17), one per issue. New sentences pending owner read: listed in the final report.

## Owner questions written

- Q5 (D-57): CLASH, ADR-015 Q182 12-hour against ADR-320 24-hour. Not decided.
- Q6 (D-67): the number of quiet minutes after entry.
- Q7 (D-68): what "Today" adds up.
- Q8 (D-47): the lots box on every row.

## Gates of section 6b

| Gate | Command | Result |
|---|---|---|
| Generated files | one commit 26bd65e (reply inventory, `openapi.json`, digest, coverage stage S6.7 for ADR-325) and a82fdf7d (coverage register) | committed |
| Stale expectations | 4f5c3ce8: a 24-hour label (D-57), the D-68 reply model registered, 22 reviewer notes for new text owners | committed |
| Reply inventory | `python scripts/reply_inventory.py --check` | exit 0 |
| OpenAPI drift | `pytest -c pytest-app.ini tests_app/test_openapi_drift.py` | 1 passed |
| Coverage map | `python scripts/orchestrator/coverage.py . --check` | OK: every discovered id has a valid stage (open-issues compare skipped: `gh` not signed in here) |
| Front end, whole | `npx vitest run` | Test Files 220 passed (220); Tests 2591 passed (2591) |
| DB files touched, one pass | 11 files under `/root/ofo-db-fresh.sh` | one pass: 66 failed, 199 passed (ADR-058 cross-file interference, as in Parts C and D). Each file alone, on a fresh clone: 11, 34, 15, 104, 10, 9, 31, 214, 28, 29, 9 passed (494, 0 failed) |
| App suite without DB | `pytest -c pytest-app.ini tests_app -m "not full_chain"` | 5430 passed, 3 failed; the 3 were stale expectations fixed in 4f5c3ce8 (those files: 253 passed); the whole suite runs again inside prepush |
| ci_local | `python tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped |
| prepush | `python scripts/orchestrator/prepush.py` | run on the report commit; result line in the progress log and the PR #722 comment |

## DONE / PENDING / BLOCKED / PARKED / NEXT

- **DONE:** 21 issues Fixed, not tested; D-50 Could not reproduce; D-48 and D-51 Feature request (parked);
  Part D's red coverage check fixed. The chain is closed in the final report.
- **PENDING:** the owner's read of ADR-325 and Q5 to Q8; the screen checks.
- **BLOCKED:** D-57's last two sentences, on Q5.
- **PARKED:** none in this part.
- **NEXT:** the screen checks on the owner's PC (list in `docs/process/GC-ICLIVE-final-report-2026-11-24.md`).
