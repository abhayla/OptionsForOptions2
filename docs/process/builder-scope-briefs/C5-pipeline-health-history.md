# W-1xx: Data pipeline, per-strategy monitoring availability, history tiers (REQ-048, REQ-049, REQ-050, REQ-051, REQ-052)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: a strategy whose quotes go stale shows 'Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused.' for that strategy only, while another strategy keeps its status.
Proof: feed the recorded frames (tests/fixtures/kite_ws/) for two strategies on different underlyings, silence only one underlying's contracts, and read per-strategy monitoring status from backend/ofo/marketdata/availability.py through the real route: one 'paused' with the exact text, one 'active'.

Tier: A (data health states decide whether any number or detection is shown; history feeds charts)

Spec basis:
REQ-048 AC-5: "Browsers never connect to a vendor, never hold vendor credentials"
REQ-049 AC-2: "Each quote has a health state: available, stale, delayed, unhealthy or unavailable"
REQ-049 AC-3: "Important rules are never triggered silently from stale data"
REQ-049 AC-6: "Monitoring availability is tracked per strategy"
REQ-050 AC-3: "No identical market metric is computed separately per user."
REQ-051 AC-2: "No complete tick-by-tick history is stored for every option"
REQ-051 AC-5: "Historical data and simulation never block live strategy creation"
REQ-052 AC-1: "The interim V1 source is Zerodha live market data through each user's own Zerodha API connection"
REQ-052 AC-7: "The platform never scrapes NSE, never exposes vendor credentials"

Copy from: legacy-reuse.md rows 1, 8 (ticker/health.py) and 75-79 already adapted in backend/ofo/marketdata/; no new copy. History store is already ours (backend/ofo/history/).

Sensibull screens: Option Chain 060-067 and OI/IV analyse pages 140-153 show data-age only as a refreshed number; no Sensibull equivalent in the study for per-strategy 'monitoring paused'. History charts (IV, OI, strategy price) are the held items REQ-091/REQ-107 built in lane B and shown only when ADR-158 clears.

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L5 (whose prices: platform-owned broker app, per-user session) and L6 (Greeks model, margin source); trap T9 (docs disagree with code): every health threshold stays configuration with a source and date.

## What to build
This is a gap-closing audit-and-fill PR: most of these ACs have code; first run the AC status table below against main and fix only what is red.
1. REQ-049 AC-6, AC-5: per-strategy availability: backend/ofo/marketdata/availability.py:27 strategy_monitoring_status and disconnect.py:61 disconnect_status_for_strategy exist; wire them to the live route (backend/ofo_app/routes/live.py, live_push.py StrategyPush) so each strategy's push carries its own status (NIFTY paused, SENSEX active), separate from the four health colours (ADR-010). Test with two strategies.
2. REQ-049 AC-3/AC-4: the trigger record shows the data health it was decided on; screens show stale or unavailable instead of old numbers. Check backend/ofo/marketdata/rule_adapter.py and frontend table cells; add the missing test only.
3. REQ-050 AC-1..AC-3: one shared computation per snapshot (greeks, chain metrics) not per user: add a test that two users' identical snapshot computes once (call counter); AC-4 load test is launch scope, mark deferred.
4. REQ-051: tiers exist (backend/ofo/history/recorder.py, store.py, bars.py, candles.py, 0009_minute_history.py, history_store.py). Verify AC-2 (no per-option tick table), AC-3 (tiers real-time, 1m/5m, daily, strategy snapshots) and AC-5 (history never blocks live paths: kill the history store, builder and chain still serve). Strategy snapshots of active strategies are the tracking store's job (C7); expose a writer function only if missing.
5. REQ-052: AC-1 and AC-7 are code (tests/test_history_not_shown.py exists; add a scan that no module scrapes NSE hosts and no browser bundle holds a vendor key). AC-2..AC-6 are owner/legal records (Zerodha written confirmation, vendor enquiries): not code, list them as owner inputs, build nothing.
6. REQ-048 AC-1..AC-5: provider interface exists (backend/ofo/marketdata/provider.py:69 MarketDataProvider, kite_provider.py:245 KiteProvider, fanout.py:35 FanOut). Add the missing test for AC-3 (a fake second provider swaps in without touching domain code) and AC-5 (frontend bundle test: no Kite host or key).

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 048 AC-1,2 | exists | provider.py:69, kite_provider.py:245, fanout.py:35 |
| 048 AC-3 | partial | no swap test |
| 048 AC-4 | exists | fanout.py:35 |
| 048 AC-5 | partial | no bundle scan |
| 049 AC-1,2 | exists | quote.py NormalizedQuote, health.py:52 evaluate_health |
| 049 AC-3 | partial | rule_adapter.py; trigger-record health field is built in lane D (D2) |
| 049 AC-4 | partial | table cells; confirm in frontend |
| 049 AC-5,6 | partial | disconnect.py:30,61 and availability.py:27 exist; not wired per strategy to the push |
| 050 AC-1..3 | missing (no REQ-050 reference anywhere in backend) | add counter test |
| 050 AC-4 | deferred | launch scope (5,000 users) |
| 051 AC-1..7 | partial | backend/ofo/history/*, history_store.py; AC-6/7 simulation is held (AC-1: disabled in V1) |
| 052 AC-1,7 | partial | tests/test_history_not_shown.py |
| 052 AC-2..6 | owner/legal | not code |

## Every answer state of each outside system
Kite quote (stated) = health from evaluate_health. Quote missing for a contract a strategy needs (absent) = that strategy 'unavailable'. Stale (failed or silent) = paused text with last-updated time. Empty feed outside market hours (empty) = 'market closed - last price' (C1). Two quotes disagree on timestamp (ambiguous) = the older one governs health (worst-of, rule_adapter.worst_health). Database history store down (failed) = live paths unaffected (REQ-051 AC-5).

## Attack cases (reviewer: hands-on first)
- Two strategies, one underlying stale: only that strategy shows paused.
- A strategy with one stale leg and three fresh legs: paused (worst-of), never 'available'.
- Strategy status colour Orange/Red never reused to mean 'paused' (ADR-010).
- Same metric computed twice for two users: counter test fails.
- History store raises on write: tick handling continues, error counted.

Threat model: in scope: staleness shown as live, cross-strategy bleed; out of scope: vendor licensing outcome (owner), load at scale.

Findings checked: last-live-answer-kept-after-drop, liveness-from-shared-subscribers, fallback-time-claims-missing-data, staleness-by-last-change-age, store-filled-only-by-tests, aggregate-across-mixed-instrument-kinds

Standing items: (a) n/a: no time-budgeted job added. (b) n/a: no CI step added. (c) applies to the new NSE-scrape and vendor-key scans: fail closed on shapes they cannot resolve, name the guard by import source. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/marketdata/, tests/history/, tests_app/test_live_push*.py, tests_app/test_history_*.py, tests/test_history_not_shown.py
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-050 AC-4 load test deferred to the launch scope (plan: out of scope list, many-user items). Proposal: record as 'deferred: launch scope' in the tracker row.
Open: business: REQ-052 AC-2 (Zerodha's written answer on showing Kite data in our SaaS), AC-4 (vendor enquiries), AC-5/AC-6 (long-term licensed source) are owner/legal inputs; list in the owner-inputs file, do not build. Ask the owner whether he wants a decision row on the long-term vendor shortlist now or at launch.
No live window needed (replay) except a final glance at AC-5 text with a real disconnect (C1's live window).
