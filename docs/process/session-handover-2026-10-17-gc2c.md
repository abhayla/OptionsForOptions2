# Session handover 2026-10-17: goal contract GC-2c (the app Execute chain) - PARTIAL

Ran 2026-10-17 05:49 IST under `/goal`. Contract: `goal-contract-GC-2c-2026-10-18.md` (cap 6 h -> 11:49). Active work
ran 05:49 -> ~09:10 IST; the next clock reading was 16:53 IST (the machine was most likely asleep or suspended - no
command ran that long), so by the wall-clock rule the cap had passed: new building stopped, the rest was parked and
this close-out ran. Verdict **PARTIAL**: items 1, 2 and 5b are DONE; items 3 and 4 are moved by name; most of item 5's
carry-overs remain. Next: **GC-2e** (`goal-contract-GC-2e-2026-10-18.md`, marked NEXT) - live-order preparation; GC-3
(the owner-present live run) is written by GC-2e.

## DONE (merged on main)
- **RUNNING marker:** PR #351.
- **Item 1 + item 2 = the contract's core, proven on the owner's real 2026-10-16 recordings:**
  - W-093 Kite read door - GET orders / trades / positions (#354). Tier A PASS.
  - W-094 stored plan intent - one open plan per strategy, tags never reused, migration 0016 (#357). ADR-050 4(b);
    ADR-105. Tier A REVISE (MAJOR: 0016 missed the ADR-048 allow-list post-phase) -> fixed, re-check FIXED; three CI
    reds fixed (pricing-name scan, broker-identifier column rule, a stale raw test INSERT).
  - W-095 Execute route (#359): saved strategy -> Zerodha order-book read -> plan number under the lock -> held
    position = net of filled quantities over ALL plans -> live depth limits -> Zerodha margin -> fresh eligibility ->
    gate -> `checked_basket` -> plan stored -> sealed basket text returned. Core: strategy 1, ENTRY BUY 65
    NIFTY26O1923650CE LIMIT 3.35 OFS1V1L0; EXIT SELL 65 LIMIT 3.30 OFS1V2L0; a third EXIT refused at net 0. Four
    rounds: Tier A review CRITICAL (after a completed exit, EXIT built SELL 65 again on a flat account - from the
    orchestrator's own brief; ADR-105 corrected) -> fixed; an independent investigation of the second core failure
    found the request-vs-database clock class -> fixed; re-check FIXED.
  - W-096 return route (#358): read back by tag, plans closed from Zerodha's answer (working / nothing_placed /
    partial / filled / exited), fills once, per-strategy reconciliation (REQ-060 AC-7), external orders recorded. Core:
    plan 1 filled 65, plan 2 exited, P&L -130.00, replay changes nothing. Tier A REVISE (two MAJORs: another strategy's
    unreturned plan hid a shortfall; a next-day return closed nothing_placed while 65 were live) -> fixed, re-check
    FIXED; round 3 found the audit stamp on the request clock -> database clock.
  - W-097 live 5-level depth (#356): the recording's frame matches Zerodha's REST quote on 10/10 levels. Tier A REVISE
    (MAJOR: a negative depth quantity crashed the frame loop) -> fixed, re-check FIXED.
  - W-099 circuit bands from GET /quote (#360). Tier A PASS (3 MINOR).
  - W-100 bands wired into the Execute route (#361, merged 17:02 IST after a network drop interrupted its first
    landing): ENTRY reads each leg's band from Zerodha's quote; Tier A PASS (4 MINOR).
- **Item 5b - W-098 one seal for proof objects** (#355): repo test discovers the gates' proof types by signature;
  Tier A PASS (4 MINOR applied); one CI red (producer-inventory scan) fixed.
- **Decision rows / findings (this docs PR):** ADR-105 (plan numbers, stored first, one open plan, held = net of all
  plans); findings `design-misses-cross-cutting-safeguard`, `repo-wide-scan-outside-targeted-tests` (7 occurrences,
  unguarded), `request-clock-for-database-stamped-fact` (3), `builder-report-describes-uncommitted-work` (1);
  occurrences added to `branch-migration-tests-move-shared-db` (now 4, three shapes) and `builder-budget-is-prose`.
- **Mechanisms in this docs PR:** `check_brief.py` requires `tests/errors/test_producer_inventory.py` in a brief's test
  line (red-then-green test); `atool.py` restores the shared test DB to main's head after its migration-tests step
  (`atool_restore.py`, fake-runner tests red-then-green).
- **Deferred issues filed:** #352 (a plan open at the end of the trading day), #353 (allow-list checked per call, not
  per calling module).
- **Item 8:** a GC-3 draft was written and independently reviewed (NOT READY: the live run could not start on what is
  merged) -> split: GC-2e written (preparation), independently reviewed (NOT READY on the first draft, 8 findings
  accepted and applied, re-check "applied: all"), marked NEXT. Records: `gc-3-draft-review-2026-10-17.md`,
  `gc-2e-contract-review-2026-10-17.md`.
- **Item 7:** kit #113 checked: OPEN, but it is about kit tools in linked worktrees - the contract mis-cited it for the
  verifier hook's false block (a class-1 card defect, corrected in GC-2e's carry-overs).

## PARKED / MOVED (by name)
- **Item 3, persisted order book (#313):** partly covered - plans, tags and per-order filled quantities are stored
  (W-094); adopted holdings remain in memory. Remainder stays on #313 (carried in GC-2e).
- **Item 4, the Execute screen:** moved into GC-2e item 5 (W-104), with a live subscription, the cost, and the owner's
  clicks per the GC-3 draft review.
- **Item 5 carry-overs:** none done this run; all listed in GC-2e's carry-over section.

## State at close
- Every GC-2c code item that was built is merged: #354, #355, #356, #357, #358, #359, #360, #361.
- Shared test DB (ofo_test): `0016_execution_plans (head)` = main's head.
- Open question (not a finding yet): CI e2e "too many connections for role ofo_app" once on #359; passed on re-run.

## Misses (each recorded)
- The orchestrator's W-095 brief stated the EXIT's held legs as "the latest ENTRY plan closed filled" -> the review's
  CRITICAL (ADR-105 corrected; the class is in `design-misses-cross-cutting-safeguard`'s family of brief defects).
- The contract assumed items 1-2 were joins of existing pieces; four pieces were missing (read door, plan store,
  depth source, band source). Found by a wiring map + a design review before code.
- Two DB runs started side by side by the orchestrator on the shared test DB (third shape of the shared-DB class).
- The orchestrator banned local DB runs to avoid contention, and two fix rounds then edited DB tests blind (W-094).
- Builders over budget: W-093 62/50, W-097 71/56, W-098 65/56, W-094 76/64, W-095 r2 106/76, W-100 42/40.
- The W-098 worktree was removed before its landing log was read (nothing lost: the branch was on origin).
- 7 repo-wide-scan reds and 3 ratchet rises surfaced only in CI or the integrator's full domain pass.

## Scorecard
CI runs = GitHub workflow runs per branch (`gh run list --branch`). Tool calls = used / budget.

| Item | Review rounds | CI runs (failed) | Local full-suite runs | check_brief | Idle > 10 min | Budget overruns |
|---|---|---|---|---|---|---|
| RUNNING marker (#351) | 0 | 3 (0) | 0 | - | 0 | 0 |
| Design + review (ADR-105) | design review 1 (UNSOUND -> applied) | - | 0 | - | 0 | 0 |
| W-093 read door (#354) | Tier A 1 (PASS) | 4 (0) | 0 | y | 0 | 1: 62/50 |
| W-094 plan store (#357) | Tier A 2 (REVISE -> FIXED) | 18 (4) | 2 integrator domain passes | y | 0 | 1: 76/64 |
| W-095 Execute route (#359) | Tier A 2 + investigation + re-check | 4 (0; 1 e2e re-run) | 1 integrator | y | 0 | 1: 106/76 (r2) |
| W-096 return route (#358) | Tier A 2 (REVISE -> FIXED) | 17 (4, draft on an old base) | 2 integrator | y | 0 | 0 |
| W-097 live depth (#356) | Tier A 2 (REVISE -> FIXED) | 4 (0) | 0 | y | 0 | 1: 71/56 |
| W-098 sealed proofs (#355) | Tier A 1 (PASS) + MINOR round | 12 (1) | 1 integrator | y | 0 | 1: 65/56 |
| W-099 quote bands (#360) | Tier A 1 (PASS) | 12 (1) | 2 integrator | y | 0 | 0 |
| W-100 band wiring (#361) | Tier A 1 (PASS) | see PR | 1 integrator | y | 0 | 1: 42/40 |
| Docs + GC-2e | contract reviews 2 + re-check | docs PR | 0 | - | 1: the machine's sleep 09:10-16:53 | 0 |

"Local full-suite runs" target 0: the integrator ran the domain suite (no DB) once per branch after the GC-2c
repo-scan reds - a deliberate change now written into GC-2e's process rules. No local full app (DB) suite ran.
