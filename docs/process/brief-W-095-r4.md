# Builder brief: W-095 round 4 - judge database-stamped facts on the database clock; real margin replies (Tier A: order path)

Core: `tests_app/test_execute_route.py::test_core_real_order_entry_then_exit` GREEN on the real data (strategy id 1,
a real Pro grant recorded through `entitlement_store.append`, ENTRY -> BUY 65 LIMIT 3.35 OFS1V1L0, plan 1 closed filled
{OFS1V1L0: 65}, EXIT -> SELL 65 LIMIT 3.30 OFS1V2L0, plan 2 closed exited {OFS1V2L0: 65}, third EXIT refused at net 0).
Proof: that DB test, run once through the main checkout's `db_run.py` with your worktree as cwd; shared DB ends at
`0015_audit_broker_allowlist` read from the main checkout.

Independent investigation (fresh Opus, 2026-10-17 ~07:50 IST, after the 2nd failure of the class "the core cannot
reach a passing ENTRY"): read its findings below; this round is built AROUND them.

RCA: the route compares facts the DATABASE stamped (a Pro grant's `granted_at`, ADR-023 trusted clock, refused if more
than 60 s from the database's clock; the instrument load's `last_seen_at` = `clock_timestamp()`) against the request's
pinned market clock (`req.now`, 2026-10-16 15:07:21 in the test). In production they agree; with a pinned market clock
every database-stamped fact reads "not yet" / "stale". Separately the test's hand-built basket-margin reply lacks the
fields `required_from_basket_reply` needs (`margin_gate.py:136-141`).
Class: every comparison in the Execute route between a database-stamped time and `req.now` - before 2
(`_pro_entitled` via `access_at(ledger, req.now)` at execute.py:431-436; `_data_health` list freshness vs `req.now`'s
date); after 0 (both on the database clock: `SELECT clock_timestamp()` and its India date). `as_of` for market data
stays the request clock.
Proof: unit tests - a grant stamped on the database clock is Pro while the route clock is pinned to a past day; a list
loaded "today" by the database clock is healthy while the route clock is pinned to yesterday; plus the core test.

Tier: A. Model: opus.
Why Opus: the fourth round of a Tier A item after an independent investigation; clock-source decision in the order path.
Budget: 45 min wall-clock, 48 tool calls. HARD limit: at call 45 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, the core test's result line,
the final `alembic current` read from the MAIN checkout.
Copy from: none - fixes inside this item.
Findings checked: setting-read-from-two-sources, wall-clock-assertion-flakes-under-load, date-stamp-typed-from-memory,
repo-wide-scan-outside-targeted-tests, branch-migration-tests-move-shared-db
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- ADR-023 (entitlement times are stamped by the trusted database clock; a client-supplied time is refused).
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order; the user cannot change a price, quantity or contract on Kite's page."

## Do (the investigator's list)
1. `git fetch origin && git checkout -B w095-r4 origin/build/W-095-execute-route && git merge origin/main` (the branch
   name is held by round 3's old worktree; push with `git push origin HEAD:build/W-095-execute-route`).
   Round 3's builder left an UNCOMMITTED grant attempt in its own worktree - ignore it; start from the branch.
2. `_pro_entitled`: `access_at(ledger, <database clock_timestamp()>)`; unit test as in Proof.
3. `_data_health`: instrument-list freshness on the database clock's own India date (not `req.now`, not the pinned
   `database_today`); unit test as in Proof.
4. Core test: a real grant through `entitlement_store.append` (granted_at = database now) as the app role inside the
   test's rolled-back transaction - never a disabled trigger or a backdated row.
5. Replace `_basket_reply`: EXIT uses the REAL reply `fetch.json` key `margin_raw` (D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json;
   SELL 65 @ 3.30, `final.total` -214.5 -> required 0) copied verbatim into `tests/fixtures/kite_replies/margins-basket-exit-150717.json`
   with a README row; ENTRY uses that same shape with the recorder's 354.25 total from `basket-121848.json`, saved as
   `margins-basket-entry-derived.json` with a README row saying it is DERIVED (no raw entry reply was recorded; Kite's
   real figure at 3.35 would be about 217.75 - 354.25 is an upper bound). Funds 1003 for entry, 671.5 for exit (the
   real `funds` / `margins-122104.json`). Update the folder's file-count test.
6. Tighten: the "flat 15:10 book" EXIT assertion asserts the reconciliation-mismatch text, not only 409; the ENTRY
   re-press asserts the open-plan refusal text.
7. Before push, each as its own command: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py tests/engine/test_pricing_scan.py`,
   `python scripts/ruff_ratchet.py`; then the ONE DB run (upgrade, `tests_app/test_execute_route.py`, downgrade to
   0015, `current` from the main checkout). Commit everything; `git status` must be clean before you report. Push.

## Investigator's findings (verbatim summary)
(a) ENTITLEMENT: route checks Pro at the pinned time (execute.py:431-436); grant active from `granted_at`
(entitlements/engine.py:202-219); DB refuses `granted_at` > 60 s off its clock (ADR-023) -> check Pro at the DB
clock. (b) MARGIN: `_basket_reply` builds an orders list holding only a zero total, without tradingsymbol/exchange/option_premium ->
`kite_margin_no_figure`; real `margin_raw` parses (required 0); derived entry 354.25 <= 1003. (c) DATA_UNHEALTHY:
`list_loaded_at` = max(last_seen_at) stamped by `clock_timestamp()` (0004:156-157) vs `req.now`'s date -> STALE; also
blocks EXIT (stale -> confirmation -> refused). Leg/underlying prices are healthy. Risk: the gate returns only its
first failure (execute.py:345); none further found by reading.

## Rules
Round 2's Rules apply (DB through the main checkout's db_run.py, one DB file, never copy .env, never atool.py, no PR).
