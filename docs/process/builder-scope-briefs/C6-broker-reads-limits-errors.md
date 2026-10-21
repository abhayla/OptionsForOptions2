# W-1xx: Zerodha read adapter with capability flags, rate limits and allow-list, plus error classes (REQ-054, REQ-117, REQ-118, REQ-053, REQ-065)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: every Kite read goes through one door with a bounded queue; a rate-limit answer is retried after Kite's stated wait at most twice, then fails closed with 'Zerodha is busy - try again in a moment'.
Proof: run the real KiteReads (backend/ofo_app/kite_reads.py) against a recorded Kite 429 reply and against a recorded positions reply through the egress door: the read retries once after the stated wait, a third answer fails; a recorded real positions JSON is parsed. Live window: one real positions + orders + margin read with the owner's Kite login.

Tier: A (every Kite call and secret path; rate limiter in the broker door)

Spec basis:
REQ-054 AC-1: "A broker interface offers: authenticate, fetch account, fetch margin, fetch positions, fetch orders"
REQ-117 AC-1: "The broker interface (REQ-054 AC-1) exposes a fixed set of named flags"
REQ-117 AC-4: "A flag that is missing, unknown or fails to load counts as off (fail closed)"
REQ-118 AC-2: "All Kite calls go through the one door (REQ-073 AC-4) and its limiter"
REQ-118 AC-3: "Each group has a bounded wait queue"
REQ-118 AC-4: "A rate-limit answer from Kite on a read (positions, orders, quotes, margin) is retried after the wait Kite indicates, at most twice"
REQ-118 AC-6: "three or more in one minute for the platform raise one alert to the platform owner through the Notifier"
REQ-065 AC-1: "Errors are classified at least as: user input, strategy validation, market data, broker authentication, broker eligibility, margin, order rejection"
REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
ADR-165 (1): "Placing orders at Zerodha or any other broker is out of this scope"

Copy from: (1) parked PR #418 (branch build/338-353-gate-fixes): the Kite allow-list change in backend/ofo/broker/kite_endpoints.py and kite_http.py (check_call) and tests/test_kite_http_guard.py; copy ONLY the read endpoints (instruments, quote, positions, orders, trades, margins calculate); do NOT copy the closing-basket or negative-balance order changes (#338). (2) legacy-reuse.md row 2 (brokers/base.py types, ADAPT, Zerodha only).

Sensibull screens: no Sensibull equivalent in the study for flags or limits; the visible read features are the Positions page funds drawer 050-053 and the Orders page in catalogue-raw.md ('Orders - /orders'): those screens are built in C8, not here.

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L2 (auth pattern A), L3 (adapter plug-in layer: keep one Zerodha implementation, no unused brokers, REQ-054 AC-2), L8; traps T6 (a gate that fails open: flags must fail closed), T9 (docs vs code: limits measured/quoted with source and date), T3 (lots vs units).

## What to build
1. Capability flags (REQ-117): a closed set in a new backend/ofo/broker/capabilities.py: basket page orders, broker-held triggers, intraday product, order-update stream, funds read, positions read, basket margin quote. Zerodha sets each with source and date; every flag unknown, missing or failing to load = off. The order-related flags stay off in this scope. A repo test fails if feature code compares a broker name or id (AC-3, by import source). Safety gates are never loosened by a flag (AC-5).
2. Read adapter surface (REQ-054 AC-1 read part): authenticate, fetch account, margin, positions, orders exist in KiteReads (backend/ofo_app/kite_reads.py:196-226 fetch_orders, fetch_trades, fetch_positions, fetch_holdings) and kite_margin.py; put them behind one interface in backend/ofo/broker/ without the basket builder. Per-broker contract mapping (AC-3) and per-broker lot/tick/freeze with date (AC-4) are already in 0004_broker_instruments.py: verify, add test only.
3. Limiter (REQ-118): limits per endpoint group (quotes, historical, margins, reads) as configuration read from Kite's docs at build with source and date (finding brief-rule-from-memory: do not type from memory); one limiter in the egress door (backend/ofo/broker/egress.py); bounded wait queue; user actions wait at most 5 s then 'Zerodha is busy - try again in a moment' (AC-3); read retries: wait Kite's stated time, at most twice, then failed and the caller's stale/fail-closed rule applies (AC-4); counts per group and user, logged; three or more in one minute raises ONE alert to the platform owner (AC-6) through the Notifier client built in D1 (until D1 merges, call an injected `alert` port with a fake).
4. REQ-118 AC-5 (never retry a create/delete) is out of scope: no create/delete call exists.
5. Allow-list: copy from #418 as above; the guard stays an allow-list of exact method+path templates, never a deny list.
6. Error classes (REQ-065): backend/ofo/errors/classes.py, templates.py, user_facing.py, explanations.py exist. Add the missing classes for the READ path (broker authentication, broker eligibility, margin read failure, market data, reconciliation mismatch, notification) and prove AC-2's four-part wording for each with the template pin test (tests/errors/test_template_pins.py). Status is [Testing]: first run it and list which classes lack a template.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 054 AC-1 | partial | kite_reads.py:196-226, kite_margin.py; no single interface |
| 054 AC-3,4 | exists | alembic 0004_broker_instruments.py |
| 117 AC-1..5 | missing | grep capabilit: no hits in backend |
| 118 AC-1 | missing | limits not held as configuration |
| 118 AC-2 | partial | egress.py door exists; no limiter |
| 118 AC-3,4,6 | missing | |
| 118 AC-5 | out of scope | no create/delete call |
| 053 AC-1,2 | exists | eligibility.py, catalogue_store |
| 053 AC-3 | in C4 | |
| 053 AC-4,5 | partial | check Zerodha rules in code cite a source and date |
| 065 AC-1,2 | partial | backend/ofo/errors/*; status Testing |
| #200 | parked | see Open |

## Every answer state of each outside system
Kite read: rows returned (stated) = parsed. Empty list (empty) = valid, 'No orders today' style message. HTTP 429 (failed, rate limit) = wait the stated Retry-After, at most 2 retries, then failed. 403/TokenException (failed, session gone) = session ended (C1), no retry. Timeout (failed) = one read-only retry is NOT allowed beyond the 2; caller shows last rows labelled with read time. Unknown field or new status word (ambiguous) = refuse the row, count, never guess (findings trust-broker-status-word, broker-reply-shape-unproven-at-domain-boundary). Missing row for a contract (not found) = contract unavailable at this broker. Notifier down (failed) = alert recorded in the database, the read path unaffected. Database: not on the read path.

## Attack cases (reviewer: hands-on first)
- Limit exhausted: 11th request in a second queues, 5 s later is refused with the exact message, never queued unbounded.
- Retry-After header missing or absurd (negative, 1e9): clamp to a configured range; test both.
- A Kite call that bypasses the door (new import of urllib in app code): repo scan red.
- Flag missing from the config: the feature is hidden, not shown; delete the flag test goes red.
- Error text contains the access token or api key: template pin test red.
- Positions reply with a row the platform did not create: parsed (finding positions-reply-refused-for-non-platform-rows).

Threat model: in scope: unbounded queues, retry storms, bypassing the door, flags failing open, secrets in messages; out of scope: forged code objects (ADR-098), Kite outage beyond the documented limits.

Findings checked: rate-gate-on-success-path-only, client-message-resets-rate-limit, trust-broker-status-word, broker-reply-shape-unproven-at-domain-boundary, positions-reply-refused-for-non-platform-rows, guard-as-forbidden-list, privilege-guard-as-denylist, secret-filter-by-key-name, margin-gate-blocks-closing-basket, money-parsed-through-float

Standing items: (a) applies: the limiter's alert pass uses a small reserved slot, never the whole window; a test shows reads still flow while an alert is pending. (b) n/a: no CI step added unless a scan imports a non-builtin: then after the install step. (c) applies: 'no feature compares a broker name' and 'no Kite call bypasses the door' scans name the door by import source and fail closed on re-exports, renames, same-named functions. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/test_egress_gate.py, tests_app/test_egress_gate_doors.py, tests/test_kite_http_guard.py, tests_app/test_kite_http_guard.py, tests_app/test_kite_margin_client.py, tests/errors/, tests_app/test_broker_*.py
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: issue #200 (PARKED, REQ-065 AC-2 remainder: response door module rebinding and seal reuse not flagged by CI) triage. Proposal: leave it parked. The issue itself quotes the owner's trust boundary (ADR-003 Q235): 'deliberate runtime replacement is out of scope, and the CI source scan flags it'. This brief builds AC-1 and the read-path templates of AC-2 only; #200's N1..N3 probes stay outside the threat model above. Re-open only if the owner widens the boundary.
Open: technical: limits are read from Kite's docs at build: the builder pastes the doc URL and date in the config; if the doc is unreachable, STOP and report (do not type from memory).
Open: business: none. Live window needed: one real read of positions, orders and margin (owner Kite login).
