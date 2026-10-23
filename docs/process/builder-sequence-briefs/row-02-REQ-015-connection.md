# Row 2: REQ-015 Zerodha connection (W-130, builder sequence chunk 1, Tier A, size M)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: the status page's "live market data" row says Connected only while prices are actually arriving.
Proof: step 1 is a failing test on `build_status` (and the route) with a running socket whose provider has had no frame
yet / is in reconnect backoff, which answers `connected` today (verifier 2026-10-22 saw `live_market_data: connected`
while `/api/market/indices` answered NOT_CONNECTED); it then answers partial with a named fix. Then the orchestrator
re-reads the live status against the owner's session.

Spec basis: REQ-015 AC-2: "The contextual prompt reads: 'Connect your Zerodha account to continue. We'll use your
Zerodha account to verify availability, check margin and prepare/execute your strategy.'" REQ-015 AC-3 (ADR-169,
owner 2026-10-22): "A user connects only by logging in to Zerodha on Zerodha's own page through the platform's Kite
Connect app, as on Sensibull; no screen asks a user to create a developer app or to enter an API key or secret".
REQ-015 AC-4: "Settings → Broker & Market Data → Zerodha shows four separate statuses". REQ-015 AC-5: "When the
connection drops within a valid Zerodha session the platform reconnects automatically, validates and resynchronises,
then resumes monitoring; reconnecting never places or submits an order (Q183)." REQ-015 AC-9: "Broker tokens are stored
only through the official integration's secure token mechanism."
Copy from: legacy-reuse map rows for REQ-015, appended below by copy_from_check.py (act on each: COPY/ADAPT used or
the reason not; REFERENCE read first).
Sensibull: connection is a Zerodha login only (study screens 180-208, `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`;
never copy a screenshot into the repo).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (checked out). Commit on it
as you go; do NOT push; no PR. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row02`.

## Verifier findings to fix (2026-10-22)
1. AC-4: `broker_status.py:108-109` calls live data connected when `live_market.current_session() is not None`, i.e.
   the socket task is running (`live_market.py:165`); `KiteSocket.run` keeps that task alive through every drop and
   backoff (`kite_ws.py:92-114`) and `FeedHealth` (`feed_health.py:46-78`) is never read. Build the live row from the
   provider's feed health (connected + a fresh frame within the REQ-049 window) as well as the task: no frame yet ->
   partial with fix `live_feed_waiting`; in backoff / not connected -> partial `live_feed_reconnecting`; healthy ->
   connected. Add the fix codes to the catalogue with plain text; the Settings page shows them.
2. AC-2: the sentence is absent; `gate_broker_not_connected` (`templates.py:324`) says "Your Zerodha account is not
   connected. Connect it to continue." Make the contextual prompt the AC's exact sentence wherever a broker-dependent
   function asks for the connection (the pinned template changes its pin: update the pin test, grep every test tree
   for the old text).
3. AC-3 (new text): confirm no screen asks for an API key/secret or a developer app; remove the now-dead
   `SessionEndedCard.vue` only if nothing imports it (verifier: imported nowhere) - or leave it and say why. The
   history line "Historical market data: not currently available in this version." stays (AC-3's old wording is gone).
4. AC-5: reconnect works (backoff 1..30 s, re-subscribe, 403 ends the session, no retry) but nothing re-reads after a
   drop: on the reconnect after a drop (not the first connect) run ONE positions read through the existing reader
   (`kite_reads` positions, which also marks `broker_sync.note_read`), never an order call. The reconcile half of
   "validates and resynchronises" needs REQ-060 reconciliation, order-path scope (ADR-165): leave
   `Trigger.AFTER_RECONNECT` unwired and say so; the orchestrator records it as `AC-5 reconcile part deferred: order
   path`.
5. AC-9: `history_finalize.py:67` reads `KITE_ACCESS_TOKEN` from the environment; read the token through
   `broker_token_store.access_token_for` (the encrypted store) like `live_market._stored_token`, never from env;
   test that an env token is ignored.

Every answer state of the feed and the read (standing item d): first frame not yet arrived; frames flowing; frames
stopped beyond the health window; socket in backoff; socket ended by 403 (session ended); positions read on reconnect
answers OK / empty / Kite error / timeout / 429 - each gives a defined status row and never an exception to the route;
no retry of the positions read (one per reconnect).

Standing items: (a) the positions read on reconnect runs once per reconnect, off the socket's receive loop, and a test
shows ticks keep flowing while it runs; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) every answer
state above listed and tested.
Threat model: in scope - a status that claims live data while none arrives, an order call reachable from the reconnect
path, a token read from the environment or logged; out of scope - a forged provider object injected at runtime (ADR-098).
Findings checked: first-live-frame-before-first-price, guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: the live row's three states each have a test from a real provider state (not a hand-set flag);
the reconnect read is the only new Kite call and is on the allow-list; exact AC-2 sentence asserted; env token ignored;
every guard has a test that dies without it (mutation list in the report); no new duplicated literal; reuse the existing
helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (except openapi.json if
a model changes).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the changed files' tests (`select_app_tests.py <worktree>` for tests_app, through `db_run.py`), vitest for changed
frontend files, `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `app/utils/market_hours.py` (138) | ADAPT | add holiday calendar and BSE hours; its hard-coded 2026 holiday list is wrong (F-54): never copy it, use the dated NSE data file (ADR-119) | REQ-049 |
| `services/brokers/market_data/ticker/models.py` (84) | ADAPT | row 1; fix float serialization `:61-69` | REQ-049 |
| `market_data/auth_tracking.py` (102) | REFERENCE | token-expiry detection idea | REQ-015 |
| `app/api/routes/auth.py:60-175` | REFERENCE | row 9; token stored only via the secure mechanism | REQ-015 |
| `src/services/priceService.js` (251) | ADAPT (P3b) | polling fallback only; change math from the backend | REQ-049 |
| `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` | ADAPT (P3b) | data-health indicator | REQ-049 |
| `src/components/settings/KiteSettings.vue` (388), `views/AuthCallbackView.vue` (81) | ADAPT (P4) | no token in URL | REQ-015 |
