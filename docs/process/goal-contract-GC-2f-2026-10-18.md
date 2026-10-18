# Goal contract GC-2f (Sun 2026-10-18 night -> Mon 07:30): build ahead without live data; nothing product merged

Chain: `goal-chain.md` (rules, process rules 1-9, scorecard). Written 2026-10-18 from the owner-approved plan (plan
mode, after a fresh Opus plan review: CHANGES NEEDED, all 12 findings applied) and ADR-109 (the owner's answers).
**Owner needed: NO.** Runs unattended.
**Cap: 6 h from the lock or 2026-10-19 07:30 IST, whichever is earlier** (the lock commit says so). Close-out starts at
cap - 45 min. If `lock/gc-2f` still exists at 08:30, the owner may delete it and start GC-3L with the fallback prompt
in the GC-3L delta.

Core: the reconciler answers correctly from the app's own tagged fills under ADR-109 (2) - W-108, "attribute before
compare": per contract the expected quantity is every strategy's held units (`execute_plan.held_units`,
`backend/ofo_app/execute_plan.py:188`) plus the recorded standalone quantity; a same-direction surplus of Zerodha's net
beyond that is reported as outside lots and removed before `ofo.reconciliation.compare`
(`backend/ofo/reconciliation/compare.py:399`) runs; `compare` is unchanged; the result keeps Zerodha's raw net. The
StrategyRecord's `active_version.intended_position` (`versions.py:156-157`) is built from the held units.
Proof: `tests_app/test_reconcile_attribution.py` on `tests/fixtures/kite_replies/` (`orders/positions/trades-122104`,
`-151006`; tags OFS1V1L0 BUY 65, OFS1V2L0 SELL 65; lot 65): (a) the real replies -> 0 mismatches; (b) strategy 65,
Zerodha 130 -> not blocked, 65 outside; (c) strategy 65, Zerodha 0 -> blocked; (d) strategy short 65 + outside long
65, Zerodha 0 -> blocked (an opposite-direction difference: asserted explicitly, it must reach `compare`); (e)
strategy 65 + standalone 25, Zerodha 90 -> no mismatch (the lot-65 analogue of REQ-060 AC-7's example); (f) two
strategies 65 each on one contract, Zerodha 65 -> both blocked (Q224); (g) a contract no strategy holds, Zerodha 65 ->
65 outside, no mismatch. A failing core stops items 1 and 7 only and re-plans GC-3F.

## Main stays frozen for product code until GC-3L ends
Every code item ends as an OPEN pull request: CI green, reviewed, NOT merged. Only docs merge tonight (the close-out),
and only paths under `docs/`, `spec/`, `knowledge/`, `views/`, `work/` (GC-3L delta section 2). `evidence/` files ride in
their item's open PR. GC-3F step 0 merges the held PRs after GC-3L L4.

## Items (in order; item 1 is the core; items 2-6 run in parallel from the start)
0. Take `lock/gc-2f` (chain rule 2) with `cap <min(lock+6 h, 2026-10-19 07:30)> IST` in the commit. `git pull` main.
1. **W-108 core** (Tier A; Opus builder, fresh Opus review): the adapter + the proof test above. Reuse `compare`,
   `held_units`, `strategy_blocked` (`execute_plan.py:233`). No route wiring.
2. **W-090** range/step + At Expiry / Estimated Now (Tier B; REQ-034 AC-4, AC-6): the request already takes `view`
   (`routes/outcome.py:146`), but `step` at `:231` is response-only, so a backend request change for range/step is
   part of the item.
3. **W-089** Settings -> Broker & Market Data (Tier B; REQ-015 AC-4, AC-8; REQ-051 AC-1): status route + page,
   Reconnect / Disconnect (`broker_token_store.py`). Its ofo_dev proof runs at GC-3F (no live run tonight); tonight's
   proof is the route + page tests on the test database in CI.
4. **W-109** My Strategies list + Completed filter (Tier B; REQ-009 AC-2; `GET /strategies`, `routes/strategies.py:329`).
5. **W-110** repo-wide money guard (REQ-063 AC-3; finding `money-value-computed-outside-engine`) + evidence-only verifier
   passes for REQ-048 AC-1/AC-5, REQ-049 AC-4, REQ-052 AC-1 (evidence in this item's open PR).
6. **Small fixes** (one PR each or batched by area): #381 (return route: trades and orders read consistently; real
   fixtures `orders/trades-122104`; Tier A), #257 (freeze limit older than 8 days -> the ADR-091 warning; Tier A),
   #370 (flaky e2e: root cause first; parked after 1 h without one), #159 (closed after confirming `/broker/connected`
   is served on main; a close needs no PR).
7. **W-111** Positions part 1 (Tier A; REQ-044 AC-3): stacked on W-108's branch after its proof passes; strategy-linked
   lots and outside lots apart; no P&L figure; parked if item 1 fails.
8. **Close-out (cap - 45 min -> cap):** main checkout on `main`, clean, at `origin/main`; ports 8765 and 4173 free
   (stop any server by PID); builder worktrees released or listed; a scoped fresh Opus re-check of GC-3L (contract,
   delta, runbook) against ADR-109 and ADR-108 (chain rule 3: it precedes a real-money run); handover `session-handover-2026-10-19-gc2f.md`; goal-chain: GC-2f DONE/PARTIAL with
   the open PR list, GC-3L NEXT; **GC-3F draft** `goal-contract-GC-3F-draft.md` written from items 1 and 7: step 0
   merge the held PRs (`gh pr update-branch N`, `merge_when_green.py N`, `merge_audit.py`), then #380 option C as 3
   stacked Tier A PRs (migration; reconciler in both routes + T8 shorts-first exits; partial actions per ADR-109 (3) +
   3-action reconcile screen per ADR-109 (4) + rejection reason T9), then W-111 part 2 (P&L/risk); GC-3L's close-out
   finalises it (chain rules 3-4). One docs PR via `land.py`; lock deleted; prompt, 5-line summary, scorecard,
   evidence table.

**Cut order when time runs short** (review 2026-10-18): W-111 first, then #370, then W-110's evidence passes. The GC-3F
draft is written as soon as items 1 and 7 settle, not left to the last minutes.

## Rules (checkable)
- Every brief passes `check_brief.py`, says `Common brief: docs/process/builder-brief.md`, carries `Core:` / `Proof:`,
  `Copy from:` (the legacy-reuse map), `Findings checked:`, `Threat model:` for a guard, `Budget:`, `Report:
  evidence-table`, and the B4 standing items. Builders run targeted tests only; CI runs the full suites.
- Tier by data flow; at most 2 review rounds per item, then park (`parked` issue). Red CI: read the failed log, fix,
  push.
- No live run: no Kite call, no write to ofo_dev, no `db_run.py` full suite (the VPS PostgreSQL also serves IPODhan
  production); DB tests run in CI.
- No file under `work/` while a verifier runs; generated files only in the close-out docs PR.

## Stops
- None needs the owner. A Kite call, an owner decision not in ADR-109, or a product merge before GC-3L ends -> park.
- The 07:30 cap is hard: unfinished items are parked with their open branch named, and the close-out still runs.
