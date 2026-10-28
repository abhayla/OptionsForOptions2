# Session handover: GC-BM (builder must-have set + user-style test), 2026-10-27 15:48 to 2026-10-28 ~09:45 IST

Contract: `docs/process/goal-contract-GC-BM-2026-10-27.md` (local branch `build/gcbm-must-have`, NOT pushed). Result: **PARTIAL, ON HOLD before the push**. Every item is built
and walked clean on the real app; one F-row remainder is PARKED (#596), and the contract counts a parked remainder as
not passed. **NEXT = GC-B2.**

## DONE
- The 5 must-have rows: G-065 (mixed-expiry legs answer, #586), G-070 (drawer opens on the nearest expiry with
  strikes), G-075 (one value per drawer column), G-024 (More actions: Save, Save As, Rename), G-051 (chart hover: price,
  % from spot, P&L). Gap-list re-verdicts in `docs/process/builder-gap-list-2026-10-27.md`.
- F-rows from the user walks, each with failing tests first: F-1, F-5, F-8, F-10..F-20 (F-2 / F-3 not reproduced or
  by design, see the contract table). Owner decisions ADR-199 (default expiry rolls after the close on an expiry day)
  and ADR-200 (prices from the last close outside market hours; "last close" = the session close; real-app
  closing-price walks prove this contract).
- Walks on the real app: walk 4 (after hours) clean U-1..U-32; 2026-10-28 09:09 pre-open walk of the label surfaces
  and the depth popup PASS ("Market closed. Prices are from 27 Oct 2026, 15:30:00 IST.", legs "Close, 27 Oct 2026,
  15:30:00 IST"); 09:16 in-hours check PASS (live prices, no banner, "captured 28 Oct 2026, 09:16:16 IST", depth 5
  levels).
- Reviews: Tier A (Opus) and Tier B (Sonnet) PASS in two rounds.
- Local checks: full vitest, ruff ratchet (no rule rose), coverage, openapi no drift, DB route tests on db_run_fresh,
  Playwright for the 12 builder specs 80 passed / 8 skipped / 0 failed. prepush.py run 1 (44e8410f): every step PASS
  except ci_checks (stale generated files); regenerated in 2dbd84f0; run 2 stopped at the owner's hold after ci_checks
  PASS (no marker written).

## PENDING
- Deferred issues: #597 (Option Chain default expiry after the close), #598 (ADR-008 scan MINORs), #599 (market
  calendar holds 2026 only: add 2027 before 2026-12-15), #600 (leg-edit echoes client close_at), #601 (drawer first
  open ~4 s late after hours), #602 (broker-status time has no date); #497 got the ofo_test measurement.
- Owner visual-differences list: the "Visual differences for the owner" table in the contract (not fixed here).

## PARKED
- #596: the close label on a saved strategy reopened later reads "captured <time>" (the numbers are right); needs a
  migration for `close_at`, which needs draft-PR CI (ADR-191 (2)).

## Process notes
- OWNER HOLD (2026-10-28 ~09:50 IST): "Don't create the PR ... I need to work more, test few more, implement few
  more features before we create a PR and push." Nothing pushed; no PR; worktrees kept.
- Local e2e: Git Bash `$!` is not the Windows PID, so the old script never stopped its servers; on 2026-10-28 servers
  from 06:42 answered the 09:22 run on a dropped database (8 false failures). The script now refuses busy ports and
  stops servers by the PID that owns each port. The 2026-10-28 ~07:00 whole-suite numbers in the contract are suspect
  for the same reason (strategy-table passed once the ports were clean).

## NEXT
- When the owner's extra work is in: merge main, `regen.py`, prepush.py with the servers stopped (needs a marker for the
  final head), ONE push, ONE PR (body draft: D:\Abhay\scratch\gcbm-briefs\pr-body.md, fill the prepush row), CI,
  merge.py, then wt-rm.ps1 for the gcbm-* worktrees.
- GC-B2 (`docs/process/goal-contracts-builder-phase-2026-10-27.md`): edit speed p95 <= 1,000 ms (G-019) and the Width /
  Hedge values (G-018). Market hours, the owner sets it as /goal in a fresh session.
