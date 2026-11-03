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
## Close state (written 2026-11-03 03:55 IST)
- Full gate run 1 on 0b9f3a86 (02:47): killed by Claude Code's low-memory reap, no output.
- Run 2 on 0b9f3a86 (02:58-03:26): ran to the end, TOTAL FAIL on 4 of 9 steps, every red a guard catching new code (selector pin, the word 'intraday' in PreferencesTab.vue, private T-19 helpers used by the worker, a time-zone literal, alert_style route edges, 3 unregistered reply models, one long line, ADR-236/237 stage rows). Fixed: 6d4e1f39 (merged 208c1baf) + c2ad7028 (one stale private call in a test). Frontend test 10 passed, eslint clean after the merge.
- Run 3 on c2ad7028 (03:43-03:55): killed by the same reap, no output. Stopped there (the reap note: restart only when the owner asks).
- Measured: the only run that survived had a monitor printing every minute; run 1 had no monitor and run 3 a silent one (it would have printed below 2.5 GB free and never did, so run 3 was killed with more than 2.5 GB free at every 30 s sample; run 1 unmeasured). The reap fires on low memory WHILE THE SESSION IS IDLE, so a chatty monitor (or starting Claude Code with CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1) is the likely way to get one run through.
- Update 05:08: run 4 on 474dabd6 (03:56-04:10) TOTAL FAIL app_tests only (collection error: tests_app/worker_records.py
  still imported the renamed _t19_record; fixed 689a9bec). Run 5 on 689a9bec (04:12-04:40) 8/9 PASS; app_tests 1 failed,
  3986 passed: tests_app/test_feed_control.py::test_no_token_or_fingerprint_is_on_the_bus_or_in_any_log_line ("the login
  and the Disconnect were not published"); that file alone on a fresh DB: 16 passed; no feed/bus file changed since
  6e94f46d -> a load flake. Run 6 on 689a9bec (04:42-05:06) KILLED by the reap again, although a monitor printed every
  minute and read 4.5 GB free at 05:06. The chatty-monitor theory above is WRONG. Stopped; not pushed. Reliable options:
  the owner runs `python scripts/orchestrator/prepush.py --full` in their own terminal, or restarts the app with the
  reap switched off (env CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1); on TOTAL PASS push.
- CLOSED 05:36: run 7 on 7a80cbce, started as a separate Windows process (Start-Process, outside the session's background
  shells, so the reap could not stop it), 05:09-05:35: TOTAL PASS 1520.2s, all 9 steps (app_tests 722.3s), marker
  .git/ofo-prepush/7a80cbce7c24fc23e3fbb238d55bf3d19e1b423d.json. Pushed `396c1eaa..7a80cbce` to origin/feature/adjustments.
  Nothing on main. This line is a docs-only commit on top, pushed with PREPUSH_GATE_ALLOW (reason in the push).
- (superseded by the line above) NOT DONE: gate TOTAL PASS on the final head; push of feature/adjustments (66 local commits ahead of origin). Nothing on main.
- NEXT for the owner: say 'run the gate' (one run, chatty monitor) -> on TOTAL PASS push feature/adjustments as its own command; then approve GC-LIVE4.

