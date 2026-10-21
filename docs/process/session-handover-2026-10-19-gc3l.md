# Session handover 2026-10-19 (GC-3L: 4b live gate, owner present) - DONE (core proven live)

Run: `lock/gc-3l` (6eb4e4c) 09:20 IST, cap 15:30; live steps 09:20 - ~11:30. Contract `goal-contract-GC-3L-2026-10-19.md`
+ delta `goal-contract-GC-3L-delta-2026-10-18.md`. One real 1-lot round trip placed by the owner on Kite's page; cost
about Rs 71 (22.75 price + ~48 charges). PRs: #427 (freshness clock) + this close-out PR. Nothing parked.

## DONE (evidence, measured 2026-10-19 IST)
- Step 0 (09:20-09:30): main 9f028b8 docs-only head, last code merge 414553c CI/App tests/coverage success incl.
  execute-screen-e2e; alembic head 0017 (no migration since Sunday); rates_in_force read_on 2026-10-15; owner
  AccessLevel.PRO. ADR-107 triage of 10 new deferred issues (#389, #390, #400-#403, #409, #411, #422, #423): none blocks,
  Opus check agreed 10/10, #401's reason corrected (it can only end the session; owner places by hand); #400 checked
  (ChargeOrder uses the sealed order quantity 65). NSE contract file 19102026 HTTP 404, 16102026 loaded: freeze
  inserted=4064 not_in_catalogue=46 disagreements=0. Catalogue reload REFUSED by ADR-058 (2179 of 4064, 53.6%), then
  ADR-059 (262 of 470 for 2026-10-19).
- L1 (09:3x): login /broker/zerodha/login -> /kite/callback 302; `holdings --save monday-before.json` exit 0 (6 holdings,
  same 26 raw keys as Sunday), `--compare` holdings_unchanged; funds 1000.00 (F-44 resolved); live 5-level depth on 13
  contracts (first live-depth proof); NIFTY ~23,130-23,160 (Kite 23162.70); pick NIFTY26OCT24000CE (bid 7.50 / ask 7.60
  at 09:42); Kite Positions and Orders empty (rule 5).
- Execute refused live; three defects handled: (1) MARKET_DATA_103 on every prepare (freshness clock) -> builder fix,
  fresh-Opus Tier A PASS (4 mutations caught), PR #427 merged a614b16 (e2e first 4/4 TooManyConnectionsError for
  ofo_app, re-run green); (2) stale instrument list after the refused reload -> technical call under the owner's data
  delegation: one forced `apply_update` (force=True, reason+actor, audit ADMIN_CHANGE_RECORDED): added=210 seen=4714
  newly_unlisted=2683 retired=396 delisted=2287; (3) tag > 8 chars: strategy 11 plan 1 BUY 65 LIMIT 7.10 tag OFS11V1L0,
  go 10:19:48, Kite `tag should be max 8 characters` (InputException), nothing placed; Check x2 (10:21:12, 10:21:25) ->
  nothing_placed, 0 mismatches. Workaround: same leg on strategy 9 (PUT /strategies/9, revision 2) -> tag OFS9V1L0.
- L2: strategy 9 plan 1 BUY 65 LIMIT 7.45, net premium -484.25, charges 23.82, funds 1000.00, margin 484.25 (10:24:54);
  go 10:33:53; basket DA1707 BUY 65 7.45 LIMIT NRML DAY; order 261019170382597 COMPLETE 65/65 avg 7.00 at 10:34:26;
  Check x2 10:35:05/10:35:18 -> filled, 0 mismatches, 65/65. F-41: no redirect after Place (tab stays on
  /connect/basket with "Refresh order status" / "Finish"; Finish not pressed); the Execute tab's Check closed the plan.
- L3: plan 2 SELL 65 LIMIT 6.65 tag OFS9V2L0, received 432.25, charges 24.43, funds 545.00, margin 0.00 (10:35:55); go
  10:38:15; placed 10:41:35 OPEN 0/65 (LTP 6.45), then COMPLETE 65 @ 6.65 (order 261019170402780); Check x2
  10:47:18/10:47:32 -> plan 1 filled, plan 2 exited, 0 mismatches, 0/0 units, Realised P&L -22.75.
- L4: `holdings --compare` holdings_unchanged exit 0; `pnl --tag-prefix OFS9V` (replies saved to
  ofo-kite-ticks/2026-10-19/replies-after-exit): fills 2, gross_pnl_from_fills -22.75, kite_position_pnl -22.75,
  kite_position_unrealised -22.75 (Kite reports a flat position's P&L in the unrealised field), pnl_equal exit 0;
  `audit --since 10:20`: hash chain verified rows=9 anchor_count=9 (order_prepared, broker_response_recorded,
  execution_recorded for plan:9:1 and plan:9:2).

## FINDINGS (registered in the GC-3L findings batch): basket-tag-exceeds-publisher-limit,
daily-list-trims-far-strikes-trips-truncation-guard, freshness-judged-on-request-start-clock (fixed #427),
db-role-connection-limit-below-pool-size, outcome-multi-expiry-unhandled-500. F-41 measured, F-44 resolved.
## OWNER RULES TODAY (memory + rule file): data issues are technical calls, decided as a market-data expert; content and
layout of ALL screens decided by a design role studying similar apps (look: GLOBAL.md section 3); conflicting business
requirements always go to the owner (`conflicting-business-requirements` project rule).
## AFTERNOON (owner "Today" ~11:40: tag fix + live proof same day)
- Tag fix PR #438 merged d859ccb (Tier A fresh-Opus PASS, 9 mutations, SQL CHECK emulation agrees on 50,000 rows; CI
  first red twice on my slips: spec digest not regenerated, then a docstring line > 120 chars). Owner approved the
  ADR-105 tag-form SPEC CHANGE (AskUserQuestion). New tag `Q` + strategy(4) + plan(2) + leg(1) base-36; legacy OFS
  tags keep their meaning. ofo_dev migrated to `0018_basket_tag_8` as owner (in-memory URL, scratch helper).
- Live proof NOT run: strategy 14 (24000 CE) and 15 (24100 CE) refused `RECONCILIATION_MISMATCH` "status unknown".
  Cause: the owner's own equity trades today (FRANKLININD CNC -201900, LIQUIDBEES CNC -2; the owner confirmed
  the sales were theirs) made `positions_from_reply` refuse the whole reply (`FRANKLININD (token 138288644) matches 0 instrument rows`)
  -> every Execute blocked. Fix PR #440 (allowlist `platform_may_own`, unknown exchange refuses, ignored rows logged):
  review round 1 FAIL (MAJOR: unknown exchange was ignored) -> fixed a8a29fb -> round 2 re-check. Nothing placed.
- Live proof moved to GC-3F (Wed 09:30-10:30): at 14:17 the timeline put the EXIT ~15:15, risking a carry-over over
  the Tuesday holiday; the stated 14:50 cutoff applied.
## PENDING: PR #440 round-2 verdict + merge; the live proof of #438 + #440 on a strategy id >= 10 (GC-3F item 1).
BLOCKED: none.
## PARALLEL: GC-5S (screens) RUNNING, owner-approved, own lock; its held PRs merge only after `lock/gc-3l` is gone.
## LESSONS (lessons.md): (a) push the branch BEFORE starting a reviewer - the verifier-in-flight hook blocks pushes
(~10 min lost); (b) a refused catalogue reload IS a stop for Execute, not "not a stop" as the delta said; (c) replay
tests pin the clock after the frame, so live-only clock bugs hide; (d) the Builder always saves a NEW draft (no update
path in the UI), hence the PUT workaround; (e) run CI's own checks (spec digest --check, ruff ratchet) before EVERY
push, even a one-line docs edit (~20 min lost on #438); (f) a contract traded today and the whole account's positions
feed reconciliation - read live positions before picking the proof strategy; (g) the verifier-in-flight snapshot is
shared by every session on the machine and records no owner, so a parallel session's verifier blocks this session's
git writes (finding to register; run-discipline E2).
## NEXT: GC-3F (`goal-contract-GC-3F-2026-10-21.md`, Wed 2026-10-21; Tue holiday): item 1 = the LIVE PROOF only (code
merged: #438 tags, #440 positions) on a strategy id >= 10 on a contract untraded that day, then the held-PR merges
(#419's migration renumbers to 0019) and #380.
