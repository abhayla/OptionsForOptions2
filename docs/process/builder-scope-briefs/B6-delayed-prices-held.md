# W-1xx builder brief (lane B6): Delayed prices before a Zerodha connection (built OFF in production)

Common brief: docs/process/builder-brief.md
Core: the server releases a price to a user without a Zerodha session only when its exchange time is at least 60 seconds old, labels it delayed, and plan / paper-track numbers on it come from the same engine marked 'on delayed prices'.
Proof: step 1 is a test on RECORDED Kite frames (`tests/fixtures/kite_ws/`): a NIFTY tick stamped 10:41:05 is withheld at 10:41:50 and released at 10:42:05 (REQ-105 AC-2 example); the released value equals the recorded frame value; and a delayed-health quote offered to the basket builder or the trigger builder raises (AC-6). The choice of a real delayed data source is NOT part of this proof: see Open: business.
Tier: A (price release for users without a broker, feed health, a rule that keeps delayed values out of margin and any order path).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-105) and its coverage-stages row; commit them unchanged. Depends on lane B4 (held-switch module; register the name `delayed_prices`, do not add a second config reader). Login and per-user separation are launch scope (ADR-165 (8)): this PR keys the mode on 'this session has no Zerodha token' and takes the user from the session, so adding users later needs no rewrite.

## Spec basis (quoted)
REQ-105 AC-1: "One server setting enables the delayed mode; it defaults to off"
REQ-105 AC-2: "The server releases a price to a user without Zerodha only when its exchange time is at least 60 seconds old; a fresher price is held back, never sent early (fail closed)."
REQ-105 AC-3: "No delayed value is ever labelled live."
REQ-105 AC-4: "A delayed price older than 5 minutes during market hours is"
REQ-105 AC-5: "On delayed prices the user can build, save and paper-track (REQ-109) strategies"
REQ-105 AC-6: "Delayed prices never drive a monitoring rule's action or an alert on a real position, never feed a margin figure, and never reach the order path"
REQ-105 AC-7: "drafts are recalculated, never rewritten (REQ-016 AC-4)"
REQ-105 AC-8: "Public pages for signed-out visitors show no market data (ADR-027 Q58 unchanged)"
REQ-105 AC-9: "each planned entry is re-read from the live feed"
Scope change from ADR-165: AC-5's Execute / margin / broker-validation lock and AC-9's 'before Execute is offered' are met by Execute being off; keep the re-capture on connect and the test that no delayed quote reaches any basket or trigger builder.

## Copy from
Copy from: spec/technical-design/legacy-reuse.md ticker rows 1 and 8 (`ticker/models.py`, `ticker/health.py`, ADAPT: health states per ADR-015) and the in-repo `ofo/marketdata/feed_health.py`, `fanout.py`, `availability.py` (the adapted copy; extend, do not re-copy); frontend row `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` (ADAPT, P3b: data-health indicator). The delayed source adapter and hold-back rule: Copy from: none - new, behind the market-data adapter (ADR-012).

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 200-206 Google login pass (catalogue-raw.md, screens 168, 202, 206-208): a user with no broker uses the builder; Funds & Margins shows 'Standalone Funds / Standalone Margin' (no Margin Available); 'Trade All' disabled with 'To trade this, login with a supported broker.'; 'Add to Drafts' still enabled (paper).
- 180-181 login page: 'Login with Zerodha' beside 'Sign in with Google'.
- Differences kept on purpose: the 1-minute delay and the banner 'Connect Zerodha for real-time prices' are required by ADR-155; the hold-back is applied on the SERVER and fails closed; Sensibull's paid-plan tiers are not in scope (REQ-017-023).

## What to build
1. Adapter interface `ofo/marketdata/delayed.py` (new): `DelayedSource` protocol (behind the market-data adapter, ADR-012) and `release(quote, now)` returning the quote only when `now - exchange_time >= 60 s`, else nothing; an exchange time that is missing or in the future is withheld (fail closed); health set to `delayed` (REQ-049 AC-2) with the exchange time; older than 5 minutes in market hours becomes `stale`; outside market hours the last close labelled 'Market closed - last price <time>'. Server clock only, never the request-start clock (finding freshness-judged-on-request-start-clock).
2. Wiring: the outcome and chain reads pick the delayed path when the session has no Zerodha token and `delayed_prices` is on (`ofo_app/held_switches.py` from B4); when off, today's behaviour (REQ-016 'Draft - Live data not connected') stays exactly. A recorded-frames implementation of the source for development and test only; no vendor client is written (Open: business).
3. Labels and banner: catalogue texts 'Delayed 1 min - as of <time>' and 'Connect Zerodha for real-time prices'; the outcome says 'on delayed prices'; Frontend banner component shown on every screen that shows a delayed value.
4. Paper-track: tracking (REQ-109) records legs at the delayed price marked delayed (lane C/D own REQ-109; this PR only exposes the health to it and adds the test that a delayed quote never feeds a monitoring rule's action or an alert on a real position).
5. Connect: when Zerodha connects, re-read planned entries from the live feed and show per-leg change ('23,000 CE planned at 81.30 on delayed prices, now 84.10 live' as a catalogue text with values from the server); after the daily 06:00 token expiry fall back to delayed with the banner, never to the expired live feed.
6. Test (AC-6): a delayed-health quote offered to the basket builder, the trigger builder, the margin call or the monitoring input raises; the test enumerates those consumers from the code (fails closed on a consumer it cannot resolve).
7. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-105 AC-1 switch | missing (B4 module) |
| REQ-105 AC-2 hold-back | missing |
| REQ-105 AC-3, AC-4 labels, stale | partial (health states exist, `ofo/marketdata/health.py`; no `delayed` release path) |
| REQ-105 AC-5 | partial (builder works on live; paper-track REQ-109 is Step 2 / lane C) |
| REQ-105 AC-6 | missing |
| REQ-105 AC-7 | missing |
| REQ-105 AC-8 | partial (no public market data page exists; keep it so, add a test) |
| REQ-105 AC-9 | missing |

## Attack cases
Tick with no exchange time (withheld); exchange time 2 seconds in the future (withheld); clock skew of 3 seconds around the 60-second boundary (exactly 60 s released, 59.9 s not); market closed (last close labelled, no stale banner); feed drops while a delayed price is shown (stale rule applies); Zerodha connects mid-edit (drafts recalculated, entries re-read, nothing rewritten silently); token expires at 06:00 (falls back to delayed, not to the dead live feed); the switch off and a user without Zerodha (exactly today's message); a delayed quote reaching `kite_margin` (raises); a signed-out request for any price (none).

Threat model: in scope a request path where a delayed or fresher-than-60-second price reaches a user without Zerodha, and any delayed-health quote reaching margin, basket, trigger or monitoring consumers; out of scope the data licence itself (business, Open below) and a user holding a Zerodha session reading their own live prices (allowed).

## Findings checked
Findings checked: freshness-judged-on-request-start-clock, last-live-answer-kept-after-drop, liveness-from-shared-subscribers, fallback-time-claims-missing-data, setting-read-from-two-sources, guard-as-forbidden-list, guard-without-killing-test, verified-on-a-module-the-product-does-not-call, caller-supplied-verdict-trusted

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the AC-6 test lists the allowed consumers of delayed quotes and refuses everything else (allow-list), names the quote type by import source, and fails closed on a consumer it cannot resolve; (d) applied: answer states of the feed (tick fresh, tick old enough, no exchange time, future time, health stale, market closed) each have a defined release result and a test.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/marketdata/test_delayed.py (new), tests_app/test_delayed_mode.py (new), tests_app/test_held_switches.py (B4's file: add the name), tests_app/test_response_door.py; frontend: `npx vitest run tests/delayed-banner.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: which source supplies the delayed prices and at what cost. Business call: spend and a data licence. Spec basis: ADR-155 and REQ-105 AC-1 hold the mode off until Zerodha or a licensed vendor confirms in writing what may be shown to users without their own broker link and at what cost (ADR-014, ADR-034); no source is named (searched: REQ-105, ADR-155, ADR-034). Recommendation: build the hold-back rule, labels and the AC-6 test now against recorded frames; write no vendor client; ask for the source when the written answer exists. The core ('a real delayed price may be served') cannot be proven on real input before then, so nothing is built around a specific vendor.
Open: technical: with one fixed owner and no login, 'a user without Zerodha' means the session has no token. Proposal as above; tests use two session fixtures.
