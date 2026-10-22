# Lane A and B brief index (drafted 2026-10-21; plan Step 4, ADR-165)

All briefs are in `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5d950a7e-a8d9-4cf2-838f-25c125932241\scratchpad\lane-briefs\`. Each ran `python scripts/orchestrator/check_brief.py <file>`; result column below. W-ids are placeholders (`W-1xx`); the orchestrator allocates them.

| File | Title | REQs / ACs briefed | Tier | Depends on | Size | check_brief |
|---|---|---|---|---|---|---|
| A1-leg-rows-prices-moves.md | Leg rows, entry prices, Shift / Width / Hedge | REQ-076 AC-1..10, REQ-077 AC-1..9, REQ-078 AC-1..10 | A | main only (#448 pool, Step 1 Execute off) | L (split point named: 076+077 then 078) | 32 quotes: 32 OK, 0 FAIL |
| A2-leg-picker-depth-futures.md | Leg picker, depth popup, futures and forward | REQ-080 AC-1..8 | A | none (uses chain code on main) | M | 9 quotes: 9 OK, 0 FAIL |
| A3-option-chain-remainder.md | Option Chain remainder, REQ-087 display options, live preview, per-user setting store | REQ-029 AC-3,5,9,10; REQ-030 AC-3,7,12,13,14,16; REQ-031 AC-1..3; REQ-087 AC-1..5 | A | #466 (W-120) and #457 merged; owns the generic `user_setting` migration | L | 18 quotes: 18 OK, 0 FAIL |
| A4-suggested-setups-preferences.md | Strategy modes, suggested setups, strategy preferences | REQ-024 AC-7; REQ-025 AC-2..4; REQ-026 AC-5; REQ-027 AC-1..5; REQ-068 AC-1,3..6; REQ-069 AC-1..9; REQ-028 AC-2 | A | #457; B4 (switch + placer); A3 (setting store) | L | 23 quotes: 23 OK, 0 FAIL |
| A5-saved-strategy-actions.md | Delete with undo, notes, share link, proposal Before/After | REQ-070 AC-6; REQ-037 AC-3 (+AC-1,2,5 API); REQ-086 AC-1..7; REQ-111 AC-1..6 | A | #393 (My Strategies); A3 migration number | L | 19 quotes: 19 OK, 0 FAIL |
| B1-summary-money-figures.md | Summary money figures and margin read | REQ-081 AC-1..11; REQ-055 AC-3, AC-4 (read part) | A | A3 only for the AC-5 setting; #448 | M | 14 quotes: 14 OK, 0 FAIL |
| B2-payoff-chart-whatif.md | Payoff chart both curves, what-if, SD bands, OI bars, Greeks panel | REQ-083 AC-1..7; REQ-084 AC-1..9; REQ-034 AC-6 (what-if half) | A | W-090 (read first, todo) | L (split point named) | 21 quotes: 21 OK, 0 FAIL |
| B3-warnings-and-market-context.md | Builder warnings, How this trade works, market context strip | REQ-085 AC-1..9; REQ-106 AC-1..8 | A | lane C REQ-050 (soft); PR #455 data file (soft) | M | 18 quotes: 18 OK, 0 FAIL |
| B4-held-switch-ready-made-pop.md | Held-feature switch module, ready-made shapes, quick picks, probability of profit (off in production) | REQ-079 AC-1..11; REQ-082 AC-1..7 | A | A1 (soft: edit/step legs) | M-L | 18 quotes: 18 OK, 0 FAIL |
| B5-history-charts-held.md | Strategy price history and market history charts (off in production) | REQ-091 AC-1..7; REQ-107 AC-1..8 | B | B4 (switch); lane C REQ-051 storage | M | 15 quotes: 15 OK, 0 FAIL |
| B6-delayed-prices-held.md | Delayed prices before a Zerodha connection (off in production) | REQ-105 AC-1..9 | A | B4 (switch) | M | 9 quotes: 9 OK, 0 FAIL |

Merge order suggested: A3 and B4 first (they own the shared setting store and the held-switch module), then A1, A2, B1, B2, B3 in parallel, then A4, A5, B5, B6.

Not briefed, with the reason:
- REQ-009 AC-1..8: verified (evidence/W-054).
- REQ-034 AC-1..5, AC-7, AC-8, REQ-028 AC-1, 3..5, REQ-070 AC-1..5, REQ-037 AC-1, 2, 4, 5 (domain), REQ-026 domain AC-3, 5..7, REQ-068 AC-2, REQ-029 AC-1, 2, 4, 6, 8: verified in evidence/; REQ-024, REQ-026 UI and REQ-030 selection ACs are in #457 / #466 (being merged).
- REQ-029 AC-7 (Pro-only): launch scope. REQ-037 AC-4, REQ-055 AC-1, AC-2: order path, out of scope (ADR-165).
- REQ-108 (events, FII / DII): blocked on a business input (no cleared data source); see below.

## Open: business (needs the owner; nothing decided)
1. A4: what Conservative / Balanced / Aggressive mean in numbers (REQ-027 AC-1 names them, no value in the spec). Recommendation: values in admin configuration, production values empty until Q211 clears.
2. B5 / REQ-108: which events source and which FII / DII source, with licence and cost (ADR-156 (3), ADR-012). Recommendation: leave REQ-108 unbuilt until a source is named.
3. B6 / REQ-105: which source supplies delayed prices and at what cost (ADR-155). Recommendation: build the hold-back rule and labels on recorded frames, no vendor client.

## Open: technical (proposals are in the briefs)
Hedge-leg rule for vertical spreads (A1); Start tracking with an unticked leg (A1); shared `user_setting` store owner (A3); strategy-alone margin mode (B1); signed-in meaning without login (A5, B6); charting library (B5); REQ-034 AC-6 built once in B2; REQ-037 Before/After component shared with lane D (A5).
