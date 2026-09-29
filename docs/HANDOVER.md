# Handover

Updated 2026-09-30 (end of the overnight build session 2026-09-29/30). Main at the merge of this file's PR.
Read this first, then `docs/owner-review-2026-09-30.md` (the owner's morning list), then `spec/open-questions.md`.

## Rule for the next session: nothing pending is closed until it is implemented and verified
Every item under PENDING, PARKED, BLOCKED and DEFERRED below stays open (issue open, work item not `done`) until
its code is merged **and** an independent verifier passed it with evidence (`evidence/<W-id>/`). Do not close an issue
because it "looks done", because a builder said so, or with a partial-fix PR: GitHub closes an issue on any
"closes/fixes #N" in a PR body — for partial fixes write "addresses items of #N" (this closed #43 by mistake once).

## DONE (merged, independently verified, evidence recorded)
Product code is standard-library Python under `backend/ofo/` (domain layer only: no API, DB, UI or real Zerodha yet),
tests under `tests/` — **1218 tests pass** on main.

| Work item | Requirement | What it is | PR |
|---|---|---|---|
| W-001 | REQ-033 | Calculation engine core (P&L, breakevens, max profit/loss) | #5 |
| W-002 | REQ-032 | Engine inputs, Black-Scholes, Greeks, money precision | #8 |
| W-003 | REQ-034 | Scenario level set, two views | #16 |
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

Requirements VERIFIED end to end (`python tools/trace_check.py .`): REQ-020, 032, 033, 038, 040, 057, 058, 059, 060,
064, 070. Others are partly built (their UI or later-stage ACs are not in any work item yet).

## PARKED (owner decision needed — do NOT resume without it)
- **W-024 error messages — issue #30.** Failed 4 times. Needs the owner's call on how strict the advice-word ban is
  (recommendation in the issue). Branch `build/W-024-error-catalogue` @ adda683 holds the last round (not merged; it
  also narrowed strategy-template wording coverage — REQ-028 AC-3 — which must NOT merge as is).
- **W-004 strategy table — issue #21** (AC-7 Guided headers; the failure came from the orchestrator's brief).
- **W-007 entitlement engine — issue #12** (owner decision on the recommended fix). Blocks W-008, W-009, W-011.

## BLOCKED (external)
- **W-017 audit payload allowlist (REQ-063 AC-5):** needs real Kite Connect responses.
- **Core proof with real Zerodha (ADR-034, Q210):** waits for Zerodha's written answer and the owner's Kite credentials.
  All order/position code so far runs against fakes; Kite field names (order_id, trade_id, filled_quantity,
  tradingsymbol formats) are **unverified** until then.

## DEFERRED (open issues — each must be implemented, not closed)
- **#43** execution plan: item 4 open — freeze 1,755 units, 10 orders/batch and "margin impact" meaning are unverified
  placeholders until the Kite adapter build (REQ-056 AC-10). Items 1-3 done in W-028.
- **#45** price is passed through unchecked (price protection = REQ-056 AC-7, Q28); no first-entry execution path yet
  (when built it must go through the broker sink + Strategy Guard). Item 1 done in W-029.
- **#50** Close Partial Strategy does not slice at the freeze limit (a large close would be rejected as one order).
- **#51** 3 fixture symbols in tests/marketdata and tests/range still not in the catalogue (allowlisted in
  `tests/test_fixture_symbols.py` with the issue link — remove each entry when fixed).
- **#29** items 5-6 (active-legs hash is a consistency tie; integration must read legs from the store; forged
  alternative strike recorded to history).
- **#10** small verifier findings from W-002/W-006/W-013.

## OPEN QUESTIONS for the owner (`spec/open-questions.md`, `docs/owner-review-2026-09-30.md` §4)
Q204, Q205 (Zerodha feed model), Q211 (legal — gates discovery/advice-like features REQ-025/027/045/046/068/069),
Q212 (YouTube transcript — REQ-071), **Q223** (Close also lists cancels for the strategy's own open entry orders —
built as orchestrator default OD-m, list only), REQ-039's state-machine table (awaiting owner review), W-024 wording
strictness. Delegated overnight and reversible (ADR-045): **Q222** (agreeing reconciliation run does not unblock by
itself), **Q224** (shared contract disagreeing with Zerodha blocks all holders; no guess-based fixes). The owner's own
actions from the morning list: send the Zerodha email; rotate the Kite secret exposed in public `abhayla/algochanakya`.

## NEXT (in order)
1. Owner answers: W-024 wording rule, W-007 fix, W-004 OK, Q223, and whether Q222/Q224 stand.
2. Deferred issues that need no decision: #51, #50, then #45 item 3 when an entry path is designed.
3. Once Zerodha answers (Q210) and credentials exist: the core proof (throwaway script, real login, 3 real option
   quotes per index + margin), then W-017 and the Kite adapter behind `send_guard` (see
   `spec/technical-design/legacy-reuse.md` "Broker adapter boundary").

## How the overnight session worked (reuse it)
- Flow per item: builder (own worktree, `isolation: worktree`) → independent verifier (fresh context, read-only) →
  orchestrator records evidence with `scripts/orchestrator/ev_agent.py` → CI mirror → PR → `tools/merge_when_green.py`.
- Brief templates: `docs/process/builder-brief.md` (quality bar grows with every finding) and
  `docs/process/verifier-brief.md`. Every brief carries Budget, Core/Proof, Spec basis (quoted from the spec — never
  from memory: 10 overnight brief errors, finding `brief-rule-from-memory`).
- `scripts/orchestrator/`: helpers for agent worktrees, whose path contains the kit folder name that the kit guard
  blocks in Bash — `agentwt.py` (status/release), `agit.py` (git in an agent worktree), `atool.py` (CI mirror),
  `ev_agent.py` + `record_evidence.py` (evidence from verifier JSON), `aregen.py` (regenerate the findings index
  during a rebase), `gh_issue.py` (issues; the kit repo name trips the guard).
- Before every dispatch: `git pull --ff-only` in the main checkout (agents branch from LOCAL main — finding
  `agent-worktree-from-stale-local-main`).
- Repeat failures: second red of the same class → independent reviewer before round 3; third red → park (issue with
  the `parked` label). Verifiers keep finding smaller gaps; agree the bar with a reviewer first (W-026 R1-R3).
- Never trust a builder's "all green" or "pre-existing": re-run on main (two false claims overnight).
- Findings registry: `knowledge/findings/` (18 classes, index regenerated by the kit script); read it before designing.
