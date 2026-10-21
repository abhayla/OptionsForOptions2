# GC-3F delta (2026-10-19): what changes because GC-6 runs beside it

Wins over `goal-contract-GC-3F-2026-10-21.md` where they differ; that text (Opus-reviewed in GC-3L's close-out) is not
edited. Source: the owner-approved GC-6 plan of 2026-10-19 (`goal-contract-GC-6-2026-10-19.md`).

1. **Lock.** GC-3F checks main-line locks only (`lock/gc-3f` and any other `lock/gc-*` except `lock/gc-6`); `lock/gc-6`
   is the parallel-build lock (chain rule 1b) and never blocks GC-3F.
2. **Item 1 (live tag proof) unchanged,** run first. Its proof is pinned to the main sha it starts on (record it); GC-6's
   docs and frontend-only merges may land meanwhile and do not change what item 1 proves.
3. **Item 2 (held PRs) unchanged in order.** GC-6 runs the last review round of #421 and the fresh-Opus review of #424
   before Wednesday; GC-3F merges them. After item 2, GC-6 merges its held backend/Tier A PRs in dependency order.
4. **Item 3 (#380 steps 2.2/2.3) moves to GC-6** (rows #380-2, #380-3, #389, #390, #423). OQ-GC2h-2 is answered (owner,
   2026-10-19: "Kite flat -> one action", ADR-116), so step 2.2 no longer parks. #390 is built as two baskets (ADR-117).
   Their live proof is GC-6 row ORDER-LIVE-THU (Thu 2026-10-22), not Wednesday.
5. **Item 5 (DB connection limit) moves to GC-6** as row POOL-BUDGET (GC-6's core). #395 is already merged (2026-10-19).
6. **Item 6 (outcome multi-expiry 500) moves to GC-6** (row OUTCOME-500).
7. **Item 7 (W-111 part 2) moves to GC-6** (row POSITIONS, after #400).
8. **Items 4 (far-strike trim) and 8 (#444 brief items) stay in GC-3F,** as do Q272 and the ADR-058/059
   percentage-guard question to the owner.
9. **Execute outside market hours:** ADR-119 (owner D8) applies from the PR that builds MKT-HOURS; item 1 runs in market
   hours anyway.
10. **Next contract.** GC-3F's close-out no longer writes GC-3G (superseded by GC-6). It writes GC-5 (4c live gate) only
    when GC-6's 4c rows are closed; otherwise it marks GC-6 still RUNNING and names GC-5 as planned.
