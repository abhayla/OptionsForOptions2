# RESULTS: Lane Q1 (route time outside the price read), 27 Nov 2026

send_message to the coordinator was refused (elevated_session_untrusted_device); status lines are kept here.

## Status lines
- 14:48 IST LANE Q1 ALIVE: branch perf/route-profile-1127 cut from origin/hotfix/api-blocking-1127 (8fe1997).
- 15:20 IST: push 1 prepared (step timing + before table); gate on 094f7ed running; pushed with push 2 if not before.
- 16:05 IST: push 2 prepared at the head of this file's commit: wording-scan memo, latency guards, concurrency harness; parked request memo patch. Gate before push.

Spec basis: REQ-049 AC-4; REQ-170 AC-5; ADR-008. No product behaviour change: same answers, faster.

## Bad news first
(a) One request at a time, with an instant price read, no route is slow here (17 to 80 ms). The PC's 4 to 10 s is not in database queries or compute of a single request.

(b) The two fixes that would save the most are NOT built, because they change answers:
- The margin gather (funds and basket read together). Today's tests pin that a funds failure makes no basket call. D-36 round 2 pins one 8 s bound over the two SERIAL reads, so 0.2 s + 0.2 s reads as "could not be read".
- Skipping `cheapest_offered` (~25 ms of ~35-42 ms compute per check). It is in the reply.

(c) Under concurrency the event loop serialises checks: 10 concurrent plan-watch median 525 / max 756 ms, 20 concurrent 1006 / 1450 ms (before). So the Positions page's one plan-watch per row, plus two testers, plus the background paper monitor (it runs on the API's event loop when LIVE_MARKET is on: `main._lifespan` -> `paper_monitor.start`) is the most likely non-price cause on the PC. Unproven until Monday's log lines.

## What was built (no answer changes)
- 8706a0a: step timing on the request log line.
- d70fe1e: harness.
- 094f7ed: lint.
- 6fe88e0: step_timing failed-statement fix.
- 2a89975: concurrency harness.
- 31074cf: latency guards (`tests_app/test_route_latency_budget.py`). Query ceilings at today's counts 23/19/18/11 as N+1 guards; single route <= 300 ms with instant price; concurrent guard 4000 ms; cold-margin <= 450 ms kept as xfail(strict) until the margin gather is decided.
- 4a91fef: parked request-memo patch (`q1-parked-request-memo.patch`, NOT applied). It saves 4 to 7 local queries, a few ms. It touches stores on the stop and plan paths. Four suites could not be proven on the broken local DB at the time.
- c65ebaf (red test) + e1fd1fe + 9206d40 + 34c26ac: wording-scan memo (`ofo/errors/model.py` `_scan`, `ofo/errors/explanations.py`). 156 wording scans per adjustment-check -> 16 cold, 0 warm. Only an exact-text PASS is remembered; a refusal re-raises every time; the checker identity is still verified first (ADR-056 (1)).

Trade-off for the coordinator: model.py says messages are "Re-checked on every read". With the memo, a repeated text is not re-scanned. Drop e1fd1fe if the literal re-check must stay.

## Before / after
| route | step | before | after |
|---|---|---|---|
| plan-watch, warm single | total / compute | 74.5 / 52.2 ms | 64.4 / 42.3 ms |
| adjustment-check, warm single | total / compute | 68.9 / 52.2 ms | 50.9 / 34.6 ms |
| adjustment-plan, warm single | total | 47.5 ms | 31.0 ms |
| plan-watch, 10 concurrent | median / max | 525 / 756 ms | 460 / 605 ms |
| adjustment-check, 10 concurrent | median / max | 510 / 697 ms | 414 / 542 ms |
| plan-watch, 20 concurrent | median / max | 1006 / 1450 ms | 778 / 1165 ms |
| adjustment-check, 20 concurrent | median / max | 745 / 1178 ms | 782 / 1094 ms (flat, noise) |
| cold margin | total | 1002 ms | 1002 ms (not built) |
| queries (plan-watch / check / plan / levels) | count | 23/19/18/11 | 23/19/18/11 (unchanged) |

Note: ms swing with machine load on a 4-core box. Query counts are exact.

## Test evidence
Base vs after, fresh DB per file.

| Suite | Result |
|---|---|
| test_plan_watch | 7/7 passed |
| test_adjustment_check | 11/11 passed |
| test_adjustment_plan | 22/22 passed |
| test_request_log | 6/6 passed |
| test_outcome_route | 25/25 passed |
| test_route_latency_budget | 6 passed, 1 xfailed |
| test_step_timing_failed_statement | 1 passed |
| test_wording_scan_once | red first (156 scans of 29 distinct texts), then 2 passed |
| tests/errors | 710 -> 710 passed |
| ruff ratchet | OK, no rule rose |
| repo_scan | 1558 passed at 094f7ed (re-run in the gate for the final head) |

## Proposals needing a decision (not built; what each changes)
- (a) Margin read together. Saves ~one broker round trip per cold margin. Changes the funds-failure call count and the D-36 round-2 answer.
- (b) Margin off the request path. The worker keeps each strategy's margin with its "Checked at" time; a request shows the stored figure with its time and never waits on the broker. Changes the freshness of the shown margin and of T-16 % of margin in the route. The worker's own alerts are unchanged.
- (c) `cheapest_offered` computed only when a shown rule needs it, or cached per (legs, chain quote times, plan). Exact if keyed right.
- (d) Implied-volatility solves (~84 per check) cached within one request. Exact. Engine file, needs the options-math review.
- (e) Checks off the event loop (process pool, or the worker precomputes). Design change.

## Design: one request for all Positions rows' plan-watch (not built; touches Lane J/R files)
Route: `GET /api/plan-watch?strategy_ids=1,2,3` (max 20, the user's own only).

Reply: `{as_of, items: [{strategy_id, state: "ok"|"refused", watch: <the PlanWatchOut of today> | null, refusal: <the same refusal body the single route answers> | null}]}`.

Server:
- One auth, one market context, one price snapshot per underlying shared by all rows (Lane U's read door, read once per underlying, not per row).
- Then `run_check` per strategy in turn, with `await asyncio.sleep(0)` between rows so the loop stays responsive.
- One row's failure is that row's refusal (fail closed per row), never the whole reply.
- Same lines, same wording as the single route (ADR-008: the same `run_check`, never a second evaluation).
- The single route stays for the plan dialog.

Page: the Positions page's page-wide plan-watch queue (Lane R) makes one call per 60 s cycle instead of one per row. Each row reads its item by id. A refused item shows that row's refusal text. The 20 s timeout applies to the one call.

Files: `routes/plan_watch.py`, `PlanWatch.vue`, the Positions page (Lanes J/R).

Gain: N HTTP requests and N price reads -> 1 request and one price read per underlying. CPU per check is unchanged, so (c) and (e) still matter.

## PC measuring steps for Monday's open
1. Pull this branch and restart the API only. No frontend build needed.
2. With two testers on Positions + the plan dialog, run for 10 minutes from 09:20 IST.
3. Collect the request log lines (the API's stderr log, where the 27 Nov request log came from).
4. Run this on the log file. It prints, per route, the count and the average ms per step.

```
python -c "import re,sys,statistics as s,collections as c;d=c.defaultdict(lambda:c.defaultdict(list))
for l in open(sys.argv[1],encoding='utf-8',errors='ignore'):
 m=re.search(r'request (\S+) (\S+) (\d+) ([\d.]+)ms(.*)',l)
 if not m: continue
 k=m[1]+' '+m[2];d[k]['total'].append(float(m[4]))
 for n,v in re.findall(r'(\w+)=([\d.]+)ms',m[5]): d[k][n].append(float(v))
for k,v in sorted(d.items(),key=lambda x:-s.mean(x[1]['total'])):print(k,len(v['total']),{n:round(s.mean(x)) for n,x in v.items()})" <logfile>
```

How to read it:
- `price=` large: Lane U's read door.
- `margin=` large: proposals (a) / (b).
- `compute=` large only when many requests overlap: the event loop (proposals c / e and the batch route).
- `db=` large: the parked request memo and the PC's database.

Report the table to the coordinator.

## Task | model
| Task | Model |
|---|---|
| Phase 1: step timing + harness + before table | Sonnet |
| RESULTS draft + first gate pre-check | Haiku |
| Lint fix + gate run | Haiku |
| Phase 2: memo / latency tests / margin attempt | Sonnet |
| Round 2: wording memo + branch rebuild | Sonnet |
| This RESULTS | Sonnet |
| Splitting, routing, verification, decisions (ship the wording memo, park the request memo, do not build answer-changing fixes) | the lane session (Opus) |

No Opus helper was used: no money/stop/exit/price path was changed.

## To file as deferred issues
1. Margin read together: decision needed (pinned tests: test_outcome_margin funds-failure count, D-36 round 2).
2. Margin off the request path, shown with its time.
3. `cheapest_offered` per check (~25 ms CPU on the event loop).
4. IV solves cached within a request (options-math review).
5. Checks off the event loop / worker precompute.
6. Batch plan-watch route (design above; Lanes J/R).
7. The parked request memo (`q1-parked-request-memo.patch`): re-run on a good DB and decide.
8. Local test DB catalogue state: suites that seed with `load_library` fail on a reused ofo_test ("would drop 750 of 750 live NIFTY contracts"); a fresh DB per file is green. A tests_app isolation defect.
9. `db_run_fresh` needs `D:\Abhay\GLOBAL.env`, so cloud lanes cannot use it.

---

## What push 1 adds
- `backend/ofo_app/step_timing.py` (new) and `request_log.py`: every request line now ends with
  `db=<ms>/<n>q price=<ms> margin=<ms> compute=<ms>` (absent steps omitted; a request with no step logs the old line).
  Example (real app, cold margin): `request GET /api/strategies/{strategy_id}/plan-watch 200 1748.9ms db=34.6ms/26q price=510.1ms margin=1002.8ms compute=201.3ms`.
- db: SQLAlchemy cursor events on the app engine (`db.py`). price / margin: the readers are wrapped once at the top of
  `run_check` (`routes/adjustment_check.py`); plan-watch and adjustment-check both go through it. Lane U's price-read line is untouched.
- `tests_app/perf_route_profile.py`: the harness (skipped unless `OFO_PERF=1`; run it only on a throwaway database).

## Before table (instant price read, local PostgreSQL 16, broker margin stubbed at an ASSUMED 0.5 s per call; 1 warm-up + 5 runs)
"warm" = the existing OutcomeMargin cache kept (as in production); "cold" = cleared before each run.

| route | cache | total ms med/max | db ms / queries | price ms | margin ms | broker margin calls (funds+basket) | compute ms |
|---|---|---|---|---|---|---|---|
| plan-watch | warm | 74.4 / 93.0 | 12.4 / 23 | 8.7 | 0.1 | 0+0 | 53.3 |
| plan-watch | cold | 1087.7 / 1108.3 | 13.8 / 23 | 9.3 | 1002.8 | 1+1 | 58.9 |
| adjustment-plan | warm | 44.8 / 52.8 | 10.7 / 18 | 0 | 0 | 0+0 | 33.6 |
| adjustment-plan/levels | warm | 20.3 / 22.4 | 3.1 / 4 | 0 | 0 | 0+0 | 17.2 |
| adjustment-check | warm | 80.5 / 81.6 | 10.5 / 19 | 9.6 | 0.1 | 0+0 | 59.3 |
| adjustment-check | cold | 1082.4 / 1108.4 | 10.0 / 19 | 10.5 | 1002.7 | 1+1 | 62.0 |
| positions | warm | 28.9 / 36.4 | 6.9 / 5 | 0 | 0 | 0+0 | 23.3 |
| paper/strategies/{id} | warm | 16.5 / 21.2 | 5.0 / 11 | 0 | 0 | 0+0 | 11.7 |

Bad news first: one request at a time, with an instant price read, no route is slow here (17 to 80 ms warm). The PC's 4 to 10 s
is NOT explained by database queries or compute on a single request. What is left: (1) the price read (Lane U's fix);
(2) the broker margin read: on a cold or failed cache entry it is two SERIAL broker calls (funds, then basket) under an
8 s timeout, and a failed read is retried after 30 s, so a slow broker costs one request up to 8 s per strategy every 30 s
(this matches the PC's 8.5 s and 10.2 s maxima, unproven until Monday's log line); (3) concurrency: two testers plus one
plan-watch per Positions row plus the background worker on one event loop (measured in push 2); (4) the PC's database link.

## Causes found (ranked; file:line)
1. Margin: `outcome_margin.py:209-235` `_fetch`: funds then basket, serial. Cache key (session, orders) is stable for an unchanged position.
2. Compute: `ofo_app/adjustment_check.py:304` `cheapest_offered` prices ~17 approaches per check (~45% of compute, ~25-30 ms).
3. Repeated reads within one request: plan-watch 23 statements / 17 distinct (strategy ownership + scenario marker twice,
   plan row twice, entry facts twice, catalogue twice); adjustment-plan reads `system_playbook_versions` 3 times; paper book reads the catalogue 4 times.
4. Smaller: 84 implied-volatility solves per check for an unchanged chain (`ofo/engine/chain_values.py:150`); 152 `check_platform_text` calls (~15% of profile).
