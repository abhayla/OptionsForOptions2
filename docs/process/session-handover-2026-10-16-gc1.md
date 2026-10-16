# Session handover 2026-10-16 night: goal contract GC-1 (4a close-out + 4b core proof)

Ran 19:50 IST -> 21:00 IST under `/goal` (chain rule: one contract at a time). Contract:
`goal-contract-GC-1-2026-10-16.md`. Next: **GC-2a** (`goal-contract-GC-2a-2026-10-17.md`, marked NEXT in
`goal-chain.md`).

## DONE
- **Item 1, 4a audit:** `docs/process/4a-closeout-audit-2026-10-16.md` - every 4a AC, build-plan row, finding and
  issue with a verdict; the orchestrator re-checked 8 rows against source (one correction: 2 audit emitters, not 1).
- **Item 2, verified:** REQ-001 (W-087, fresh Sonnet verifier PASS AC-1..4, evidence recorded), REQ-035 and REQ-038
  moved to Verified (all ACs with passing verifier evidence). REQ-034 and REQ-064 deliberately NOT moved although the
  trace chain is complete: the audit found unbuilt behaviour (REQ-034 AC-4/AC-6 UI; REQ-064 emitters and timeline).
- **Item 3, gaps:** each gap placed (audit, "Disposition"): built tonight = W-088; new cards W-089..W-092 placed in
  GC-2b / GC-2d; the rest named with their contract.
- **Item 4, #159 (W-088):** merged as **PR #332** (W-088). The Tier A review of the existing pages found the real defect: Kite calls back on the API host (`:8765`), so the bare-path redirect landed on the API's 404 every time. The fix redirects to a start-up-validated `FRONTEND_ORIGIN`. Round 1 review REVISE: a public setter over a mutable list let any file widen the door to an open redirect, and CI could not see it. Round 2 (a second fresh Opus) PASS: the origin is write-once, a repo scan allows only `main.py` to set it, and 10 plants each fail CI alone. CI 5/5 green, including the DB-backed broker files. Pre-existing `_check_location` / `_PATH_LOCATION` rebinding added to #200. #159 stays open until GC-3's live login lands on `/broker/connected`.
- **Item 5, #126:** disposition comment on the issue - the setting is read; the alert + daily scheduler need the
  Notifier (GC-5); the audit record is NOT built because ADR-058 asks only for an alert and REQ-064 AC-1's closed event
  list has no such type; delisted-held -> reconciliation moves to GC-2b.
- **Item 6, #232:** closed with the gate re-run evidence; #297 stays open.
- **Item 7, bookkeeping:** coverage register regenerated (closed issues dropped, new cards staged); W-075 card to its
  real state (done; AC-7 NOT re-verified after its rounding change - GC-2a item 5); W-017 card's stale blocker removed
  (class 1 card defect); superseded worktree `agent-aaaebf66eb2e8d59e` released - main checkout 1513 tracked files, 201
  node packages, 261 pip packages before and after.
- **Item 8, 4b core proof:** `docs/research/core-proof-4b-2026-10-16/` - 4/4 checks PASS on the real order, but ONLY
  through four throwaway adapters: every real Kite row is refused at the domain boundary. Finding F-40 +
  `broker-reply-shape-unproven-at-domain-boundary`. Shapes GC-2b (W-091).
- **Item 9:** GC-2a written, independently reviewed (fresh Opus, READY WITH CHANGES, 8 findings, all ACCEPTED after
  re-checking the three load-bearing ones), marked NEXT:
  1. MAJOR: `wt-w080` holds `land/W-080`, so item 1 cannot re-create it. Accepted: remove it first.
  2. MAJOR: items 1 and 2 share `kite_margin.py` / `live_market.py`. Accepted: the order is now 1 -> 2 -> 3.
  3. MAJOR: half-up rounding reverses `margin_gate.py:141`'s "errs on the safe side". Accepted (re-read line 141):
     decision row + attack test (short by Rs 0.01 still blocks); real basket data is `rest/`, since `margins-*.json`
     hold only funds (re-checked: keys `equity`, `commodity`).
  4. MAJOR: no Kite login reply is recorded. Accepted (re-checked: zero hits): W-017 moves to GC-2b, the session type
     stays unproven until GC-3.
  5. MAJOR: about 16-19 h of work against a 6 h cap. Accepted: W-017 moved out; item 3 runs only if 2.5 h remain.
  6. MINOR: Linux may raise `OSError` before the gate. Accepted: assert that no packet leaves.
  7. MINOR: the integrate brief has no margin content. Accepted: item 3 writes its own brief.
  8. MINOR: missing checkable lines. Accepted: RUNNING first commit, `update-branch`, `merge_audit.py`.

## Decisions taken as architect tonight (information, not questions)
- **#159 fix shape:** the callback redirects to a start-up-validated absolute `FRONTEND_ORIGIN` instead of proxying
  `/kite/callback` through the frontend server - the proxy route also needed the owner to change the Kite developer
  console redirect URL; this one needs nothing from the owner.
- **Chain re-plan:** GC-2b split. GC-2b = the 4b boundary (W-091 adapter, W-092 eligibility - today the safety gate
  refuses every leg as unconfirmed, so GC-3 cannot pass without it); GC-2c = the Execute chain (the old GC-2b); GC-2d =
  4a screen gaps off the critical path. **Cost: GC-3 (Monday 09:15) runs only if GC-2c is DONE by then; if not, it
  moves to the next market day.**

## PARKED / BLOCKED
- None parked. Deferred by placement (each named in the audit's disposition table): W-089..W-092, W-017, #126's alert/scheduler (GC-5), REQ-064 emitters and timeline, REQ-063 AC-1/AC-3.

## Owner items (unchanged, named by the audit)
- `rotate-algochanakya-secrets` - still open, now overdue (a live Kite login has happened).
- REQ-052 AC-2 / AC-4 and F-23 - Zerodha's written confirmation, the vendor tracker.
- F-35 stamp check against the 2026-10-16 contract note.

## Per-PC setup not in git
- `.env` needs `FRONTEND_ORIGIN=http://127.0.0.1:4173` once W-088 is on main (added on this PC tonight; the API
  refuses to start with the broker routes configured and this key missing). The frontend must be served on that origin
  (`vite preview --port 4173`) for the post-login page to load.

## Misses tonight (recorded as findings, same turn)
- Wrote cards into a scratch worktree while a verifier ran; the write-guard moved two of them (restored by sha256).
  The morning's workaround was wrong: the guard watches every worktree. Finding `verifier-guard-watches-every-worktree`,
  kit issue Startup-Factory 110, memory corrected.
- All three audit agents overran their tool-call budget (104 / 66 / 57 of 40); finding `builder-budget-is-prose`
  bumped (8 occurrences); GC-2a now routes read-only work to capped agent types.

## Scorecard
| Item | Review rounds | CI runs | Local full-suite runs | check_brief before dispatch | Idle gaps > 10 min | Budget overruns (tool calls used / budget) |
|---|---|---|---|---|---|---|
| 1 4a audit (3 Sonnet agents) | 0 (orchestrator re-checked 8 rows) | 0 | 0 | y | 0 | **3**: 104/40, 66/40, 57/40 (time 4.5-6.4 of 20 min) |
| 2 W-087 verify (REQ-001) | verifier 1 | in #333 | 0 | n (verifier template brief, not run through check_brief) | 0 | **1**: 40/30 |
| 4 #159 / W-088 | Tier A 3 (1 on the existing pages, 2 on the fix) | #332: 2 (1st: coverage red - no stage line) | 0 | y (all 4 briefs) | 0 | **1**: builder round 1 91/75; round 2 56/60; reviews 19/60, 18/50, 12/30 |
| 5 #126 | 0 | 0 | 0 | - | 0 | 0 |
| 6 #232 | 0 | 0 | 0 | - | 0 | 0 |
| 7 bookkeeping | 0 | in #333 | 0 | - | 0 | 0 |
| 8 4b core proof (Opus) | 0 (orchestrator re-ran it) | 0 | 0 | y | 0 | 0: 23/80 |
| 9 GC-2a + handover | contract review 1 (8 findings accepted) | #331: 1, #333: 3 (1st red: build order, spec index, W-087 tests_required format) | 0 | y | 0 | 0: 30/40 |

Broken rules recorded the same turn: budget overruns (`builder-budget-is-prose`, now 8 occurrences); a push without the
CI mirror (`local-ci-mirror-runs-a-subset`, 2 occurrences; GC-2a carries the `atool.py` line); cards written while a
verifier ran (`verifier-guard-watches-every-worktree`, new, kit issue 110).
