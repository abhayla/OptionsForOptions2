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

## Step 1 - W-108 redesign of the open-plan case (#405, parked by GC-2f)
Fresh builder (Opus), brief = #405's findings: an open plan's orders count 0 held, so the app's own lots read as
outside (MAJOR); refuse a non-default store reader outside tests; cap the outside count at Zerodha's holding. Then a
fresh Opus review (at most 2 rounds); then W-111 (`build/W-111-positions`, stacked, never reviewed) gets its Tier A
review. Merge W-108 then W-111.

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
