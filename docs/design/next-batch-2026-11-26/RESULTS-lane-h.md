STATUS 18:05 | item 1: built, tests green | item 2: measured, no gain, parked | item 3: measured, not material | item 5: built, tests green | next push 19:00 (after Opus review + gate) | blocker: send_message to @parent refused (elevated_session_untrusted_device); this line is the report

# RESULTS: Lane H (speed fixes, same answers), 27 Nov 2026

Branch `perf/speed-fixes-1127` from `origin/perf/route-profile-1127` (093c09c). No PR. Spec basis: REQ-049 AC-4; REQ-170 AC-5;
ADR-008; ADR-330 (13). No answer changed, no migration, no order endpoint touched.

## Bad news first
1. **Batching does not make 20 rows faster on the server.** One batch request of 20 rows took 1333 to 1640 ms; 20 concurrent single
   requests took 1333 to 1417 ms wall. The work is CPU on one event loop (about 65 ms per check), and a batch does the same work.
   What the batch removes is 19 HTTP requests, auths, market contexts and connections, and the pile-up of requests behind each
   other: the first row is no longer the slowest only when it arrives last. Do not promise the owner "2 s for 20 rows" from this.
2. **Moving the check off the loop to a thread gains nothing (measured twice, reverted).** State_of (about 30 ms of pricing every
   approach) in `asyncio.to_thread`: 20 concurrent plan-watch median still 0.94 to 1.02 s, event loop still held up to 41 ms at a stretch
   (old 41 to 48 ms). The GIL: a thread shares the one interpreter. A process pool would give real parallelism but: `ExpiryModel`
   (frozen) does not survive pickling (`AttributeError: ExpiryModel is immutable` on unpickle, tried), and on the owner's Windows PC
   each worker is a spawned process that imports the whole app. At best it halves 20 checks (the other ~35 ms per check is request,
   database and reply work that stays on the loop). Parked: see "To file".
3. The 6 to 20 s the owner saw is NOT explained by anything measured here (one check is 60 to 100 ms; 20 together 1.4 s). It must be
   the price read (Lane U) or the broker margin read (Q1: cold margin 1 s per strategy, 8 s bound). Monday's log lines decide.

## Fix table (before / after, local PostgreSQL 16, instant price, warm margin; `perf_route_profile.py -k concurrency`, 2 runs each)
| fix | before (median / worst per request; wall) | after | how |
|---|---|---|---|
| 1 batch route `GET /api/plan-watch?strategy_ids=` | 10 concurrent plan-watch: 629 / 837 ms; 20: 934 / 1330 ms (wall 1333) | ONE request, 10 rows: 609 to 781 ms; 20 rows: 1333 to 1640 ms. HTTP requests 20 -> 1. Statements for a one-row batch 23 (= single route, guarded). | `routes/plan_watch_batch.py`; the single route's whole answer is now `plan_watch.watch_of`, called per row (same lines, same wording). |
| 2 check off the loop (thread) | 20 concurrent plan-watch median 934 to 1024 ms; loop held max 41 / p99 26 to 46 ms | median 940 to 1025 ms (same); loop held max 41 / p99 26 to 35 ms: NO GAIN | REVERTED, not shipped. |
| 3 paper monitor share | not measured before | step 0.021 ms x 2 per second = 0.004 % of the loop; its 60 s reload 4.4 ms = 0.007 % | `perf_monitor_share.py`. NOT material: nothing to move, nothing proposed for Lane J2. |
| 5 `POST /api/playbooks/test` connection held across broker reads | 1 pooled connection held for the whole read wait (test red first) | 0 held | `_tested`: read the legs first (one by one, the only DB reads of the outside part), `release_connection(db)`, then the bounded broker reads. |
| guards | single <= 300 ms, 10 concurrent <= 4000 ms | single <= 200 ms, 10 concurrent <= 2500 ms (measured 60 to 100 / 600 to 840 ms); new: batch statement ceiling | `test_route_latency_budget.py` |

Same-answer proof (item 1 refactor; item 2 reverted so no change there): `tests_app/perf_reply_dump.py` writes the full replies
of plan-watch, adjustment-check, adjustment-plan and the batch for the armed ADJ-01 strategy; base build vs this build:
`diff` empty except the database timestamp `accepted_at` (the plan's seed time). `test_plan_watch_batch.py` compares each batch
row to the single route's body field for field, and the batch refusal of an unknown strategy to the single route's 404 body.

## What was built
- `backend/ofo_app/routes/plan_watch_batch.py` (new): `GET /api/plan-watch?strategy_ids=1,2,3`, 1 to 20 ids (repeats answered once; anything else 422), the caller's own strategies only (another's = that row's 404, as the single route). Reply `{as_of, items: [{strategy_id, state: "ok"|"refused", watch, refusal, status}]}`. One bad row is that row's refusal (and the shared session is rolled back so the next row works). Rows run in turn with `await asyncio.sleep(0)` between them. Writes nothing.
- `plan_watch.py`: `watch_of(...)` extracted from the route (the route now calls it). `errors.py`: `row_answer(exc, where)` = the message and status `handle_error` would answer (user-facing error, HTTP error, busy store, internal with reference).
- `main.py`: router registered. The single route stays for the plan dialog.
- `frontend/src/lib/planWatchBatch.js` + `frontend/tests/plan-watch-batch.test.js` (3 tests, eslint clean): `readPlanWatchBatch(ids)` -> Map id -> the same view `readPlanWatch` gives (ok / not_found / failed / unavailable); one request, 20 s timeout; never throws; a failed request fails every id.
- `playbooks.py` item 5, `test_playbook_test_pool.py`.
- Harness: batch measure, loop-held ticker, `OFO_PERF_SLOW` stack sampler in `perf_route_profile.py`; `perf_reply_dump.py`; `perf_monitor_share.py` (all skipped unless `OFO_PERF=1`).

## For lane V (exact page change; I did not edit PaperStrategies.vue)
Lane R's page-wide queue (`lib/planWatchQueue.js`, on `hotfix/plan-watch-load-1127`, contained in `hotfix/plan-save-1127`; NOT in my base: `git merge-base --is-ancestor` says no) runs one read in flight and compact reads 20 s apart. With the batch route the Positions page needs ONE read per cycle:
1. In `PaperStrategies.vue`, once per 60 s cycle (and on first mount), call `readPlanWatchBatch(rowIds)` (import from `@/lib/planWatchBatch`) with the ids of the rows that show a Plan watch box, at most 20 (`PLAN_WATCH_BATCH_MAX_ROWS`; chunk by 20 beyond that), through ONE `submitPlanWatchRead('positions-batch', 'compact', run)` job (the queue stays: it already keeps one read in flight).
2. Hand each row its view: pass `:view="views.get(String(row.id))"` to `PlanWatch.vue` (add a prop `view`; when it is given the box does not call `readPlanWatch`/the queue itself; the builder's full box keeps its own single read). A row with no entry shows "Reading the plan watch..." (view null), as today.
3. A refused row shows its own text (`view.text`); the other rows are unaffected. Keep the `stale` handling as is.
4. Do not compute or compare anything in the page (ADR-008).

## To ask the owner (items I did NOT build: they change answers)
1. **Read funds and basket together for a cold margin.** The trader sees: on a funds failure today NO basket call is made and the margin reads "could not be read" after the funds failure; together, both calls are always made. D-36 round 2: funds 0.2 s then basket 0.2 s under one 0.3 s bound reads "could not be read" today; together it would read "read". Measured gain: cold margin 1002 ms -> about 500 ms per strategy (stub 0.5 s per broker call; the real broker time is unknown until Monday). Recommendation: yes, but only after Monday's `margin=` figure shows broker time is the cost (Q1 log reader); then build with the owner pinning both answers.
2. **Skip `cheapest_offered` (T-19 "cheapest approach") on checks where no shown rule needs it.** The trader sees: the T-19 line's approach and cost would be absent on Plan watch (it is in the check's reply today, ~25 ms of ~35 to 42 ms of compute per check). Measured gain: about 25 ms per check on the loop; for 20 rows about 0.5 s. Recommendation: no for the adjustment-check (it is shown there); yes for plan-watch only if plan-watch never shows T-19 (it shows lines, not that figure): needs a one-line check of which lines read it before building.
3. (from item 2) **Run the check in a process pool.** Gain at best about 2x on 20 concurrent checks; cost: Windows spawn (each worker imports the app, +3 processes of memory), `ExpiryModel` and other frozen models need pickling support. Recommendation: not now; the page-wide queue plus the batch already ask for 1 request per cycle, so concurrency stops being the shape of the load.

## Monday measurement, check T2-16 (two testers, live market)
- Two testers on Positions (the batch page change from "For lane V" in place) plus one plan dialog, 10 minutes from 09:20 IST. Time `GET /api/plan-watch` and `GET /api/strategies/{id}/plan-watch` to the second from the request log line. **Target: under 2 s** for the whole list (and the log line's `price=` and `margin=` steps listed beside it: if either is above 1 s the cause is Lane U / the broker, not this lane). Q1's log reader (RESULTS-lane-q1.md) prints the average per step.
- Market-closed PC step that counts requests per page load: open Positions with at least 5 rows that have a plan, with the browser's network tab filtered on `plan-watch`: expect ONE `GET /api/plan-watch?strategy_ids=...` per cycle and no `/strategies/{id}/plan-watch` for those rows (today: one per row). Also `grep -c "request GET /api/plan-watch" <api log>` after one minute: 1 (not N).

## Tasks (model / minutes)
| task | model | minutes |
|---|---|---|
| Baseline harness, batch route, refactor, tests, measurements, items 2, 3, 5, frontend module, this file | Sonnet (this session) | about 75 |
| Independent review of the plan path before push | Opus helper (Why Opus: plan path and refusals) | 7 |
| Gate run | Sonnet (this session) | about 43 |

## To file as deferred issues
1. Process-pool the check (needs frozen models pickleable; Windows spawn cost); measured: threads give nothing.
2. Page change for the batch route (Lane V, section above).
3. `_ids_of` tolerates blank entries in `1,,2` (answers `1` and `2`); tighten if the page could send them.
4. Batch shares one price read per underlying: NOT built (each row still reads prices; the single route's reads are Lane U's and N's); gain unmeasured, price reads were 9 to 15 ms each here.
5. The seed gives ONE strategy per scenario, so the concurrency harness's "ten strategies" are one strategy asked ten times (Q1's harness, kept as is; numbers are still the right CPU load).
6. Opus review (PASS, 5 minor): fixed the stale comment and the missing 422 case in `row_answer`. Left: (a) the legs read of `POST /api/playbooks/test` is no longer inside the 8 s bound (a DB read; only a leg reader slower than 8 s answers differently: checked instead of left out); (b) a batch row's 503 loses `Retry-After: 60` (the page waits its own cycle); (c) a failing `rollback()` fails the whole batch (fails closed); (d) one shared margin read covers every row (fails closed); missing tests: row A raising a busy-store error with row B equal to the single route; 409/503 rows equal to the single route; a slow leg reader.
7. Test DB isolation (Q1's item 8) hit again: two plan-watch test files in one pytest run share armed triggers (`_arm` twice -> 4 leg stops). Run one file per fresh database.
