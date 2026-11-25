# Plan: one door per capability (modular clean-up + 5 bug fixes)

Owner request, 25 Nov 2026: "find the areas or features that are called from multiple places and make sure we have
not written multiple codes for the same part; if yes, compact it into a small module which can be called from
multiple other features" (example given: one exit function: given a strategy, exit all open legs at market).

Written 25 Nov 2026 ~16:40 IST from three read-only reviews (evidence/ folder). Base: branch `fix/ic-live-test-1123`
at e98148e1 (= 5d9b53ca + one test-golden commit). Work branch: `refactor/modular-doors`.

## Owner decisions that bound this plan (question tool, 25 Nov)

| # | Decision | Effect on this plan |
|---|---|---|
| Q1 | Start now on the fix branch, on its own branch | Build on `refactor/modular-doors` (from the fix branch). The owner screen-tests the fix branch (5d9b53c) tomorrow 26 Nov; this branch must not be merged into it until the owner says so. |
| Q2 | Scope = clean-up + the 5 bugs that come from the duplicates (D-01, D-05, D-41, D-60, S-20); no new features | Every duplicate below becomes one shared module; the 5 bugs are fixed INSIDE those modules. All other behaviour stays exactly as today. Exit supports "now / market" only. |
| ADR-327 | D-01 rule: in market hours, a trigger whose level cannot be checked against a live price (after asking the feed and waiting up to 3 s) is refused: "Not saved: the live price could not be read, so this level cannot be checked. Try again in a moment." Market closed: unchanged (saved, arms at next live tick). | Phase 1 implements it. `spec/decisions/ADR-327.md` is committed on this branch. |

Out of scope (written down so nobody builds them): paper limit-order exit (new feature; needs owner rules on leg order
and partly filled legs, ADR-281 / F-102); plan target / stop-loss / time exit placing orders (today they only alert;
feature S-10); bulk delete; the other 23 bugs of `evidence/combined-findings-2026-11-25.md` (separate fix round);
real (Kite) order placement of any kind (ADR-281: paper only).

## The principle (why)

One capability = one function (a "door") that every screen, rule and route calls. A fix in the door fixes every
caller. Today the same capability is rebuilt in several places, and three of today's defects are exactly that:
D-01 (the stop-save check read the price a different way from the monitor), D-05 (Positions blocks Exit on stale
prices, the builder's own Exit does not), D-41 (two panels on one builder screen read leg prices from two sources).
Prefer a structural guarantee over a detector (kit rule C3): the door is the only path; a guard test keeps it so.

## Inventory (what is duplicated today) — evidence: evidence/review-backend.md, evidence/review-frontend.md

Server (backend/):

| # | Capability | Copies today | Door to build | Bug fixed inside |
|---|---|---|---|---|
| B3 | Read a live price (leg or index) | 9-11 readers, several hold mechanisms, 4-5 hold nothing; `live_push.hold_and_read` (live_push.py:95) is bypassed | `read_market(ctx, underlying, leg_keys, need_index, purpose)`: asks the feed to hold what it needs, waits up to 3 s, returns prices + a state per price (live / stale / missing / market closed) | D-01, S-20 |
| B5 | Trigger save: "already crossed?" | `routes/paper.py:1637 _already_crossed` reads with no hold; keep route same shape | `check_trigger_levels(...)` on top of `read_market`; ADR-327 states | D-01 |
| B4 | "May this act now?" (market open, prices live) | `paper_limit.refuse_when_closed` (paper_limit.py:119), `paper_monitor.on_quote` calendar (:177), `market_state` (outcome.py:224), `paper.is_live`, others | `may_act(ctx, action, at) -> Allowed | Refused(reason)`, plus a read-only answer the screens can show before a click | D-05 (server half) |
| B1 | Exit legs (paper) | 4 server builders of "opposite side of the open book" (`routes/paper.py:1296`, `routes/tracking.py:513/550`, `paper_monitor.py:205/231`, `paper_settlement.py:164/171`) + the browser builds the basket (`frontend/src/lib/paperList.js:199 exitRowsFor`) | `exit_strategy(strategy_id, reason, only=None)`: reads the open net book under the strategy lock, builds opposite orders, buys first (ADR-117 / D-02), prices via `read_market`, refuses whole exit if a leg has no live price, writes through `paper_store.place` | D-05 (one rule for every Exit) |
| B6 | Strategy money figures (P&L, booked, charges) assembled for the API | `routes/paper.py:651 _figures`, `routes/tracking.py:312 _figures`, `outcome.py:389`, `adjustment_history.py:333`, `routes/adjustment.py:428` | `strategy_money_view(strategy_id, prices)` (engine maths stays where it is; only the assembly is merged) | D-41 (server half) |
| B2 | Real exit "close list" | `execute_plan.py:223 exit_legs`, `ofo/execution/partial.py:788`, + paper copies | share only `open_legs_to_close(book)`; the real gate stays separate. Tier A review | none (maintenance) |
| B7 | Raise an alert | `paper_trigger_store.add_alert`, `playbook_store.open_suggestion`, `notifier.notify` | `raise_alert(kind, strategy_id, facts)` | S-20 wording path |
| B8 | Order recording | `paper_store.place` — already one door | none; B1 feeds it | — |

Screens (frontend/src/):

| # | Shared thing | Copies today | Module | Bug fixed inside |
|---|---|---|---|---|
| F1 | Price freshness rule + wording | 6 separate checks, 8 strings (`tracking.js:108`, `paperList.js:16`, SummaryCards.vue:160 ...) | `lib/priceState.js` + `usePriceFreshness` | D-05, D-39 label (only where it is the same rule) |
| F2 | Exit paper positions | 2 order builders, 2 POSTs, 2 gates: `PaperStrategies.vue:240` (blocks on failed read) vs `StrategyBuilderPage.vue:439,444` + `PaperBookPanel.vue:16` (Exit all never disabled) | `usePaperExit` + one `ExitButton`; calls server door B1 | D-05 |
| F3 | Leg price per leg | builder alone polls 3 endpoints; Net Positions table vs `/tracking` panel (`TrackingPanel.vue:32`), each with its own 5 s timer | `usePaperBook` (one poll, one source) + `LegPrice` | D-41 |
| F5 | P&L total / booked / unbooked / as-of | 3 parsers, 2 pollers of `/paper/strategies` | `PaperPnlBlock` + one reader (`usePaperBook`) | D-41 |
| F6 | Add or move a leg | door exists (`lib/legDoor.js`); dialog copied (`LegPicker.vue:676`, `StrategyBuilderPage.vue:996`); strike step, ready-made, chain link and Compare entry points bypass it | `useLegDoor` + one `DuplicateLegDialog`; every entry point through it (ADR-322 (1)) | D-60 |
| F7 | Stops panel | `PaperStops` mounted on Positions only | mount the same component in the builder (no copy) | — |
| F8 | Rename | 2 UIs, one write call | `useRename` | — |

Helper-level duplicates from the 23 Nov review (`evidence/duplicates-2026-11-23.md`, RANK 1 RISK R1-R12): expiry
cut-offs (R1), ownership SQL (R2), rupee text (R3), setting-in-force (R4), intrinsic value (R5), Kite money parsers
(R6), Decimal parsing (R7), Kite token wiring (R8), Kite HTTP paths (R9), browser time formatting (R10), database
now (R11), to-IST (R12). R1 needs an owner answer (REQ-109 AC-7 pins 15:45) — park it. RANK 2/3 groups: skip unless a
door above touches them.

## Phases (in this order; each phase = tests first as its own commit, then the code commit)

Each phase states Core / Proof. "Behaviour unchanged" means the existing tests for every caller still pass unmodified,
except tests that pin one of the 5 bugs (change those in the tests-first commit and say why).

1. **B3 read_market + B5 trigger check (D-01, S-20, ADR-327).**
   Core: a save of "Above X" with the index above X is refused even when nothing else holds the index.
   Proof: `evidence/repro_d01.py.txt` (rename to .py to run) turned into a test (`tests_app/test_paper_trigger_unheld_index.py`): unheld index ->
   refused `paper_trigger_already_crossed`; held -> refused; market open + no price after 3 s -> refused with the
   ADR-327 line; market closed -> saved. Leg-stop alert carries the index value when the index ticks (S-20).
   Move every reader that bypasses the hold onto `read_market` (list in evidence/review-backend.md section 3).
2. **B4 may_act + F1 priceState (D-05 server half, D-39 where same rule).** One answer to "may I exit / place now?"
   that both the route and the screen use. Proof: a test per action state (open+live, open+stale, open+missing,
   closed) on the server; a vitest per state on `usePriceFreshness`.
3. **B1 exit_strategy + F2 usePaperExit (D-05).** All 4 server exit paths call `exit_strategy`; the browser sends
   "exit these contracts" (ids, lots for a partial) and the server builds sides, order and prices. Find whether
   `POST /strategies/{id}/tracking/exit` has any caller (none found in frontend; check tests); delete it if dead.
   Proof: one test per caller (manual all, manual subset, conditional exit, leg stop, settlement) asserting the same
   stored rows (side, qty, kind, reason, buys-first order) as before; builder Exit and Exit all disabled with the
   Positions wording when `may_act` refuses (vitest).
4. **F3 + F5 + B6 one paper book source (D-41).** The builder's Net Positions table and Paper P&L panel read the same
   prices from one poll. Proof: vitest rendering both panels from one fake book shows identical LTP per leg and leg
   rows that add up to the total; server test that paper and tracking figures for one strategy come from
   `strategy_money_view` and match.
5. **F6 useLegDoor (D-60).** Strike step, Shift, Width, Hedge, picker, edit form, ready-made, chain link, Compare:
   all through the door (ADR-322 (1): Increase / Keep separate / Cancel; one live question per move). Proof: vitest
   per entry point: moving onto a held contract opens the question; Escape = Cancel leaves the draft unchanged.
6. **B2, B7, F7, F8** (maintenance, behaviour unchanged). B2 touches the real-order path: Tier A review (fresh Opus,
   adversarial) before it lands; it must not change what is posted to Kite.
7. **23 Nov helpers R2-R12** where a phase above did not already absorb them (R1 parked for the owner).
8. **Guard tests (keep it modular).** A repo test that fails when: a route/monitor calls `read_snapshot` or a
   provider quote outside `read_market`; something other than `exit_strategy`/`paper_store` builds exit orders; a
   frontend file defines its own not-live string or exit POST. Detector is the second layer; the door is the first.

## How the cloud session works (rules)

- Read first: CLAUDE.md, `docs/process/runbook.md`, `.claude/kit/GUIDE.md`, this PLAN.md, the evidence files,
  `spec/decisions/ADR-327.md`, ADR-317, ADR-322, ADR-117, ADR-281, F-102 (spec/findings.md).
- Model routing (CLAUDE.md hard rule): the main session manages; builders Sonnet; Opus only for Tier A (B1 exit,
  B2 real path, B3 price door) review.
- Each phase: tests-first commit (red), code commit (green), then `python tools/ci_local.py`. Targeted pytest/vitest
  per file; long output to a log, read the tail. No DB test runs against the owner's VPS from the cloud; DB tests run
  in CI on the PR.
- Money is Decimal, never float (ADR-008). Never call a broker order endpoint. Paper only.
- Every PR body carries the Spec-deviation block (`Class: 3` for ADR-327 with the decision id; `Class: none`
  otherwise) and `Fixes`-free wording for partial items (no "fixes #N" unless the whole issue is done).
- Park, don't drag: 2 failed rounds on a phase -> write a `parked` note in this folder with evidence and go on.
- Questions for the owner are NOT asked in the cloud session: append them to
  `docs/design/modular-doors-2026-11-25/owner-questions.md` with a recommendation and continue with the spec-conformant
  choice.
- End: push `refactor/modular-doors`, open a DRAFT PR into `fix/ic-live-test-1123`, never merge, never mark ready.
  The owner merges after tomorrow's screen tests on the fix branch.

## Done means

- Phases 1-5 landed with their proofs green; 6-8 landed or parked with a note.
- `python tools/ci_local.py` TOTAL PASS on the final head; CI green on the draft PR (or every red explained).
- A results file `docs/design/modular-doors-2026-11-25/RESULTS.md`: per phase, the door, the callers moved
  (before -> after counts, e.g. "price readers: 11 -> 1 door + 0 bypasses"), the tests, and anything parked.
- A screen-check list for the owner (what to click to see D-01, D-05, D-41, D-60, S-20 fixed), since the cloud
  session cannot drive the live app.

## Who owns what (added 25 Nov ~16:50 IST, to stop two sessions fixing the same thing)

Two cloud sessions work at once. No item belongs to both.

| Session / branch | Owns | Must not touch |
|---|---|---|
| GC-ICLIVE session, Part F, on `fix/ic-live-test-1123` | The owner's Q2-Q6 answers (its ADR-326: Take profit refused at a loss after charges; 24-hour IST everywhere incl. the disconnect sentence; adjustment pop-up quiet 5 min after entry when its rule was already true; header totals and timeout messages kept), Q7 and Q8, screen-check FAILs D-18 and D-44 | D-01, D-05, D-41, D-60, S-20 and the shared modules of this plan |
| Modular session (this plan), on `refactor/modular-doors` | Phases 1-8 and the bugs D-01, D-05, D-41, D-60, S-20 (D-01 rule = ADR-327) | The Part F items above, `docs/process/owner-questions-2026-11-24.md` |

ADR numbers: ADR-326 = the GC-ICLIVE session's Q2-Q6 answers; ADR-327 = the D-01 rule (this branch). Any new
decision record on either branch takes the next number free on BOTH branches (`git ls-tree` both before writing).
Merge order: Part F lands on the fix branch first; this branch merges the fix branch head before its final push.
