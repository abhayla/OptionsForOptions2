# GC-ICLIVE Part B report: the 16 money-number issues (24-25 Nov 2026)

Contract: `docs/process/goal-contract-GC-ICLIVE-B-2026-11-24.md`. Branch `fix/ic-live-test-1123`, draft pull request
abhayla/OptionsForOptions2#722 (still a draft, not merged). Cloud session, owner away; no screen was opened, so the
highest status is **Fixed, not tested**. Ledger: `docs/process/ic-live-test-2026-11-23-status.md`. Decisions:
`spec/decisions/ADR-321.md` (PENDING OWNER READ). Owner question: `docs/process/owner-questions-2026-11-24.md`.

## Start of the part

- `origin/main` was already inside the branch: no merge.
- Part A's checks on f0230d0, read once: 5 done (success or skipped); api, frontend and domain-tests were still running,
  none red. Part C reads them again.
- Local PostgreSQL 16, template `ofo_h_tpl`, a fresh clone per DB run (`/root/dbrun.sh`); proof
  `test_paper_duplicate_leg_d60.py` 2 passed.
- Skipped (already done): none. No Part B issue had been started before.

## Per issue

Every fixed issue got: a red test first in its own commit, the fix at the engine or reply every screen reads, an
independent fresh-context review (Opus for money maths), and the hand check below.

**D-06 (card vs builder max profit/loss).** Wrong: the Live card rebuilt a plan from the open legs (no booked P&L,
plan charges). Now: the card reads the one paper reply the builder tiles read. Hand check C1 155: the open-legs
figures +1,985 / -4,515 leave out the booked +643.50; the paper reply gives +2,380.32 / -4,119.68, a range of
6,500.00 on both screens. Test: `live-card-paper-figures-d06.test.js`, red 4 failed, then 3 passed. Fixed, not tested.

**D-07 (three P&L totals).** Every paper total already comes from `book_after_charges`. The C4 gap was not found in
code. The card now says "Total P&L ... (after charges)" with its time. Could not reproduce. To reproduce: record the
three screens and the paper reply in the same minute.

**D-08 (expiry-day estimate).** The engine already values to the 15:30 close in exact seconds. The -1,675 against
+484.25 gap was real time value from high expiry-day IVs, not a one-day floor. "Estimate not available" came from one
leg at intrinsic with no solvable IV, which emptied the whole curve.
- Now: on a leg's own expiry day, before its close, a no-IV leg within one tick of intrinsic is valued at intrinsic.
  Every figure built that way says so. Other days are unchanged, and a price more than a tick under intrinsic still
  refuses.
- Hand check: at the close the C2-shaped condor is worth 7.45 x 65 = +484.25 at 25,300 and at 25,900; the engine gives
  484.25.
- Test: `tests/engine/test_expiry_day_d08_d12.py`, 10 passed. Three rounds (one extra by owner direction); the final
  review found nothing. Fixed, not tested.

**D-09 (fill vs quote on the dialog).** The fill rule (server live price, REQ-109 AC-4) is unchanged. The dialog now
says "about 42.55, as of 10:41:20, the server sets the exit price when you confirm". Test:
`paper-exit-quote-age-d09.test.js`, red 2 failed, then 3 passed. Fixed, not tested.

**D-10 (closed legs).** The engine splits each contract into lifecycles, so a closed leg is its own row with entry,
exit and booked. Hand check C1 155: (120.00 - 115.71) x 150 = +643.50 on the closed short; the new long row has 0
booked; the sum equals the strategy booked. Tests: `test_orderbook_lifecycles.py` 8 passed;
`test_paper_closed_rows.py` 6 passed. Six reconciliation probes in review. Fixed, not tested.

**D-11 (Add Booked switch).** Switch ON: tiles, curves, table TOTAL, 0-P&L columns and breakeven cells all include
booked P&L. OFF: the open legs, with a basis line. Hand check on strategy 63 (booked +962.00, 65 units): the
breakevens move by 962 / 65 = 14.80 (22,326.85 to 22,312.05), and TOTAL reads 0.00 at both. Three rounds (one extra
by owner direction); the final review passed. Fixed, not tested.

**D-12 (theta on expiry day).** On expiry day theta is replaced by "Decay left today: Rs X" in the builder Greeks, the
what-if, the paper API, the chain (per unit) and the adjustment Compare. Hand check:
(4.20 + 1.05 - 3.10 - 0.60) x 65 = +100.75; the engine gives 100.7491, shown 100.75. Merging D-12 turned every what-if
reply into a 500 (a response-model field was missing). It was found by the D-15 build and fixed in c8cacba4: 29
failed, then 75 passed. Why it was missed: the D-12 tests never called the outcome route with a target. Fixed, not
tested.

**D-13 (profit left gross).** Profit left and Loss left are now the ADR-306 figures after charges. REQ-109 AC-9 now
cites ADR-306. Test: `test_charges_basis_d13_d14.py`, red 5 failed, then 6 passed. Fixed, not tested.

**D-14 (three charge estimates).** One cost to close, at the live price, everywhere. The Charges line reads "Charges
paid" with "Estimated cost to close" beside it. On expiry day the page shows "If held to expiry" and "If exited now".
Hand check C2 157: held = 484.25 - 97.24 paid = +387.01, the settled figure; the old screen showed
484.25 - 193.76 = 290.49. Three rounds (one extra); the final review passed. Fixed, not tested.

**D-15 (plan vs fills).** Done:
- The server derives the summary's price basis from the paper book, so a client cannot claim it.
- The Add to Paper price shows "plan 36.45" when the price was re-quoted.
- Hand check C11: 23.70 x 65 = 1,540.50 at fill prices.

**Parked:** the "Plan: Get Rs X" line was withdrawn (17e585a0). Its round-3 review found it priced only the legs still
held once a planned leg was exited, which gives a made-up plan credit. Next: check that every plan leg is still held,
then turn the line back on with a test.

**D-16 (breakevens).** The paper breakevens now carry the same charges and booked P&L as Max Profit and Max Loss, with
a basis line. The chart marks sit on the curve's own basis. Hand check: a charge of 500 on 65 units moves each
breakeven by 7.69 points (22,653.30 to 22,660.99). Fixed, not tested.

**D-17 (time value basis).** Needs owner decision. REQ-081 AC-3 says time value is "current premium minus
intrinsic"; the contract says it uses the same prices as the credit. Built to the contract, a sold put read +1,709.50,
a "premium paid" sign. The code is reverted to live prices; question Q1 has a recommendation.

**D-18 (2-4 prices per leg).** Each leg price carries its own quote time. The leg list leads with the oldest, taken
from the server, and the chain picker uses its own quote time. No shared store was built. Tests: route tests 66 passed;
frontend 7 passed. Three rounds (one extra); the final review: covers the class. Fixed, not tested.

**D-19 (LTP outside bid/ask).** LTP, bid and ask come from one packet, now pinned by a test. The chain shows "Last
trade 09:19:53 IST", with the date when the trade is from an earlier day. Test: `test_chain_live.py` 90 passed.
Fixed, not tested. The rest is a feed-timing fact: Could not reproduce.

**D-20 (parity gap).** Could not reproduce. Carry at 6.5% over 3 days gives F - S = +44, not -72; -72 would need an
implied yield of 17% a year. No strike-level snapshot of 23 Nov exists to replay. Nothing built.

**D-63 (two-expiry trade).** The P&L Table lists the closed rows and the charges lines, so the rows add up to the
Total. Hand check: 750.00 + 643.50 - 40.00 - 20.00 = 1,333.50 = Total. The Greeks Total says "summed across 2
expiries". Margin is unchanged. Fixed, not tested.

## The one function each shared number reads

| Number | Function every screen reads |
|---|---|
| D-06 max profit / loss on card and builder | `GET /paper/strategies/{id}` `_extremes` → `extremes_charges.max_after_charges` |
| D-07 total P&L | `extremes_charges.book_after_charges` via `sharedTotal` / `afterFigure` (labels only) |
| D-11 curves and tables with booked | `outcome/target.with_booked_curves` + `scenario/levels.booked_level_set` (engine `add_booked`) |
| D-16 breakevens | `extremes.book_breakevens(view, terms, charges=)` over `metrics.breakevens_with_shift` |
| D-18 leg prices | each reply's own quote time; `oldest_quote_at` from the outcome route |

## Decisions pending the owner's read

All of them are in ADR-321, points (1) to (9). The new sentences are pinned `pending owner read` in
`tests/errors/template_pins.json`. The front-end sentences cannot be pinned there and are listed in the builder
reports:
- "Charges paid", "Estimated cost to close", "If held to expiry", "If exited now"
- "Open legs only: ..."
- "Last trade ... IST", "Oldest leg price as of", ", as of HH:MM:SS"
- "Decay left today (Rs/unit)", "Total (summed across N expiries)", "plan X"

## Deferred (outside the issues' classes)

1. The held-leg-without-LTP change in the adjustment review was reverted, because it turned T-19 ADJ-20c red. Next:
   split `charges_known` in `compare.approach_cost`.
2. The table grid range is still taken from the open-legs breakevens. A large booked loss can push a shifted
   breakeven off the grid.
3. A cell whose whole quote is from an earlier day shows its last trade time only.
4. The table Greeks and Decay show no figure for a no-IV leg, while the what-if gives delta 1 or 0.
5. The full Strategy table view has no charges lines (only the compact P&L Table has them).
6. The templates `money_plan_get`, `money_plan_pay` and `money_plan_changed` are unused since the plan line was
   withdrawn.
7. Two helper commits (c8cacba4, 17e585a0) carry a different co-author line.

## Gates (section 6b, on the final head)

| Gate | Result line |
|---|---|
| Regenerate generated files | 50954e3e (openapi, reply inventory, spec digest), 498c36ea (outcome.openapi.json, ADR-321 stage) |
| `scripts/reply_inventory.py --check` | rc=0 |
| OpenAPI drift test | `test_committed_openapi_schema_matches_the_route` 1 passed |
| `coverage.py . --check` | OK: every discovered id has a valid stage (GitHub issue comparison not run: GraphQL 403) |
| vitest whole suite | 192 files, 2437 passed |
| DB files this part touched (14, one pass) | 551 passed |
| `tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped |
| `scripts/orchestrator/prepush.py` | see the pull request comment for the final head |

## Summary

- DONE (Fixed, not tested): D-06, D-08, D-09, D-10, D-11, D-12, D-13, D-14, D-16, D-18, D-19, D-63.
- Could not reproduce: D-07, D-20.
- Needs owner decision: D-17 (Q1).
- PARKED: D-15 (plan line). Next step is above.
- PENDING: the screen checks in the ledger, on the owner's PC in market hours; the owner's read of ADR-321.
- BLOCKED: none.
- NEXT: Part C, `docs/process/goal-contract-GC-ICLIVE-C-2026-11-24.md`, started by the orchestrating session.
