# GC-3F DRAFT (written by GC-2f, 2026-10-18; GC-3L's close-out finalises it per chain rules 3-4)

**DRAFT.** GC-3L runs first (Mon 2026-10-19, live gate). GC-3L's close-out rewrites this from its own results (a stop
or a finding on the live run changes the order below) and runs the full fresh Opus review (it adds order and
reconciliation behaviour).

Core: the reconciler, wired into both live routes, gives ADR-109's answers on the real 2026-10-16 replies and on
GC-3L's own replies - an outside same-direction surplus never blocks, a shortfall always blocks, an open plan never
hides the app's own lots.
Proof: the W-108 attribution tests plus a route test on GC-3L's recorded orders/trades/positions replies (saved by
GC-3L) - plan closed filled, 0 mismatches; derived 130 -> 65 outside, not blocked; derived 0 -> blocked.

## Step 0 - merge GC-2f's held PRs (after GC-3L L4, never before)
Order (each: `gh pr update-branch N`, `python tools/merge_when_green.py N` in the foreground, then
`python scripts/orchestrator/merge_audit.py`):
1. **#395** (#370 e2e pool budget) FIRST - it removes the `strategy-save-draft` flake that turned #396 and #399's
   frontend jobs red (2026-10-18 runs 39129072601 and the #396 run); its own app-tests run was fully green.
2. #394 (#381 return route; Tier A review PASS, covers the class; minors fixed at 8bb300a).
3. #393 (W-109 My Strategies; review PASS).
4. #396 (W-110 money guard; round 2 PASS) - must go green after #395 (its red was the flake).
5. #397 (W-089 Broker settings; Tier A round 2 PASS). Then the ofo_dev proof W-089 names: one run with the owner's
   session (Connected rows) and one after Disconnect (feed stopped), screenshots at 390 and 1280.
6. #399 (W-090 range; round 2 PASS) - must go green after #395 (its frontend red is the same flake; if it stays red
   on `strategy-save-draft`, W-090's new controls are the suspect: fix before merge).
Each PR's description says HOLD; remove the draft flag only at merge time.

## Step 0.5 - only if GC-3L ended with a carried-over position (ADR-111): fix #352 first
An execution plan left open at the end of a trading day is read back the next day, so the carried-over lot is exited
through the strategy's Execute screen (next session Wed 2026-10-21). Deadline: merged by Mon 2026-10-26 12:00 IST,
else the owner sells the lot on Kite that day and the app records the mismatch. Tier A (order state).

## Step 0.7 - GC-2h's held PRs (2026-10-19)
First the two PARTIAL steps: #421 (#352-1) last review round, then CI; #424 (#403) Tier A review. Then merge, after
#398 / #410: #419 (migration 0018, own PR), #418 (#338/#353 + ADR-113), #420 (never split), #421 (stacked on #419 +
#398), #417 (tracker_check), #424. Before #380 step 2.2: the owner's answer to OQ-GC2h-2 (shared-contract unblock) and
#423 (the route derives Zerodha's net and basket-reconciled from Kite). Tracker rows say the same.

## Step 1 - merge #398 (W-108) then W-111
GC-2g did the W-108 redesign (ADR-110 pending state, closed-plan drift; two fresh Opus rounds, round 2 PASS at
05ae2c5) and W-111's rebase + review (see `session-handover-2026-10-19-gc2g.md`). Merge #398 after #395 (its frontend
red was the #370 flake), then W-111's PR, each with `gh pr update-branch N` + `merge_when_green.py N` + `merge_audit.py`.
Step 2's wiring passes Zerodha's order book (`orders_from_reply`) beside the positions net and uses
`Attribution.blocked`; an unreadable orders reply refuses (never an empty book).

## Step 2 - #380 option C (ADR-109), 3 stacked Tier A PRs (~1,600-1,900 product lines, `fix-380-draft-2026-10-18.md`)
1. Migration (own PR): stored mismatch record, sticky block (Q222), standalone store (REQ-060 AC-7).
2. Reconciler in both routes through `reconcile_attribution.attribute_and_compare` (one reconciler, T3; bind
   `Account.user_ref` to the logged-in user; #405 note), triggers as reads only (T4), shorts-first exit baskets (T8,
   #389), expired legs via settlement (T6).
3. Partial actions per ADR-109 (3) (entry: the four REQ-058 AC-2 choices; exit: "Complete exit" and "Review
   manually"), the 3-action reconcile screen per ADR-109 (4), the rejection reason shown (T9), REQ-056 AC-4 entry
   baskets (#390) if it fits, else its own contract.
Detection: T10 (a repo_scan test that a Verified requirement's evidence module is reachable from `ofo_app.main`).

## Step 3 - W-111 part 2 (P&L/risk on the Positions screen) - only after the ADR-008 work in #400 decides where
those figures come from.

## Carried, not in GC-3F
#400 (ADR-008 violations on main - its own contract), #401 (Disconnect CSRF - with Stage 5 login, #129), #402
(wording), #403 (Windows pytest egress), #404 (evidence passes), Q272 (account-only control, asked after GC-3L).
