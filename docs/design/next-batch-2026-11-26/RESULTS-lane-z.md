STATUS 02:25 | round 1: build 016163439c8d gated TOTAL PASS and pushed; tag weekend-r1 made LOCALLY (annotated) but git push of a tag is refused by this container (HTTP 403): coordinator or owner pushes it, or the PC takes sha 016163439c8d from integration/weekend-1127 | Opus review of stop/exit paths = REVISE (F1, F2, F3 below) | merged: M3 integration/conflicts-1127 cdce22ce + worker-chain e3cf60b0 | left out: hotfix/worker-2-1127 (not on origin) | hard condition: worker-chain 10 passed on PostgreSQL | blocker: tag push 403; send_message refused

# Lane Z (weekend build 1127), working notes

## Results so far
| Check | Result |
|---|---|
| Base 206a9f0 full gate | TOTAL PASS (2429 s) |
| Build c9f95935 (my first build) full gate | TOTAL PASS (2264 s), pushed |
| Build 23b71600 (c9f95935 + M3 group 1 + worker-chain, plan-read-2, builder-open, two strict-xfail marks removed) serial gate | TOTAL PASS (2378 s), pushed |
| Migration 0059 | 0057 to 0059 to 0057 to 0059 on a scratch database, `alembic heads` prints one head `0059_last_close` |
| Hard condition (crossed plan stop on a fresh trade gives an alert, worker as a separate process) | `tests_app/test_plan_stop_worker_chain.py` (Lane Q3): 10 passed against PostgreSQL 16, 6 min 51 s, on this build |
| App suite on PostgreSQL, whole `tests_app/` | NOT PROVEN here (see PostgreSQL) |

## Merge notes
- The two strict expected-fail marks I removed earlier (the freeze-limit parity row and the 08:07 reload test) are reverted in this build: Lane M3's merge brings the same removals, and two edits of the same lines conflicted. I did not resolve a test conflict; I reverted my two commits and merged M3 clean.
- Document conflicts kept both sides: RESULTS-lane-j.md, RESULTS-lane-r.md, knowledge/findings/INDEX.md (regenerated with scripts/orchestrator/regen.py). screen-inventory.json is regenerated with `node frontend/e2e/support/inventory-extract.mjs`.
- Lane J2's Opus review of the joined stop worker (903a0f30): PASS with 6 minor findings (top of RESULTS-lane-j2.md). Lane M3's own Opus reviews (group 1 and group 2) passed with no critical or major finding (RESULTS-lane-m3.md).
- My own Opus review of the joined stop and exit paths against the base is NOT done yet (not started by the budget cut of round 1).

## PostgreSQL in this container
- The cluster once stopped with no shutdown line, no out-of-memory line and no crash in its own log (the next start said "Removed stale pid file"). The session had resumed (the harness showed a resume hook), which kills the processes started in the container. Memory was never the cause (about 14 GB free). `runapp.sh` (scratchpad) wraps a suite so it stops within 15 s if the cluster stops and writes the cluster state and log tail first.
- Aborted runs leave rows in the test database (a "would drop 750 of 750 live NIFTY contracts" refusal in later tests, and one test hung 21 min on an advisory lock held by an idle transaction): drop and recreate `ofo_test`, grant `ofo_app`, upgrade to head, before every run. Never run two suites, or a suite and a single test file, on the same database at the same time (a "playbook name 'Mine' taken" error came from my own concurrent runs).
- The whole-suite run fails in this container from about 21% on and then hangs; the first failing group (`tests_app/test_adjustment_held_timeline.py`, via `tests_app/test_strategy_store.py::_with_draft` catalogue update) fails identically on the bare base 206a9f0 here. The files before it pass alone, and `test_adjustment_approaches_route.py` passes alone (108 passed). Not yet tried: CI's flags (`-m "not full_chain"`, a Redis service, `-rs`). Treat the whole-suite result of this container as environment-caused until proven otherwise.
- A gate run with its four parallel jobs while a suite runs makes `frontend/tests/paper-leg-readers-guard.test.js` time out at 15 s (it passes alone in 5 s). Run the gate with `--jobs 1` and nothing else on the machine.
## Independent Opus review of the joined stop and exit paths (build 01616343) — verdict REVISE (DO NOT SHIP)
Why Opus: the stop and exit paths move money (a wrong answer costs real money on a live-test day). Reviewer type: reviewer, model opus, read-only, in its own checkout; it attacked first (scratch scenarios against `alert_gate.step`, constructed races), ran no database tests and made no edit.

| # | Severity | Where | What | Owner (not mine to fix) |
|---|---|---|---|---|
| F1 | major, blocks | StrategyBuilderPage.vue `decideUnknownExit`, `EARLY_MS = 5000` | after an UNKNOWN exit outcome the page says "not stored" and unlocks Exit if the trade looks unchanged 5 s after the client gave up; the server can still commit later (client timeout 10 s, statement timeout 30 s, pool wait up to 30 s, no idempotency key): a second per-leg partial Exit commits too (2 of 4 lots twice = 4 lots). Full-leg and Exit all are protected by EXIT_EXCEEDS_OPEN. Against ADR-017 | V / U2 (exit page) |
| F2 | major, blocks unless the Stops panel already shows it | background.py `_read_with_either_spot` vs paper_monitor.py `on_quote` | the REST index stand-in makes the worker read FRESH and publish "watched" while the feed's index tick is silent; the paper monitor's index exits fire only on feed ticks and have no REST fallback: a crossed index exit never fires, no "exit not run" line, monitoring says watched (23 Nov case: NIFTY tick stops 15:15:18) | J2 / U |
| F3 | major, blocks | routes/paper.py:1458-1460 with PaperConfirmDialog.vue:186-198 | the stop cancel when a leg is moved is correct (same transaction, only closed contracts, never an open leg's stop) but the user is told through two failable reads; the 201 reply names no cancelled stop: on a slow or failed read the new leg has no stop, no offer and no line | U (stop-follows-leg) |
| F4-F8 | minor | paper_leg_stops.py; builder page; stop_lines.py; spec | old orphan leg stops can revive; move wording after an unknown outcome; refused attempt shows no sentence; mixed plan rules alert more; ADR-330 points (39)...(64) are only on other branches | — |

(a) no crossed plan stop or leg stop is dropped silently except the index-exit gap F2; (d) no path fires a plan stop at a wrong price; (e) every one of Lane M3's hand-merge rows S1-S6, W1, W2, W6 kept both sides' intent (W3-W5 not read in detail).

Lane N's four guard-list entries: reach_check ENTRY_MODULES + ofo_app.last_close_store ACCEPT; REVIEWED_RAW_IDENTITY last_close_store.py ACCEPT (minor: move the seed code into its own module so a future raw identity read in the product code is not hidden); PR241 selection pins of two test files ACCEPT; price-read EXEMPT adjustment_readers._index_value_not_live ACCEPT (minor: through `record_basket_facts` the stale value becomes the adjustment rules' starting point without its time).

Not covered by the review: routes/alerts.py handlers beyond the diff, the screen-side gate caller, PaperStops.vue beyond the diff, the Positions-page exit dialogs.

# THE PULL ORDER FOR THE PC (tag weekend-r1; paper only, market closed)
The PC's local test branch `test/screen-2026-11-27` is NOT on origin (kept in a git bundle on the PC). Keep it; never reset it.
0. Check the database link first (it reconnects by itself in about 10 s; look anyway).
1. Backup: a verified database backup of the production database, before anything else.
2. `git fetch origin tag weekend-r1` then `git checkout -b test/weekend-r1 weekend-r1` (a new local branch; the old branch stays exactly as it is). Confirm: `git describe --tags` prints weekend-r1 and `git rev-parse --short HEAD` equals the sha in the tag note.
3. Migration 0059 (one table `last_close`, grants on that table only, no change to any existing table; old code runs unchanged with the table present, new code on an un-migrated database serves "not available"; migrate-first and migrate-last are both safe). `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`; `alembic heads` prints one head, `0059_last_close`. Proof run here: 0057 to 0059 to 0057 to 0059 on a scratch database.
4. Lane N's one-time seed, BEFORE any restart (expected 17 rows: 15 open contracts + NIFTY 50 + SENSEX): DB tests `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_migration_0059_last_close.py tests_app/test_basket_facts_unheld_index.py tests_app/test_close_freeze_routes.py tests_app/test_closed_label_route.py` (all pass); dry run `set PYTHONPATH=backend` then `python -m ofo_app.last_close_store seed D:\Abhay\Ventures\ofo-snapshots\close-2026-11-27.json --check` (expect "would write 17", "skipped 0"; the "database:" line must be the production database; if a field is reported twice re-run with `--map price_at=<key>` or `price=`); real run without `--check` (expect "written 17", "unchanged 0", "skipped 0"; a second run prints "written 0", "unchanged 17").
5. Restart order: API, then worker, then feed. After the API restart, within 30 s open each screen: the banner "Market closed. Prices are from 27 Nov 2026, ..." and the stored close figures. Restart the API again: the same figures, read from the table.
6. The PC's own results branch (local `test/screen-2026-11-27`, head bdb0d126) is pushed only AFTER it has the tag merged or its findings index regenerated (`python scripts/orchestrator/regen.py .`), and only with the repo's pre-push gate, never with a bypass.

## Tag note (first line and lists; the full text is the annotated tag weekend-r1 in the builder's container, copy in /tmp/claude-0/-home-user-OptionsForOptions2/d7c65540-fe45-5d06-b4a4-0517c71a34d6/scratchpad/tagmsg-r1.txt)
weekend-r1 (016163439c8d, 28 Nov 2026 02:15 IST): OPUS REVIEW OF STOP/EXIT PATHS = REVISE (F1 unknown-exit unlock, F2 index exit not watched on REST stand-in, F3 moved-leg stop told only by failable reads): market-closed PC checks only, paper only

1. In the tag: Lane M3's integration/conflicts-1127 cdce22ce (= my c9f95935 build: worker-join, maxloss-line, route-profile, live-day-gaps, pnl-totals, live-test-small; plus exit-all, speed-fixes, plan-door, order-limits + last-close with migration 0059 + order-door-2, stop-follows-leg, plan-save + plan-watch + plan-read, alert-screens, plan-read-2, builder-open, page-handovers, worker-join final c1eb7a67) and test/worker-chain-1127 e3cf60b0. Left out: hotfix/worker-2-1127 (Lane J3, not on origin).
2. Tests: pre-push gate TOTAL PASS (serial, 2247 s) on this head; base 206a9f0 also TOTAL PASS. Hard condition: tests_app/test_plan_stop_worker_chain.py 10 passed against PostgreSQL 16 (6 min 51 s) at b87f2f6b, same product code as this head. The whole tests_app suite on PostgreSQL is NOT proven in the builder's container (fails there from about 21 percent on and fails identically on the bare base); the app step of the gate (no database) passed. Migration: alembic heads = one head 0059_last_close; 0057 to 0059 to 0057 to 0059 proven.

# THE PULL ORDER FOR THE PC (tag weekend-r1; paper only, market closed)
