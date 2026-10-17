# Session handover 2026-10-17: goal contract GC-3 - PARTIAL (P0 done; L1-L4 parked to GC-3L)

Ran Sat 2026-10-17 21:52-~24:00 IST under `/goal`, unattended except two owner answers. Lock `lock/gc-3` taken 21:52,
deleted at close-out. Next: **GC-3L** (`goal-contract-GC-3L-2026-10-19.md`, NEXT; reviews in
`gc-3l-contract-review-2026-10-17.md`).

## DONE (merged on main)
- P0 1-3: W-101/W-104 on main; probe/readback script #379 (replay: gross -130.00 = Kite, holdings unchanged, contract
  depth/band/funds, audit chain verified; Tier B PASS); ofo_dev migrated 0013 -> 0017; rates in force; API healthy.
- Found + fixed: the owner was LIMITED on ofo_dev (a NEW_ENTRY needs Pro) -> DIRECT_ZERODHA_CUSTOMER grant.
- P0 6 triage (ADR-107): #338, #279, #352 = yes; every "no" Opus-checked. F-43: Monday is the nearest expiry.
- P0 7: fresh Opus verifiers on main: 5 pass, 13 FAIL on the Kite-basket path (F-42, #380); REQ-058/060 -> Approved;
  evidence pinned in every owning item (kit gap Startup-Factory#116). #382.
- W-107 (#383): Execute refuses while the strategy's own closed plan has drifted (the one reachable live harm: early
  Check -> nothing_placed -> fill -> a second ENTRY). Tier A: REVISE (MAJOR wrong EXIT reason) -> PASS.
- Owner answers (question tool, 23:10/23:15 IST) -> ADR-108 (#384): start under eight operating rules; trade the
  2026-10-27 expiry.

## PENDING / NEXT
- GC-3L step 0 (Monday by 09:00) then L1-L4 with the owner; then the next contract - recommended a FIX contract around
  #380 before GC-4.

## PARKED
- L1-L4: #385 (needs the owner on a trading day) -> GC-3L.

## BLOCKED
- None.

## Open issues from this run
- #380 live path re-implements reconciliation/partial (next contract's core); #381 orders read before trades;
  #386 review MINORs; kit #116 trace_check pass-hides-fail.

## Misses
- Three CI reds on #382 (coverage stage for new findings; stale build-order view and requirements index; two paths in
  the Spec-deviation block): CI's own checks were not all run locally first -> `lessons.md` line.
- First stop at the owner step without closing PARTIAL: the goal's PARTIAL exit applied; corrected at once.
