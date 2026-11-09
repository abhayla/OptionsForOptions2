# Iron condor end to end on one code path: implementation plan (2026-11-08)

Status: DRAFT, being written with the owner one task at a time. Nothing here is approved or started.
Rule: ADR-275 (paper and live are two modes of one code path; only the place a fill comes from differs).
Gaps it closes: `docs/process/ic-e2e-code-audit-2026-11-07.md` C1 to C14, plus its architecture finding
"One position source per strategy: NO".

---

## Task 1: one code path for paper and live users (merge every duplicate)

**Core:** one reader returns a strategy's open legs from its fills, whether a paper or a live strategy made them.
**Proof:** read the open legs of the owner's live strategy 82 and of one paper strategy through that one reader,
then run the trigger checks on both. Read-only, no orders.

### What the task is

Wherever paper and live have their own code for the same job, the task merges them into one. After it, the only
mode-specific code is the fill adapter: Zerodha for a live strategy, the paper simulator for a paper strategy.
Prices stay a separate choice (the live feed or made-up scenario data), and either mode runs on either source.

### Known duplicates (measured on main da7b6b87, 2026-11-08)

| # | Job | Paper code | Live code | Gap it causes |
|---|---|---|---|---|
| D1 | Position: which legs are open | `paper_book.py` reads `public.paper_orders` (11 app modules) | `execute_plan.held_units` from order plans (7 app modules) | two answers to one question |
| D2 | Monitoring: triggers, stop lines, day rules, adjustment count | `background.py:1609` and `adjustment_readers.read_tracked` read the paper book only | none | C2 |
| D3 | Adjustment proposal (Compare) | `routes/adjustment.py` reads the paper book reader | refused ("not available") | C1 part 1 |
| D4 | Sending a basket | `paper_store.place`: a mixed close-and-open basket in one transaction | `routes/execute.py:108`: ENTRY or EXIT only | C1 |
| D5 | Order sequence | `paperDrafts.js:118` puts exits before adds | plan order or sorted by contract (`basket.py:278`, `execute_plan.py:223`); `sequence.py` not called | C3, C14 |
| D6 | Exit price | browser-sent price (`routes/paper.py:703-742`) | the server-priced `POST /strategies/{id}/tracking/exit` exists, but nothing on the screen calls it | C10 |
| D7 | Expiry settlement | `paper_settlement.py`, started at `main.py:96` | `ofo/reconciliation/settlement.py` `settle_legs`, never called | C6 |
| D8 | Reconciliation rules | n/a | the app's own `reconcile_attribution.py` alongside the domain `reconciliation/{blocking,grouping,resolution,triggers}.py` (0 app callers) | rules exist twice |
| D9 | Strategy status (open, exited) | "EXITED" worked out on the fly (`routes/paper.py:428`) | not stored | C13 |

### Steps

1. **Find every duplicate first.** The table above is what the audit found. Before anything is designed, sweep
   the app and the frontend for more paper/live pairs: grep `paper`, `is_paper`, `mode`, `held_units`, `paper_book`
   and `live` branches in `backend/ofo_app` and `frontend/src`. Add each new pair to the table with file:line.
2. **Prove the core** (above) on real strategy 82 and one paper strategy. If one reader cannot return both, stop
   and re-plan before any merge.
3. **Merge each duplicate into one path**, in dependency order: D1 position first, then D2 monitoring and D3
   proposal (they read D1), then D4 + D5 + D6 basket, sequence and price, then D7 settlement, D8 reconciliation
   and D9 status. The old paper-only and live-only code is deleted in the same change that replaces it.
4. **Fill adapter:** Zerodha and the paper simulator implement the same fill interface (ADR-029). The paper
   simulator can be set to fill, part-fill or reject a leg, so nights and weekends can test the cases the market
   will not produce on demand.

### Done when

- Every row in the duplicates table (including rows the step 1 sweep adds) has one code path, and the old code
  is deleted.
- A search for mode branches in the shared path returns only the fill-adapter choice. Any other hit is listed
  with its reason.
- The same tests pass for a paper strategy and a live strategy (parametrised by mode), on both price sources.
- Kept unchanged: a paper strategy never reaches the Zerodha order path (REQ-109), and the user presses to send
  every real order (ADR-003, ADR-016).

### Not in this task

- The gap fixes that build on the merged path (C1 adjustment action, C4 freeze split, C5 partial-fill route,
  C9, C11, C12, C7, C8). Those are later tasks.
- C8 / T-14 on live prices stays off until the owner decides (ADR-253).

### Open, measured later

- How much existing data (paper orders, order plans) must move into the merged position store. Unmeasured: it
  depends on the design step 1 leads to. A data move is a migration and gets a Tier A review.
