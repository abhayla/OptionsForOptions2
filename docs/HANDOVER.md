# Handover

Updated 2026-09-29 16:40 IST (end of the owner-present day session; the overnight session before it ran
2026-09-28 20:42 → 2026-09-29 09:16 — its "2026-09-30" stamps were wrong and are corrected, finding
`date-stamp-typed-from-memory`). Main at the merge of this file's PR.
Read this first, then `spec/open-questions.md`. The overnight owner list is `docs/owner-review-2026-09-29.md`; most of
it is answered (see "Answered today").

## Rule for the next session: nothing pending is closed until it is implemented and verified
Every item under PENDING, PARKED, BLOCKED and DEFERRED below stays open (issue open, work item not `done`) until
its code is merged **and** an independent verifier passed it with evidence (`evidence/<W-id>/`). Do not close an issue
because it "looks done", because a builder said so, or with a partial-fix PR: GitHub closes an issue on any
"closes/fixes #N" in a PR body — for partial fixes write "addresses items of #N" (this closed #43 by mistake once).

## DONE (merged, independently verified, evidence recorded)
Product code is standard-library Python under `backend/ofo/` (domain layer only: no API, DB, UI or real Zerodha yet),
tests under `tests/` — **1295 tests** collected on main.

| Work item | Requirement | What it is | PR |
|---|---|---|---|
| W-001 | REQ-033 | Calculation engine core (P&L, breakevens, max profit/loss) | #5 |
| W-002 | REQ-032 | Engine inputs, Black-Scholes, Greeks, money precision | #8 |
| W-003 | REQ-034 | Scenario level set, two views | #16 |
| W-004 | REQ-035 | Strategy table model; Guided headings per Q227 (2026-09-29) | #58 |
| W-005 | REQ-028 | Parametric strategy templates + matcher | #15 |
| W-006 | REQ-053 | Instrument catalogue from Zerodha's public list | #7 |
| W-010 | REQ-020 | Admin qualifying Client ID list | #13 |
| W-012 | REQ-038 | Strategy definition vs live state, versions | #20 |
| W-013 | REQ-041 | Rule engine (three-valued logic) | #9 |
| W-014 | REQ-059 | Pre-execution safety gate | #24 |
| W-015 | REQ-064 | Append-only audit log | #14 |
| W-016 | REQ-070 | Builder history, undo, restore | #18 |
| W-018 | REQ-049 | Market data model + health | #25 |
| W-019 | REQ-057 | Order lifecycle, single fill ledger | #28 |
| W-020 | REQ-040 | Strategy timeline + rule-trigger records | #27 |
| W-021 | REQ-060 | Reconciliation with Zerodha positions | #40 |
| W-022 | REQ-056 | Multi-leg execution plan | #42 |
| W-023 | REQ-058 | Partial execution, no automatic retry | #39 |
| W-025 | REQ-026 | Range input pick lists | #36 |
| W-026 | REQ-036 | Strategy-only execution + Strategy Guard | #44 |
| W-027 | REQ-037 | Strategy modification proposals | #35 |
| W-028 | REQ-058 | Complete/Retry split into lot-aligned freeze slices | #49 |
| W-029 | REQ-036 | Tests pinning W-026 backup checks | #48 |
| W-030 | REQ-053 | Guard: test fixtures use real catalogue symbols | #52 |
| W-031 | REQ-053 | Last three fixture symbols on the real catalogue (closed #51) | #56 |
| W-032 | REQ-056 | Close Partial slices exits at the freeze limit (closed #50) | #57 |
| W-033 | REQ-038 | Performance tests count work, not wall-clock time (+ guard) | #60 |
| W-034 | REQ-035 | TOTAL row: P&L % = unrealized ÷ max loss; net Entry Value Cr/Dr (Q233, Q236) | #67 |
| W-035 | REQ-020 | Client ID format per owner Q234 (AB1234 / ABC123) | #66 |

Requirements VERIFIED end to end (`python tools/trace_check.py .`, run 2026-09-29 ~16:35 IST): REQ-020, 032, 033, 038,
040, 057, 058, 059, 060, 064, 070 (11). Others are partly built (UI or later-stage ACs not in any work item yet).

## Answered today (owner, all written into the spec)
Q223 (Close lists cancels for own open entry orders), Q225 (+ clarification: ledger stamps recorded_at), Q226, Q227,
Q228 (paid month 30 days / year 365), Q229 (entitlement rules 2-3 confirmed), Q230, Q231 ("safety" allowed), Q232
(Greeks from Advanced only; REQ-006 AC-3 corrected), Q233 + Q236 (TOTAL row), Q234 (Client ID format), Q235 (wording
trust boundary = W-026's; promise phrases), Q237 / ADR-046 (path-filtered `app-tests.yml` for API/web CI); Q222 and
Q224 confirmed. Findings-index wrapper approved until kit #40 is fixed (memory `findings-index-wrapper`).

## PARKED (owner decision needed — do NOT resume without it)
- **W-007 entitlement engine — issue #12.** Rounds 5-6 today. Parked until the DB layer exists (owner's choice): any
  in-memory ledger lets its creator choose the clock, so backdating stays possible until a trusted time source (DB
  insert time / server clock at the application boundary) exists. Branch `build/W-007-entitlements` @ a459ac0.
  Blocks W-008, W-009, W-011.
- **W-024 error messages — issue #30.** Rounds 5-7 today; owner set round 7 as the last. Round 7 failed on the CI scan
  missing relative-import rebinding of the checker. Recommended if unparked: an allowlist rule (no attribute
  assignment on any imported module in `backend/ofo`) + a runtime identity check. Branch
  `build/W-024-error-catalogue` @ a3ef79a.

## BLOCKED (external)
- **Zerodha core proof (ADR-034, Q210):** the owner sent the email; Zerodha asked for additional information; the
  owner will discuss it later. All order/position code runs against fakes; Kite field names are unverified.
- **W-017 audit payload allowlist (REQ-063 AC-5):** needs real Kite Connect responses.

## DEFERRED (open issues — each must be implemented, not closed)
- **#43** item 4: freeze 1,755, 10 orders/batch, "margin impact" meaning are unverified placeholders until the Kite build.
- **#45** price passed through unchecked (REQ-056 AC-7, Q28); no first-entry execution path yet.
- **#29** items 5-6 (integration must read legs from the store; forged alternative strike recorded to history).
- **#10** small verifier findings (W-006 `validate_source` host check, 50% truncation threshold; W-013 AST money guard
  misses `getattr`; W-002 NaN/float tests).
- **#61** fixture guard checks only the head of f-string symbols.
- **#62** Close Partial refusals raise after `mark_closing` instead of returning a message.
- **#63** two ProposedOrder builders (reconciliation/resolution.py:343, rules/actions.py:45) don't slice — unreachable
  to the broker today.
- **#64** reconciliation compare is quadratic in active strategies (0.477 s at 800).
- **#65** wall-clock guard misses timeit / datetime / aliased timers / named-constant thresholds.

## OPEN QUESTIONS still for the owner
Q204, Q205 (Zerodha feed model — wait for Zerodha), Q211 (legal review), Q212 (YouTube transcript), REQ-039's
state-machine transition table (`spec/data/domain-model.md` §6), extra checks kept on exits (W-014), a moneyness
column, OD-e ("buy-backs of shorts go first", a code default not in the spec), the scenario caption shown at all
three UX levels (W-004 builder's call), the TOTAL P&L % "—" cases for missing LTP / multi-expiry (REQ-035
clarification), "safety net" passing the wording check, the W-024 residual reworded promises.

## NEXT (in order)
1. Deferred issues that need no decision: #62, #64, #61, #65, #10 (items 1, 3, 4).
2. API/web layers: the first work item adds `app-tests.yml` (ADR-046) with the first API code — but prove its core
   first (CLAUDE.md, run-discipline): the Zerodha core proof is still the project's real core and is blocked.
3. When Zerodha answers: the core proof (throwaway script, real login, 3 real option quotes per index + margin),
   then W-017 and the Kite adapter behind `send_guard`.

## How the sessions work (reuse it)
- Flow per item: builder (own worktree, `isolation: worktree`) → independent verifier (fresh context, read-only) →
  orchestrator records evidence (`scripts/orchestrator/record_evidence.py <worktree> <W-id> <builder> <verifier>
  <json>`) → CI mirror → PR → `tools/merge_when_green.py` run as its OWN command (the kit guard blocks it after `&&`).
- Brief templates: `docs/process/builder-brief.md`, `docs/process/verifier-brief.md`. Every brief carries Budget
  (builder ≤ 80 tool calls, verifier ≤ 32 — hook-enforced), Core/Proof, Spec basis quoted from the spec, and
  Class/Proof lines on fixes (hook-enforced).
- Verifiers run `git worktree remove` from the MAIN checkout; one left a half-removed folder when run from inside.
- Commit messages with "Claude" in a `-m` string trip the prod-gate hook; use `-F <file>` or a heredoc.
- `sed` patterns containing `.*` trip the prod-gate "dot-directory wildcard" rule; use the Edit tool.
- `scripts/orchestrator/` helpers reach agent worktrees (whose path names the kit folder the guard blocks).
- Before every dispatch: `git pull --ff-only` in the main checkout (finding `agent-worktree-from-stale-local-main`).
- Repeat failures: second red of a class → independent reviewer; third red → park. The owner may choose "one more
  round"; say plainly when a class keeps failing because of the bar or the design (W-007 clock, W-024 denylist).
- Never trust a builder's "all green": re-run on the merge candidate (CI mirror) before the PR.
- Findings registry: `knowledge/findings/` (20 classes); read it before designing.
