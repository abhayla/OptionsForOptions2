# Hard-coded business values: scan for ADR-222 (2026-10-31)

Read-only scan of `backend/ofo`, `backend/ofo_app` and `frontend/src` on `feature/adjustments` 6c75f344 (an
independent agent; key rows re-checked by grep: `live_market.py:50`, `detection.py:32`, `OptionChainPage.vue:34`,
ADR-007:63). Owner decision behind it: ADR-222 (every number a calculation uses is an admin setting with a default,
on one Settings page). Counts are hand tallies: about 95 business numbers in 24 groups (A), about 20 time-varying facts
typed in code (B), about 150 technical values that change no figure a user sees (C, not settings).

Only the charge rates are already a dated admin setting (table `charge_rates`, migration 0012, ADR-082).

## A. Business values that become settings

| # | Value | Where | Now | Group | Spec already says admin setting |
|---|---|---|---|---|---|
| 1 | Cost per leg | `ofo_app/adjustment_check.py:56` | Rs 40 | Charges | ADR-222 (retire, F-77) |
| 2 | Near-level alert distance | `ofo/adjustment/detection.py:32` | 0.5% | Detection | REQ-045 (Q253) |
| 3 | Risk-free rate | `ofo_app/live_market.py:50` | 6.5% | Pricing & Greeks | ADR-056, open-questions |
| 4 | Scenario columns (step, anchor, width, margins, count) | `ofo/scenario/config.py:121-123` | NIFTY 100/100/1000/2/200, SENSEX 300/300/3000/2/200 | Scenarios & payoff | ADR-042 (step) |
| 5 | Range pick-list cap and step | `ofo/range/pick_lists.py:43,46-48`; `frontend/src/lib/guided.js:32-33` | 3000/9000 pts, 100 | Limits | REQ-026 |
| 6 | Strangle quick-pick distances | `ofo/strategy/placement.py:27` | NIFTY 50-200, SENSEX 100-400 | Scenarios & payoff | REQ-079 AC-7 |
| 7 | Max delist percent | `ofo/instruments/catalogue.py:57`; env `ofo_app/config.py:32` | 10% | Data | ADR-058 |
| 8 | Trial and referral days | `ofo/entitlements/engine.py:40-41` | 7 / 30 | Billing | ADR-025, ADR-038 |
| 9 | Live push interval | `ofo_app/live_push.py:46` | 1.0 s | Speeds | REQ-166 AC-1, ADR-220 (3) |
| 10 | Undo window | `frontend/src/pages/OptionChainPage.vue:34`; `frontend/src/lib/legEdit.js:26` | 8 s; 10 s | Other | ADR-007 (about 5 s) - F-79 |
| 11 | Approach config | `ofo/adjustment/approach_config.json` | short delta 0.30 / 0.25, roll 200/500 pts, iron fly 3+ days, reduce /2 | Adjustments | file says "admin config" |
| 12 | System playbook guards | `ofo/adjustment/system_playbooks.json:115-122` | OI 10000, spread 5%, max 2, target 50%, stop 50%, cost warn 50% | Adjustments | no |
| 13 | System playbook day rules | `system_playbooks.json:80-95` | 15:00 pre-holiday, 13:00 / 20% expiry day | Adjustments | no |
| 14 | Gap-at-open window | `ofo/adjustment/playbook_eval.py:41` | until 09:30 | Detection | no |
| 15 | Compare curve range, steps, move columns | `ofo/adjustment/compare.py:87-89` | +/-6%, 48, +/-1% +/-2% | Adjustments | no |
| 16 | What-if target span | `ofo/engine/target.py:16` | +/-10% | Scenarios & payoff | REQ-084 states 10% |
| 17 | Payoff table steps and default | `ofo/outcome/service.py:96,99` | 10/25/50/100; NIFTY 50, SENSEX 100 | Scenarios & payoff | REQ-137 states values |
| 18 | SD band horizon | `ofo/outcome/service.py:102` | 7 days | Scenarios & payoff | no |
| 19 | Forward quality width, strikes near, min strikes | `ofo/marketdata/forward.py:46-48` | 5%, 21, 3 | Pricing & Greeks | no |
| 20 | Feed stale and reconnect windows | `ofo/marketdata/feed_health.py:39,41` | 3 s, 30 s | Detection | no |
| 21 | Freeze file stale after | `ofo/execution/freeze.py:24` | 8 days | Other | ADR-091 states 8 |
| 22 | Chain strikes each side | `ofo_app/chain_push.py:90`; `frontend/src/composables/useChainLive.js:13` | 15 | Limits | no |
| 23 | Leg-picker widths | `ofo_app/routes/leg_picker.py:75-76`; `frontend/src/lib/legPicker.js:79` | 10/20/30/40, default 10 | Limits | REQ-080 AC-1 states them |
| 24 | Lot and history caps | `frontend/src/lib/legEdit.js:12`, `legPicker.js:81`, `stores/chainSelection.js:14`; `ofo_app/strategy_price_history.py:39` | 50, 10, 10000; 15 days | Limits | no |

Test- and dev-only (stay in code): scenario stand-in margin rate 0.12 (`ofo/engine/adjust_money.py:71`, reached only
from scenario mode), replay rate (`ofo_app/replay_mode.py:28`).

## B. Time-varying facts typed in code (data, not admin choices)

Market hours and expiry close (`ofo/timeutil.py:27-32`), paper settlement window (`ofo_app/paper_settlement.py:59,62`),
Kite session expiry 06:00 (`ofo/broker/session.py:28`), freeze units / batch defaults labelled "UNVERIFIED
placeholders" (`ofo/execution/sequence.py:85-86`), Zerodha rate limits (`ofo/broker/rate_limit.py:64`), feed limits
(`ofo_app/kite_ws.py:72-73`), quote limit 500 (`ofo_app/kite_reads.py:46`), tick 0.05 (`ofo/engine/orderbook.py:51`),
stamp and SEBI caps (`ofo/charges/rates.py:33-34`, migration 0014), contract list publish time 08:30
(`ofo_app/catalogue_picker.py:35`). These move to settings in the "Exchange and broker facts" group, edited only by the
admin, with the source of the fact in the note.

## Not covered by the scan

Numbers written inline inside functions and inside Vue template markup were not checked one by one; error-message
templates were not checked for embedded numbers. Values the spec names as admin settings but that have no code yet:
REQ-045 conditions 2 and 3, REQ-085 AC-4 low-liquidity thresholds.
