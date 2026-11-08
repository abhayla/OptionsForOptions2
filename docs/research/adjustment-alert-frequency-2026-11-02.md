# Adjustment-alert frequency study (2026-11-02)

Status: **study only, nothing approved or built.** Owner asked (2026-11-02 ~11:50 IST) for a study, as an experienced
options seller, of how often adjustment suggestions should fire, per trader type, with references from leading option
apps. Scope confirmed by question tool: three trader types separately (intraday, weekly, monthly); both knobs (how
often the app checks, and how often a suggestion is shown). Owner then (~12:05) agreed: the values belong in Settings /
Preferences "wherever applicable", and all of this is picked up AFTER market close, not during market hours.

## 1. Our own evidence (live, 2026-11-02, background role, no browser)

| Strategy / rule | Same suggestion raised | Window | Shortest gap |
|---|---|---|---|
| 66, T-07 profit target | 30 times | 10:38-11:09 | 16 s |
| 67, T-07 profit target | 23 times | 10:38-11:10 | 44 s |

75 of 103 records shown since 09:30 lapsed on their own (`GET /api/adjustment-opportunities`, 11:50). Strategy 78's
records are excluded (thresholds were moved by hand during the D3 test). Checks ran every 1-8 s then; a 30 s check does
not fix it, because the figure crosses, dips back and crosses again within minutes.

## 2. Two knobs

- Knob A, check: read prices and evaluate rules (cheap once the check path makes no database call, #636).
- Knob B, show: when a crossing becomes a suggestion, and when the same rule may speak again. This is what the trader
  feels, and it causes the noise.

## 3. What leading platforms do

| Platform | Behaviour | Evidence |
|---|---|---|
| Sensibull | Builder numbers refresh every 30 s, positions every 45 s; conditional exits handed to Zerodha alert triggers; P&L / price alerts on WhatsApp | own study `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\ARCHITECTURE.md` lines 97, 120, 123, 150 (strong); Sensibull blog (medium) |
| Zerodha GTT / ATO | fires on LTP, once; must be set again after firing | Zerodha support pages (strong) |
| thinkorswim | study alerts default "once"; "once per bar" or every tick optional | official thinkScript Alert reference (strong) |
| Streak / AlgoTest | alerts and many stop / target checks act at candle close (1 or 5 min; AlgoTest at second 59) | staff forum replies, AlgoTest blog (medium) |
| tastytrade / Option Alpha | manage at 50% of max profit (25% straddles), around 21 DTE; review positions about once a day | tastylive episode summaries, Option Alpha lesson (medium) |
| General alerting | hysteresis (reset level apart from trigger) + cool-down (common default 5 min) | engineering docs (strong as a pattern) |

Gap: no Indian app publishes how often it raises adjustment suggestions.

## 4. Recommendation by trader type

Rule for all: **edge, not level.** Raise a suggestion when a line is crossed; stay silent while it stays crossed;
re-arm only after it clears by a margin; speak again early only if it gets one stage worse (playbook stage values).
Hard stop-loss exits are never delayed by confirmation.

| | Intraday (0-1 day) | Weekly (2-7 days) | Monthly (8-30+ days) |
|---|---|---|---|
| Check speed | 5 s | 30 s | 60 s |
| Confirm before showing | 1-min candle close beyond the line | 5-min close | 15-min close |
| Same rule speaks again after | 5 min | 30 min | 2 h or next day |
| Re-arm after clearing by | 10% of the gap to the threshold | 20% | 25% |
| Max suggestions per strategy per day | about 6 | about 4 | about 2 |
| Quiet time | first 5 min | until 09:30 (S-01) | until 09:45 |
| Plus | stop-loss on LTP immediately | last day: intraday rules | 15:00 end-of-day summary; profit / time rules once a day |

Today's strategy 66 under the weekly row: 1 suggestion at 10:38 instead of 30.

## 5. Where each value lives (owner agreed in principle 2026-11-02 ~12:05; exact split still to approve)

| Value | Screen |
|---|---|
| Check speed | Admin Settings only (REQ-167) |
| Confirm on candle close | Admin default; user Preferences (REQ-168) may change |
| Same rule speaks again after | Admin default; user may change |
| Re-arm margin | Admin only |
| Max suggestions per day | Admin cap; user may lower, never raise |
| Quiet time | Admin default; user may change |
| Trading style Intraday / Weekly / Monthly | User Preferences, possibly per strategy; picks all defaults at once |

## 6. Proposed spec work (after market close, for owner approval)

1. New requirement "alert discipline": confirmation, cool-down, re-arm margin, daily cap, quiet time, with presets per
   trader type and the admin / user split above. Nothing in the spec covers it today (searched: cooldown, re-arm,
   candle close, hysteresis). Recommended first: it removes the noise whatever the check speed.
2. Check speed per trader type (5 / 30 / 60 s) instead of one value: SPEC CHANGE to ADR-233.
3. Stop-loss exits stay immediate, separate from adjustment suggestions.

## Sources
- tastylive: why manage at 50% for strangles https://tastylive.com/shows/options-jive/episodes/why-manage-at-50-not-25-for-short-strangles-09-13-2016
- tastylive: 21 DTE https://tastylive.com/shows/options-jive/episodes/mitigating-downside-risks-with-21-dte-04-24-2024
- Option Alpha: monitoring positions https://optionalpha.com/lessons/monitoring-positions
- Zerodha GTT https://support.zerodha.com/category/trading-and-markets/gtt/articles/what-is-the-good-till-triggered-gtt-feature
- Zerodha ATO https://support.zerodha.com/category/trading-and-markets/product-and-order-types/order/articles/what-is-alert-triggers-order-ato
- thinkorswim Alert https://toslc.thinkorswim.com/center/reference/thinkScript/Functions/Others/Alert
- AlgoTest candle close https://algotest.in/blog/candle-close-implementation-on-algotest.md
- Streak delay https://tradingqna.com/t/streak-live-scan-signals-alerts-are-delayed-by-36-seconds-or-so/181298
- Sensibull positions page https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/
- Nobl9 cool-down https://docs.nobl9.com/alerting/alerting-use-cases/alerting-use-case
- Digi hysteresis https://docs.digi.com/resources/documentation/digidocs/90001469/concept/c_ct-cs_manage_hysteresis.htm
