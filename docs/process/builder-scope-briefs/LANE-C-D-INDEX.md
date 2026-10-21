# Lane C and D brief index (2026-10-21)

All 13 briefs: `check_brief.py` exit 0, 0 FAIL, 0 UNCITED. Every brief is Budget 60 min / 80 tool calls, Report evidence-table. Where a cluster needs a migration, the migration is its own small PR first (stated in the brief).

| File | Title | REQs / ACs | Tier | Depends on | Size | check_brief | Needs live window |
|---|---|---|---|---|---|---|---|
| C1-feed-health-reconnect.md | Feed health check, 60 s silence reconnect, jittered backoff | REQ-114 AC-1..8, REQ-133 AC-3 | A | #448 (pool) | M | 8 OK, 0 FAIL | 114 AC-5, AC-6 (real token expiry) |
| C2-feed-own-process.md | Market-data process separate from API, internal bus | REQ-113 AC-1..9, REQ-048 AC-4/5 | A | C1; Redis decision | L | 9 OK, 0 FAIL | 113 AC-2, AC-8 |
| C3-late-replies-and-frame-version.md | Late replies and old-version frames dropped | REQ-119 AC-1..4 (AC-5 out: Execute off), REQ-133 AC-1,2,4 | A | none | M | 6 OK, 0 FAIL | none (replay) |
| C4-four-indices-and-instruments.md | Four indices, daily fresh list, eligibility read | REQ-090 AC-1..5,7 (AC-6 out), REQ-053 AC-2,3 | A | #466 (selection); copy from parked #459 | M | 8 OK, 0 FAIL | 090 AC-5 (BANKNIFTY/FINNIFTY spot) |
| C5-pipeline-health-history.md | Per-strategy monitoring availability, history tiers, pipeline audit | REQ-048, 049, 050 (AC-4 deferred), 051, 052 (AC-2..6 owner) | A | C1 | S-M | 9 OK, 0 FAIL | glance at 049 AC-5 with a real disconnect |
| C6-broker-reads-limits-errors.md | Read adapter flags, rate limits, allow-list, error classes | REQ-054 AC-1,3,4, REQ-117, REQ-118 (AC-5 out), REQ-053 AC-4,5, REQ-065 | A | none; copy from parked #418 | M | 10 OK, 0 FAIL | one real positions + orders + margin read |
| C7-tracking-complete.md | State machine, tracked P&L rest, typed fills, manual P&L | REQ-039, REQ-109 AC-3..8, REQ-077 typed fill, REQ-089 | A (own migration PR first) | W-122; lane A price validator | L | 14 OK, 0 FAIL | tracked P&L on live prices |
| C8-zerodha-import-and-positions.md | Import real positions, compare-and-block, Orders/funds, Positions | REQ-104, REQ-061, REQ-060, REQ-103 read, REQ-044 AC-3,4 | A | #419, #451, #452, C7, C2 (event) | L | 16 OK, 0 FAIL | every AC (real positions, orders, funds) |
| D1-workers-and-notifier-path.md | Workers (never order), Notifier client, dispatcher | REQ-115 AC-1..9 (AC-2 trigger-door sentence out), REQ-116 AC-1..6 | A (own migration PR first) | C1 (stale signal), C4 (refresh callable) | L | 14 OK, 0 FAIL | 115 AC-7 reminder, one real Notifier event |
| D2-rule-engine-editor-status-colours.md | Rule storage, editor, defaults and overrides, status colours | REQ-041 (AC-3 order half out), REQ-043, REQ-045 AC-7 (machinery only) | A (own migration PR first) | W-122; D1 for evaluation | L | 12 OK, 0 FAIL | none (replay) |
| D3-detections-triggers-actions-data.md | Q253 detections 2 and 3, all triggers, action kinds, adjustment data | REQ-045 AC-1..6,8, REQ-047, REQ-071 | A | W-122, D2 | M | 11 OK, 0 FAIL | conditions 1-3 on live prices |
| D4-opportunity-panel-before-after-outcomes.md | Opportunity panel, Before/After, what the user did | REQ-046, REQ-112 (Acted on = open), REQ-045 AC-9 | A (own migration PR first) | D3, lanes A/B summary components | L | 9 OK, 0 FAIL | Before/After margin on a real strategy |
| D5-alerts-and-daily-zerodha-check.md | Alerts page, channels, alert-only rules, daily Zerodha check | REQ-062, REQ-042 AC-1 alert part, REQ-110 | A (Alerts page part B) | D1, C8 | M | 11 OK, 0 FAIL | daily check after a real close; one real alert |

## Owner inputs gathered from the briefs
1. Notifier project block + key for OFO2 in the shared gateway (D1): credentials only the owner holds.
2. The 7 unclear video values, registry rows 12, 13, 19, 20, 21, 22, 30 in backend/ofo/adjustment/metric_registry.json (D3).
3. REQ-112 "Acted on" with no basket: recommended button "I will place this on Kite myself" (D4, business).
4. WhatsApp alert template wording for Meta approval (D5, business); push notifications later (D5, business).
5. REQ-052 AC-2..6 vendor/licence records (C5, owner/legal, not code).
6. Two live market-day windows: all "Needs live window" cells above.

## Technical decisions proposed in the briefs (no owner question)
Redis pub/sub bus plus requirements-app.txt entry (C2); #200 stays parked, REQ-065 builds AC-1 and read-path templates (C6); BANKNIFTY/FINNIFTY scenario step = 2x strike gap, decision row before build (C4); condition 2 not applicable when max loss is unlimited (D3); REQ-103 AC-8 vs order-book store of #451/#452 conflict check (C8); REQ-077 tick validator single home shared with lane A (C7).
