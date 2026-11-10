# Goal contract GC-ICGUIDE: iron condor adjustments tracked and guided right, for 5 NIFTY condor types (2026-11-09)

**Status:** APPROVED by the owner on 2026-11-09 (plan approval after a question-by-question session).
**Executor:** `/goal` in a fresh session of this project.
**Branch:** a new worktree from `main`. This file is uncommitted in the main checkout: copy it in at task 2 and
commit it with the run.
**Plan copy:** `C:\Users\itsab\.claude\plans\proud-herding-pebble.md` (same content).

**Mission:** for paper iron condors entered in the app, every adjustment is tracked per the user's preferences,
guided correctly, and ends in a correct exit or expiry. This is proven on 5 NIFTY condor types, through the app's
own screens: test data first, then live prices.

**Core:** a paper NIFTY weekly condor on test data goes entry -> warning -> Compare -> booked adjustment -> new
legs watched, through today's code.
**Proof (task 4, before any code change):** that run through the screens in the owner's visible Chrome, with a
screenshot and the value of each step. It breaks -> HALT, report, re-plan. Nothing else here is useful without it.

## §0 Run rules

1. **Paper only.**
   - No real order, no Kite order page, no click inside any Kite order panel.
   - Nothing is adopted from Kite.
   - Every condor comes from the builder (ADR-201, REQ-109).
2. **Test data before live data, always.** A type that fails on test data gets no live pass until it is fixed.
3. **Status page:** https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK, db collection `tasks`.
   - Rows have `kind: "icguide"` and ids `g01`..`g38`, ordered 101..138.
   - One ArtifactData `update` at a task's START (state `running`, start time) and one at its FINISH (state
     `done` / `parked` / `failed`, finish time, actual minutes, evidence). Pin `if_version`.
   - Never a mid-task write. Never touch the run rows (`t*`) or feature rows (`f*`).
   - The page renders kinds `feature` and run rows today. Task 1 added an `icguide` section to the page source
     (republish to the same URL, nothing removed).
   - Stamp times from the clock (`Get-Date`) in the same step.
4. **Workers:**
   - Fixes go to Sonnet builders in two batches: backend tasks 10-19, 21, 22; frontend tasks 20, 23 and screen
     parts.
   - Opus only for task 13, with a `Why Opus:` line.
   - Every brief carries:
     - `Budget:`, `Core:`/`Proof:`, `Class:`, `Report: evidence-table`;
     - the `.claude/kit/builder-brief.md` standing items;
     - every answer state (stated, absent, not found, failed, empty, ambiguous).
   - Merge the builder's reported sha after a diff read (never a branch by name).
5. **Tests:** targeted per file only.
   - DB tests one file at a time:
     `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`
     (the host serves prod).
   - Long output goes to a log file; read the tail.
   - ONE full gate (task 33), ONE PR, ONE CI run.
   - Generated files stay out of the PR, except the scenario output the byte test needs.
6. **Browser:**
   - Use Claude in Chrome in the owner's visible Chrome window; app pages only.
   - Start the stack from the worktree with the commands in `docs/process/session-handover-2026-11-08-gc-ictrack.md`.
   - Run long processes under Desktop Commander `start_process`.
   - Stop only PIDs this run started. Never select a process by its command line.
   - Test-data mode is the app's scenario mode (dev only; `scenario_mode.py`).
7. **Stuck work:**
   - Park after 2 failed rounds (`parked` issue with the evidence, `PARKED (#N)` in the row) and move on.
   - A defect outside a task's done line becomes a `deferred` issue (`gh_issue.py app ... --stage`).
   - Owner away -> `docs/process/owner-questions-<date>.md`, never the question tool.
   - No AskUserQuestion at night.
8. **Done claims:**
   - Every done row names the command or screenshot and its result line.
   - "It ran" is a check, not a proof: name the value that moved.
   - Before the PR, run `python tools/ci_local.py` and keep its marker for HEAD.

## §1 Decisions to write (task 3; owner answers 2026-11-09, question tool)

- **ADR-281:** order placement on Kite is on hold for this round (handover 2026-11-06: "Paper only; no real order").
  - The owner's wish that both baskets are placed automatically is a FUTURE item. It needs a SPEC CHANGE of
    ADR-054 / ADR-100 (the user presses Execute on Kite) at that round, plus the two-basket rule of ADR-117 for
    adjustments and exits.
  - Audit C1, C3, C4, C5, C14 stay open under it.
- **ADR-282:** the iron condor proof matrix is NIFTY only, 5 types, each through entry, warnings, a guided 1st and
  2nd adjustment, and exit or expiry:
  - (1) intraday: entered and closed on expiry day, 0 days left;
  - (2) weekly, entered 5-6 days before;
  - (3) monthly expiring this month;
  - (4) next month;
  - (5) 2 months out.
  - Proven on test data first, then live prices, through the app's screens as a user. SENSEX later.
- **REQ-046 AC-2 "margin utilisation"** = the strategy's margin / (available funds + margin in use). Decided as the
  strategy expert under the owner's delegation; written in the AC text.
- **Audit decision lines** (`docs/process/ic-e2e-code-audit-2026-11-07.md`):
  - C9, C10, C11, C12, C13, C6: "fix in GC-ICGUIDE";
  - C1, C3, C4, C5, C14: "on hold, ADR-281".
- **F-102 in `spec/findings.md`** (+ class file `knowledge/findings/publisher-basket-order-not-guaranteed.json`;
  regenerate the index via its wrapper). Measured 2026-11-09 by web research:
  - **(a) Kite's own basket (Kite web/app) is sequential.**
    - "The orders are placed in the same sequence as in the basket"; drag to reorder.
    - For F&O, "place the buy option orders first so that the required margin is lower".
    - The final margin is the same whatever the order; max 20 orders per basket.
    - Source: https://kite.trade/docs/kite/orders/. Z-Connect: "tiny delays of a few milliseconds between each
      order ... Without this delay, margin calculations might not keep up, and orders could get rejected"
      (https://zerodha.com/z-connect/featured/advanced-order-features-on-kite-a-comprehensive-guide).
  - **(b) The Kite Publisher basket (`kite.zerodha.com/connect/basket`, our path, `basket.py:57`) does not
    guarantee order.**
    - Zerodha staff, Oct 2018: "The Kite Publisher will just make API call in parallel, the order of execution is
      not guaranteed"; the user's own 2-order test "seems random"
      (https://kite.trade/forum/discussion/4917/basket-order-execution-order).
    - No newer official statement was found: unverified for 2026.
    - Cheap proof if ever needed: 2 non-filling LIMIT orders in market hours, read the exchange timestamps, cancel.
  - **(c) A far OTM wing BUY can be refused.**
    - Jan 2023: an iron condor wing 350 points from spot was refused under Zerodha's member OI limits until the
      sell was placed first.
    - Staff: "there is no way to enter the buy leg without entering the sell leg first if the strike is outside the
      range" (https://kite.trade/forum/discussion/10230/basket-orders-execution-documentation-missing).
  - **(d) The Publisher returns no per-order status.** The order book has to be read afterwards (Check with
    Zerodha).
  - **Class:** "a multi-order hand-off whose execution order the vendor does not guarantee can place a dependent
    order (a sell) before the order it depends on (its hedge); correctness needs a structural split (two hand-offs
    gated on the first's fills), never a list order". Status: unguarded (ADR-281 holds the work).

## §2 Reuse (verified on main 624508d6, 2026-11-09)

- **Scenario library:** `tests/adjust_scenarios_gen.py`.
  - NIFTY: lot 65, step 50, weekly weekday Tuesday (`:57`).
  - Stages: weekly Early 5+ / Middle 2-4 / Last 0-1; monthly Early 10+ / Middle 3-9 / Last 0-2 (`:213-215`).
  - `check_expiry` (`:328`).
  - The IC expiry-day rule is 14:30, short within 0.3% (`:194-195`).
  - The byte test is `tests/test_adjust_scenarios.py`.
  - Today: 76 cases, nearly all NIFTY weekly, 2 monthly.
- **Compare:**
  - `routes/adjustment.py` reads the paper or real legs through `adjustment_readers.read_tracked` (`:122-126`).
  - `MultiExpiryError` is caught at `:418` (C12).
  - `ofo/adjustment/compare.py:397` is the #654 crash.
- **A-29:** `ofo/adjustment/approaches.py:719-724` (C11).
- **Max adjustments:** the offered filter is at `ofo/adjustment/offered.py:33-40`. Saving is at
  `routes/paper.py:726-760` and `paper_store.place`, with no limit check today (C9). ADR-255: a partial exit counts.
- **Paper exit price:** `routes/paper.py:703-742`, `frontend/src/lib/tracking.js:54-59`. The server-priced
  `POST /strategies/{id}/tracking/exit` (`routes/tracking.py:425`) has no frontend caller (C10).
- **Settlement:**
  - `ofo/reconciliation/settlement.py` `settle_legs` / `settle_expired_legs` has 0 app callers.
  - Paper settles in `paper_settlement.py`, started at `main.py:96` (C6).
- **Completed:** `frontend/src/pages/MyStrategiesPage.vue:24` `COMPLETED_STATUSES = []`; paper "EXITED" is worked
  out at `routes/paper.py:428` (C13).
- **Issues:** #623, #647, #650, #651, #652, #654, #661, #662 (read each issue body before its task).

## §3 Tasks (each <= 15 min; status row id = g + number)

| # | Task | Min | Done line |
|---|---|---|---|
| 1 | Status page: GC-ICGUIDE section and rows (done in the planning session) | 10 | ArtifactData list shows g01..g38 |
| 2 | Worktree from main (`wt-new.ps1`, purpose GC-ICGUIDE, TTL 48h); copy this contract in | 5 | `git log` on the new branch |
| 3 | §1 decisions: ADR-281, ADR-282, the REQ-046 AC-2 line, the audit lines, F-102 + class file; regenerate the digest | 15 | files exist; digest lists them |
| 4 | **CORE PROOF** in test-data mode through the screens (see the top) | 15 | screenshots + values per step, or HALT |
| 5 | Test data, intraday type (entry 09:20 on expiry day, morning move, 1st + 2nd adjustment, 14:30 rule, expiry) | 15 | byte test passes; expected values hand-checked |
| 6 | Test data, weekly type (Early -> Middle -> Last-day) | 15 | same |
| 7 | Test data, this-month type | 15 | same |
| 8 | Test data, next-month type | 15 | same |
| 9 | Test data, 2-months-out type | 15 | same |
| 10 | C9: max adjustments enforced on save (ADR-255 counting) | 15 | a 3rd is refused in a test |
| 11 | #662: a T-18 record when the maximum is reached | 10 | test |
| 12 | C11: A-29 never proposes 0 lots | 10 | 2 lots / divisor 3 refused |
| 13 | C12 part 1: before/after maths for a two-expiry position | 15 | engine test |
| 14 | C12 part 2: Compare shows it for a roll to next expiry | 15 | route test |
| 15 | #650: trigger values in their right unit | 15 | test |
| 16 | #651: max loss with one sign on every screen | 15 | test |
| 17 | #654 + #623: Compare never crashes on joined texts | 15 | tests |
| 18 | #652: open suggestions lapse when their strategy leaves the worker's list | 15 | test |
| 19 | #661: T-19 checked; S-12 entry day; no second T-11 record at flat IV | 15 | tests |
| 20 | #647: drawer margin used (§1 definition) + each option's IV / OI / LTP | 15 | test + screen spec |
| 21 | C10: paper exit priced by the server | 15 | test; browser price ignored |
| 22 | C6: an expired real leg settles (scheduled beside paper settlement); unit-proven only | 15 | test |
| 23 | C13: Completed screen: final P&L, adjustments made, their cost (closed status stored) | 15 | test + screen spec |
| 24 | New user-facing texts + wording checks (`tests/strategy/test_templates.py`, name guard, ruff ratchet); list saved | 15 | checks pass |
| 25 | Owner reads the new texts (one batch) | 10 | answer recorded |
| 26 | Screens, test data, intraday: build, place paper, warning, Compare, 1st + 2nd adjustment, 14:30 close, expiry, Completed | 15 | screenshots + values |
| 27 | Screens, test data, weekly | 15 | same |
| 28 | Screens, test data, this month | 15 | same |
| 29 | Screens, test data, next month (roll-to-next-expiry picture) | 15 | same |
| 30 | Screens, test data, 2 months out | 15 | same |
| 31 | Independent Tier B reviewer (fresh Sonnet, diff only, 20 min): money, limits, settlement | 20 | verdict PASS or fixes listed |
| 32 | Fix the findings (contingency) | 15 | re-run passes |
| 33 | `python tools/ci_local.py` once; contingency for reds | 30 | TOTAL PASS + marker for HEAD |
| 34 | One commit set, handover, ONE PR (Spec-deviation block if any), merge on green, `wt-rm.ps1` | 15 | merge sha on main; counts unchanged |
| 35 | Live prices, market hours: weekly + this-month condors entered, watched, adjusted once through the screens | 15 | screenshots + values |
| 36 | Live prices: next-month + 2-months-out, same | 15 | same |
| 37 | Next Tuesday (expiry day): intraday live through the screens; until then the row says "not yet run live" | 15 | same |
| 38 | Verifier pass over every task's done line | 15 | one evidence block per task, all PASS |

Total about 535 min (~9 h), or ~11.5 h with the measured 30% overrun.

## §4 Done

The contract is done when all of these hold:
- every row is `done` with its evidence, or `parked` with an issue (that keeps the contract PARTIAL);
- the PR is merged to main;
- the 5 types pass on test data through the screens;
- the live passes are recorded (intraday may be "not yet run live" until its Tuesday, and then the contract stays
  PARTIAL until 37 runs);
- task 38 passes.

Not in this contract:
- placing orders on Kite (ADR-281);
- real Zerodha positions;
- SENSEX;
- C4;
- #627;
- #644.

## §5 Final report

DONE / PENDING / BLOCKED / PARKED / NEXT, plus:
- the status page link;
- the PR and merge sha;
- per condor type, the test-data and live results with one example value each;
- every deviation from this contract.
