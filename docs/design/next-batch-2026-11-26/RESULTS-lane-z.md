STATUS 00:55 | round 1: build = M3's integration/conflicts-1127 8ca36525 + test/worker-chain-1127 e3cf60b0; serial gate on this head running; app suite on PostgreSQL NOT proven in this container; not tagged | merged: everything in 8ca36525 (plan-read-2, worker-join c1eb7a67, builder-open, exit-all, order-door-2 with K and N, page-handovers, stop-follows-leg, last-close with migration 0059, plan-save and plan-watch, live-test-small, alert-screens) and worker-chain | left out: hotfix/worker-2-1127 (not on origin) | tag: none yet | hard condition: worker-chain test 10 passed against PostgreSQL (see below) | blocker: send_message to the coordinator is refused; this line is the report

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
