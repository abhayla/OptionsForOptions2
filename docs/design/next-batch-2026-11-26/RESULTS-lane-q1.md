# RESULTS: Lane Q1 (route time outside the price read), 27 Nov 2026

## Status lines (send_message to the coordinator was refused: elevated_session_untrusted_device; lines kept here)
- 14:48 IST LANE Q1 ALIVE: branch perf/route-profile-1127 cut from origin/hotfix/api-blocking-1127 (8fe1997).
- 15:20 IST push 1: step timing on the request log line + measurement table (head: see git log). Fixes follow by 20:00 IST.

Spec basis: REQ-049 AC-4; REQ-170 AC-5; ADR-008. No product behaviour change: same answers, faster.

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
