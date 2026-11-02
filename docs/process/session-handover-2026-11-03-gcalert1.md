# Session handover: GC-ALERT1 (alert discipline, check speed per style), 2026-11-02 20:55 to 2026-11-03

Contract: `docs/process/goal-contract-GC-ALERT1-2026-11-02.md` (Progress table has every evidence line). Branch
`feature/adjustments` in `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`; 6e94f46d..HEAD = 55 commits,
63 files, +6,135 / -253. Nothing on main. Owner amendment 2026-11-03 00:39: the live step moved to GC-LIVE4; push as soon
as the full gate passes.

## DONE
| Item | Result |
|---|---|
| Step 0 core data | Kite 1-minute candles of both legs of strategies 66/67 (NIFTY 3 Nov 22950/23150 bull call): T-07 = 100 x (spread - debit) / (200 - debit), every live value back-solves to a 0.05 tick; fixture `tests/fixtures/alert_discipline/gclive3_2026-11-02_t07.json` (derived % only); expected 1 record per preset vs live 30 / 23 |
| Step 1 core | pure gate `backend/ofo/adjustment/alert_gate.py` replays the fixture: 1/1/1 |
| Step 2 spec | ADR-237 (band base = threshold size, candle close = last value read, record timing, lapse at the band, storage, one writer, cap/quiet); REQ-112/165/170, ADR-235 text |
| Step 3 settings | per-style admin keys (alerts.<style>.*, speeds.background_check_seconds.<style>), presets + style resolver, user cap ceiling (live: cap 8 vs admin 6 refused), migration 0035 pin + GET/PUT alert-style (live: Automatic (now Weekly) -> Monthly -> back), Preferences tables per style with units, 13 new texts pending owner read |
| Step 5 wiring | migration 0036 (held crossings table, `worse` column); the worker opens / holds / lapses only through the gate; the screen check writes nothing; per-style check speed; review fixes (no record from a candle that saw a pause, exit-lapse failure contained, superseded_by_worse reason) |
| Step 6 | three speed settings 10 / 30 / 120 s used by the worker (the old single key removed) |
| S1 #624 | unreadable playbook -> "limits not applied: playbook unreadable"; drawer liquidity flags |
| S2 #633, S3 #628 | closed with API proofs (T-19 A-29 Rs 85.04 = Compare; ADJ-13 history 4 legs + 1 adjustment) |
| S4 | #637 filed (spec_basis_gate ids from other worktrees) |
| ofo_dev | migrated 0034 -> 0036 (owner role, scratch wrapper; additive) |

## PARKED / DEFERRED
- #636 round 4 (memory-only check path): built on build/gcalert1-636r4 5bf1db31, NOT merged; Opus check FIX FIRST (one bad
  replaced settings row stops every check after a restart; stale writes; writer can die silently). Steps 5-6 use the old path.
- #638: three worker tests xfail strict (per-style interval gaps {30, 60} for weekly, plan change, day rollover), not diagnosed.
- #639: screen vs worker spot freshness on a quiet index (screen still uses the 3 s last-change age); dismiss matched by rule;
  first check after a style change waits the old interval.
- Step 7 (live counts) -> GC-LIVE4 draft `docs/process/goal-contract-GC-LIVE4-2026-11-03-DRAFT.md`.

## OWNER ITEMS
- Approve GC-LIVE4 and log in to Kite at or after 09:15 (private window).
- Read: `docs/process/owner-questions-2026-11-02.md` (lapse at the band, information) and the new texts marked "pending owner
  read" in tests/errors/template_pins.json (alert records, held reasons, style pin, limits not applied, superseded_by_worse).
- Not seen in Chrome: 390 px of the Preferences tab and the plan-sheet style picker (window would not resize, screenshots
  timed out) -> GC-LIVE4 A6.

## Process notes (measured)
- The shared ofo_test is at 0030; every DB test must use `db_run_fresh.py` (memory `db-tests-use-db-run-fresh`). Two builders
  lost about a third of their budget to it before the brief named it.
- Every Tier A review found real defects (0035 pin 404 + stored row; #636 cache; 0036 lost escalation; step 5 pause + empty
  list). Builders ran over their 80-call budgets three times.

## NEXT
GC-LIVE4 in market hours; then #638 diagnosis, #636 round 5, #639.
(Gate and push lines are added below at the close.)
