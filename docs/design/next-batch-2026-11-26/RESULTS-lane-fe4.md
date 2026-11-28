STATUS 14:10 | items 1-3 built, gate running, Opus review pending | next push after review | blocker: none

# Lane FE4 results (28 Nov 2026)

Base: origin/fix/r3-worker-3-1128 (2f9694e8d). Branch: fix/r4-worker-4-1128. Paper only; no broker call.

## Core / Proof (item 1)
Core: the worker publishes the reason `market_closed` and the reader's sentence key is `market_closed`.
Proof: `tests_app/test_reasons_fe4_1128.py::test_core_...` was RED before any change (`AttributeError: module 'ofo_app.monitoring_state' has no attribute 'sentence_code'`, 27 failed in the file), then green (`26 passed`). Regression: see Evidence.

## Item 1 (review N2)
The review named "monitoring_state's compose". The compose that words the pause is `routes/monitoring_status.py` (Lane FD4's file, not mine): it reads only `e.reason`, never `e.why`, so `stale` + `index_not_live` reads "The last price is too old". In my file I added ONE function, `monitoring_state.sentence_code(entry)`: the monitor's `why` (one of the seven codes) wins over the generic reason it rides on; else the worker's reason (the ten codes a pause can carry, incl. `market_closed`, `expiry_kind_unknown`); anything else (a free-text why, an unknown or blank reason) gives `unknown` ("Not being watched: the reason is not known."), never blank, never another reason's sentence. Pinned: every PriceState pause and every why travels `encode` -> `decode` unchanged; every key has a catalogue sentence.
Not enough on its own: the route must call it (For the owner lane 1).

## Item 2 (review N3)
`_index_pass` called `_report_not_applicable` only in the market-open branch; with the market closed (or no feed) a real position's old armed stop read watched. Now the call is made once, after the branches, for every branch. Tests `test_na_closed_fe4_1128.py`: closed after 16:00 and on a Saturday were red (2 failed), now green; a paper trade is never called not applicable; open market unchanged.

## Item 3 (issue 876, T1-06)
Test `tests_app/test_t106_fe4_1128.py`: worker as a separate OS process, real PostgreSQL; plan (system rule list, "Loss reaches 5 %") saved at frame 0 (11:40), one minute before the loss; no style pin; 27 triggers (13 on here; the PC stored 14 on, which one is not in the stored facts); loss about 10 % (9.9641) from 11:41, held to 11:56 (15 minutes).
| Code | Result |
|---|---|
| my head | NOT reproduced: one open T-06 row at 11:41 (threshold 5, value 9.9641), still exactly one at 11:56, no "no alert preset"/"no_preset" line, no order placed. 1 passed |
| Friday 206a9f0 (worktree `/tmp/friday`, harness, PATH fixtures and this test copied in; removed after) | NOT reproduced: 1 passed. Caveat: harness and fixtures are ported, the Friday code under test is unchanged |
Cause: unknown. No fix commit to name: nothing was broken for this input on either head. What the test cannot cover: the PC's real stored plan body (which 14 triggers), the real strategy's kind/expiry, a real feed's tick gaps. Evidence to ask for: the worker log for strategy 207 (`no alert preset`, `check skipped`) and the stored plan body. Lane FE3's reading still stands: the only silent-skip path on Friday was an unknown kind (`StyleRefused`), which logs, and the PC saw no log line.

## Item 4 (FE3 "Not done" in my files)
F7 (non-atomic HGETALL/HDEL of slots older than an hour): not changed; a clean fix is a Lua script, which the bare test doubles cannot run, and it needs a monitor stalled an hour. F8 (restored pause starts of a deleted trade): not changed; the worker cannot tell a deleted trade from one not yet answered, no reader sees the row. Both stay under "To file".

## For the owner lane
1. **Lane FD4 `routes/monitoring_status.py`** (needed for item 1 to show on screen): in `compose` replace `code = e.reason if e.reason in _WHY else "unknown"` and the `EXPLANATIONS` guard by `code = ms.sentence_code(e)`; keep the `f"monitoring_why_{code}" not in EXPLANATIONS` -> `unknown` guard; `_WHY` can go. Add a route test: an entry (`stale`, why `index_not_live`) reads `monitoring_why_index_not_live`; (`paused`, `market_closed`) reads "The market is closed.".

## Decided for the owner
1. `why` beats `reason` when it is one of the seven known codes. Spec basis: REQ-115 AC-4 (the pause names its true reason). A free-text why never becomes a sentence key (it can carry anything).
2. `unknown` for an unknown reason: "Not being watched: the reason is not known." (fail closed, never healthy). Spec basis: ADR-016 to ADR-019.
3. Test shape for 876 keeps 13 triggers on, not 14: the stored facts do not say which trigger the PC had extra on.

## Question for the owner
None.

## New wording for the owner to read
None (all sentences exist).

## To file as deferred issues (not filed by me)
- F7, F8 (above).
- Issue 876 cause unknown: needs the PC's worker log and stored plan body of strategy 207.

## Not done
- F7, F8. Cause of 876. Route half of item 1 (not my file).
- Opus review: see the section below.

## Opus review
(pending at this STATUS)

## Evidence
| Claim | Evidence |
|---|---|
| Item 1 core red then green | before: `pytest tests_app/test_reasons_fe4_1128.py`: `27 failed` (no `sentence_code`); after: `26 passed` |
| Item 2 red then green | before: `2 failed, 2 passed`; after with 3 older files: `18 passed` |
| Item 3 | `test_t106_fe4_1128.py`: `1 passed` on my head and on 206a9f0 |
| Regression | `pytest -c pytest-app.ini` over test_worker_j3, test_monitoring_state, test_monitoring_status_route, test_paper_monitor, all `*fe2_1128`, `*fe3_1128`, `*fe4_1128`, test_stop_fired_message: `210 passed` |
| Gate pieces | ruff on changed files clean; `ruff_ratchet.py` OK (no rule rose); `pytest tests -m repo_scan`: 1642 passed, 2 skipped, 47 xfailed; select + broker-name tests: 141 passed |

## Tasks, models, minutes
| task | model | minutes |
|---|---|---|
| build, tests, DB set-up | Sonnet | 40 |
| review items 1 to 3 | Opus | (running) |

## PC steps (paper only)
Market closed: pull the branch; `tests_app/test_reasons_fe4_1128.py`, `test_na_closed_fe4_1128.py` one file at a time through `scripts/orchestrator/db_run.py`. Live: with a real position's old armed paper stop and the market open or closed, the trade reads "Not being watched: a real position has no paper stop" once the owner lane wires `sentence_code` into the route.

SAFE TO CLOSE: not yet (review pending).
