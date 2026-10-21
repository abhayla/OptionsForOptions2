# Goal contract GC-2g (Sun 2026-10-18 night): finish what GC-2f parked; nothing product merged

Chain: `goal-chain.md`. Written 2026-10-18 ~19:00 IST after the owner asked whether GC-2f stopped short (it did: it
closed at 18:41 with its cap at 23:13 and two items that still had an allowed next step). Owner, question tool:
"Yes, GC-2g via /goal (Recommended)". **Owner needed: NO.** Runs unattended.
**Cap: 6 h from the lock or 2026-10-19 07:30 IST, whichever is earlier** (in the lock commit). Close-out starts at
cap - 45 min and **not earlier while any item below still has an allowed next step** (chain rule 4b, added by this
contract). If `lock/gc-2g` still exists at 08:30, the GC-3L delta's fallback applies with `gc-2g` in place of `gc-2f`.

Core: an OPEN plan never makes the app's own lots read as outside and never clears a mismatch - W-108 independent
redesign of #405's MAJOR (`reconcile_attribution.py:157`: an open plan's orders count 0 held).
Proof: `tests_app/test_reconcile_attribution.py` new cases on the real 2026-10-16 replies: plan 1 OPEN with its BUY 65
already COMPLETE at Zerodha (orders/trades-122104) and Zerodha net 65 -> the contract is reported pending (not
outside, not agreeing, strategy not cleared); the same plan closed filled 65 -> agrees, nothing outside; the seven
ADR-109 cases and the 61 existing tests still pass.

## Main stays frozen for product code until GC-3L ends
Every code item ends as an open draft PR (HOLD), CI green, reviewed. Only the close-out docs PR merges.

## Items
0. Take `lock/gc-2g` (chain rule 2). `git pull` main.
1. **W-108 independent redesign** (Tier A; a FRESH Opus builder - not the one that built W-108; ADR-106 / CLAUDE.md
   fast delivery 5 "independent redesign"), on `build/W-108-attribution` (PR #398). Brief = #405's findings:
   - MAJOR, per ADR-110 (owner 2026-10-18): a contract with an OPEN plan of a strategy is reported `pending` for that
     strategy (a third state next to agree / mismatch): its lots are neither outside nor cleared, **the strategy is
     blocked**, and the result names the open plan. Bounded: read the open plan's own orders in Zerodha's order book
     by tag/order id; once every one is final (COMPLETE / CANCELLED / REJECTED), use their filled quantities and compare
     as normal (ADR-109 (2)) even if Check is never pressed. Say what other strategies and outside lots on the same
     contract get while one strategy is pending. Flip the test at `test_reconcile_attribution.py:259-266`. Tests: plan
     open + order COMPLETE at Zerodha + Zerodha short -> blocked (mismatch), not pending forever; plan open + order
     OPEN -> pending, blocked; plan open, user never returned, Zerodha 0 -> blocked.
   - MINOR: refuse a non-default `StoreReader` outside `APP_ENV=test` (or patch the module in tests).
   - MINOR: cap the outside count at Zerodha's holding (own +65, standalone -100, Zerodha +65 must not report 100
     outside); report a missing standalone instead.
   - Fresh Opus review; at most 2 rounds (a redesign starts its own count); after round 2 a CRITICAL/MAJOR -> park.
2. **W-111 Tier A review** after item 1 passes: rebase `build/W-111-positions` on the redesigned W-108; the page shows
   a pending contract exactly as ADR-110 says ("Order placed - waiting for Check with Zerodha", Zerodha's quantity
   marked "not yet confirmed", no own/outside split, a link to the strategy's Execute screen); open its draft PR (HOLD),
   fresh Opus review; one fix round allowed.
   Parked again only if item 1 parks.
3. **REQ-052 AC-1** (#404's smallest gap): a NEW work item carrying REQ-052 AC-1 (W-067 carries REQ-051 and is done),
   whose `tests_required` names `tests_app/test_kite_history.py` plus a new repo_scan test that no route or
   `frontend/src` page serves or shows historical market data (AC-1's "no history shown to users" is true today only
   by absence of a screen - audit line 166); a Sonnet builder writes the test; one verifier pass; evidence written by
   the orchestrator (`record_evidence.py`); all in one draft PR (HOLD). No `work/` edit in the main checkout while a
   verifier runs. #404 stays open for the other three.
4. **Chain rule 4b** (no early close) - already merged with this contract (goal-chain.md rule 4b, lessons.md); this
   run obeys it.
5. **Close-out** (cap - 45 min, or earlier only when items 1-3 are each PASSED-and-held or parked with no next step):
   main checkout on main, clean; ports 8765/4173 free; builder worktrees released; GC-3F draft updated (step 1 becomes
   "merge #398 then W-111" if they passed); handover `session-handover-2026-10-19-gc2g.md`; goal-chain: GC-2g
   DONE/PARTIAL, GC-3L NEXT; one docs PR via `land.py`; lock deleted; prompt, 5-line summary, scorecard, evidence
   table.

## Rules (checkable)
Every brief passes `check_brief.py` and carries Core/Proof, `Copy from:`, `Findings checked:`, `Threat model:` for a
guard, `Budget:` (at most 80 tool calls for a builder), `Report: evidence-table`, the B4 standing items, and the
lessons of 2026-10-18 (quote the AC text, not the work item's summary; list every stored-data state - plan open /
closed / exited, fills stored or not, other strategies, standalone - as B4 (d) answer states). Run
`check_pr_spec_block.py --body-file` before every `gh pr create`. Local pytest on Windows: `-p no:metadata` (#403).
No Kite call, no write to ofo_dev, DB tests targeted only.

## Stops
None needs the owner. A product merge before GC-3L ends, a Kite call, or an owner decision not in ADR-109 -> park.
