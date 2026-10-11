# Handover

**2026-10-10 late — START HERE: `docs/process/session-handover-2026-10-10b.md`** (then the prompt
`docs/process/next-session-prompt-2026-10-11.md`). Merged: #192 (#155 hook, partial), #193 (owner answers, ADR-073),
#194 (W-068 leg picker, verified). Stopped for low memory on the VPS (owner). NEXT: #148 door once memory allows;
Monday 2026-10-12 W-065 live proof with the owner's Kite login.

**2026-10-10 ~04:45 IST — START HERE: `docs/process/session-handover-2026-10-10.md`** (work now runs on the Windows
VPS, whose PostgreSQL also serves IPODhan production: light local runs, heavy in CI). W-061, #163 and W-067 merged and
verified; W-066 parked (#172); W-065 waits for the owner's Kite login. Owner items: `docs/process/owner-questions-2026-10-10.md`.

**2026-10-07 ~22:00 IST — end of session; START HERE: `docs/process/session-handover-2026-10-07.md`** (what is done,
what is next, how to set up another PC, and the working rules the owner set). Stages 0-3 done; Stage 4a step 1 (core
data proof on the owner's account, F-29) done; W-057 (contract identity over time, ADR-057..059) merged as #125 and
verified. NEXT: Stage 4a step 2 - the live market-hours checks (needs one owner Kite login after 09:15 IST).

**2026-10-07 ~20:00 IST — Stages 0-2 done.** Stage 0-1 merged as #121 (findings F-11..F-28, coverage register with its
own CI check, research docs, surprise register, architecture page claude.ai/artifact/NoPqsrgmK8KvX6TiCo1Xi1). Stage 2
decisions ADR-051..ADR-056 (see the "Stage 2 outcome" block in the master plan). NEXT: Stage 3 - update and create the
requirements these decisions and findings touch, then the Stage 4a approval batch. Owner actions (Zerodha email,
legal question, Kite app at 4a): `docs/process/owner-actions-2026-10-07.md`.

**2026-10-07 18:45 IST — the order of work changed (owner-approved master plan).** Read
`docs/process/master-plan-2026-10-07.md` first. Core first: Stage 0 full spec read + coverage register → Stage 1 all
research (`docs/research/research-plan-2026-10-07.md`) → Stage 2 owner decisions one at a time (D1 = an ADR-034/ADR-050
exception to prove the core on the owner's own Zerodha account) → Stage 3 requirements → Stage 4 the core (live data →
engine → saved strategy → screen → one real order → reconcile → one rule firing) → Stages 5-8 around it. NEXT below
("P2b identity") is superseded: identity is Stage 5. The build plan's rules and copy-first map stay.

**2026-10-02 15:42 IST — where it stands now (supersedes the 09:34 note below where they differ).**
Merged today (#99-#114, each Tier A/B item independently verified, evidence in `evidence/<W-id>/`): kit 1.5.1 (#99),
P0 copy-first map ADR-047 (#100), P1 decisions Q256 + ADR-048 (#101), W-051 platform + trusted database clock (#102),
ADR-049 styling (#103), REQ-009/REQ-004 approved (#104), W-052 PostgreSQL audit store (#105), W-054 frontend skeleton +
navigation + live health page (#106), W-055 responsive check (#108), W-053 catalogue in PostgreSQL (#109), W-007
entitlement engine on the database clock, unparked and done (#111), ADR-050 cross-broker identity + findings
F-01..F-09 (#113), W-056 catalogue re-keyed on (exchange segment, exchange token) with Zerodha ids in
`broker_instruments` (#114; finding F-10: Zerodha's `exchange` column is not a segment, 30 real NSE collisions).
- App CI (`app-tests.yml`, PostgreSQL 16, database tests required): 475 passed on the W-056 head; domain suite 1429.
- The databases exist only in CI. The VPS test database (ADR-048) waits for the owner's `GLOBAL.env`
  WINDOWS_VPS_PG_ADMIN_USER / _PASSWORD.
- NEXT: P2b identity (Google sign-in, WhatsApp OTP via the Notifier) needs owner approval of REQ-012, REQ-002, REQ-003,
  REQ-013, REQ-014 and the Google OAuth client credentials; then W-008, W-009, W-011. P3/P4 stay blocked on Zerodha's
  written answer (ADR-034) and Q258 (SEBI algo provider / static IP).

**2026-10-02 09:34 IST — the build plan changed.** Kit 1.5.1 is merged (#99). The owner approved an end-to-end build
plan after an independent review: `docs/process/build-plan-2026-10-02.md` (phases P0-P6, copy-first from algochanakya
per ADR-047, the full module map in `spec/technical-design/legacy-reuse.md`). It supersedes "NEXT" below; the DEFERRED,
PARKED and BLOCKED lists stay valid and are mapped into its phases (P0.5 = NEXT item 1).

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
- (Unparked 2026-10-02: W-007 is done on the database clock, #111; W-008, W-009, W-011 now wait only for P2b identity.)
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
- **#63** two ProposedOrder builders (reconciliation/resolution.py:343, rules/actions.py:45) don't slice — unreachable
  to the broker today; depends on the #43 freeze placeholder, so it moves to build plan P4.
- **#89** three user-text paths not yet on the shared wording checker.
- **#107** scheduled audit-log verification monitor (REQ-064, P6).
- **#110** responsive check misses content clipped by overflow:hidden (REQ-004).
- **#112** entitlement ledger index and server-side free-day cap (REQ-017, with W-008/W-009).
- **#115** execution layer links orders to the catalogue by Zerodha symbol, not `InstrumentId` (W-056 review M2; P4);
  finding `instrument-identity-keyed-on-one-broker` stays unguarded until it is done.
- **#116** verify on real data whether an expired contract's exchange token can be reused (W-056 review M3; unverified).
- Corrected 2026-10-02: #10, #29, #61, #62, #64, #65 are CLOSED (W-036 #69, W-037 #70, W-038 #72, W-039 #73; `gh issue
  view` state CLOSED); this list had not been updated after those merges.

## OPEN QUESTIONS still for the owner
Q204, Q205 (Zerodha feed model — wait for Zerodha), Q211 (legal review), Q212 (YouTube transcript), REQ-039's
state-machine transition table (`spec/data/domain-model.md` §6), extra checks kept on exits (W-014), a moneyness
column, OD-e ("buy-backs of shorts go first", a code default not in the spec), the scenario caption shown at all
three UX levels (W-004 builder's call), the TOTAL P&L % "—" cases for missing LTP / multi-expiry (REQ-035
clarification), "safety net" passing the wording check, the W-024 residual reworded promises.

## NEXT (in order) — superseded by `docs/process/build-plan-2026-10-02.md`
Current step (15:42): P1 and P2a are done (W-051..W-056, W-007). Next is P2b identity, see the status block at the top.
Owner decisions taken 2026-10-02: Q256 (skew 60 s), ADR-048 (test DB on the VPS, isolated and capped).
Owner to fill `GLOBAL.env` WINDOWS_VPS_PG_ADMIN_USER / _PASSWORD (used once to create ofo_test + ofo_app).
1. (Done before 2026-10-02) Deferred issues that need no decision: #62, #64, #61, #65, #10 (items 1, 3, 4).
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
