# Session handover 2026-10-17 early morning: goal contract GC-2b (Kite replies into the domain, eligibility from Zerodha)

Ran 2026-10-17 01:23 IST -> 2026-10-17 ~04:15 IST in the same session as GC-2a, under the same `/goal` (cap 6 h, 07:23). Contract:
`goal-contract-GC-2b-2026-10-17.md`. Next: **GC-2c** (`goal-contract-GC-2c-2026-10-18.md`, marked NEXT).

## DONE
- **RUNNING marker:** PR #342.
- **Item 1, core - W-091 Kite reply adapter: MERGED** as PR #343 (d61fcfb, 02:17). The owner's real replies (redacted
  fixtures `tests/fixtures/kite_replies/`, client id replaced) go through ONE adapter (`ofo_app/kite_replies.py`) into
  the ledger and reconcile: entry 65 long NIFTY26O1923650CE, 0 mismatches; exit flat, 0 mismatches; P&L -130.00 =
  Kite's flat-row `unrealised`; trade ids 4484194 / 5966618 once; three money shapes (strings, JSON numbers, SDK
  floats). Decisions ADR-102 (P&L at the paisa; a broker AVERAGE price kept exact, 5.125 stays) and ADR-103 (an
  out-of-order fill is refused and blocks, never a side flip). Tier A: round 1 REVISE (MAJOR: an integer average -
  Kite's `0` on every open order - crashed; introduced by the orchestrator's own exact-average edit), round 2 PASS.
  NOT done, moved BY NAME to GC-2c: the strategy record exits when the ledger reaches 0 (RESULT gap e).
- **Item 2 - W-092 eligibility from Zerodha: MERGED** as PR #346 (e825d8f, 02:55). ADR-104: eligible = in Zerodha's
  current list (the catalogue store's latest load) and not expired on the India date; margin-reply refusals only
  remove tradability; the pre-execution gate accepts only a sealed `ZerodhaEligibility`. Save/restore refuse a NEW
  ineligible leg; stored legs never block a save. Core: NIFTY 23650 CE tradable from the recorder's 2026-10-16 list,
  23550 CE refused by the real gate. Tier A: round 1 REVISE (MAJOR: the gate trusted any registry its caller handed
  it - `caller-supplied-verdict-trusted`, 6th occurrence), round 2 PASS.
- **Item 3 - ADR-058 delisted-held -> reconciliation: MERGED** as PR #347 (029fc73, 03:01). A strategy holding a
  delisted contract (long or short) is blocked `delisted_held`; flat ones untouched; ambiguity raises before any block.
  Tier A PASS. Caller needs the persisted order book (GC-2c).
- **Item 4 - W-017 broker-reply audit allowlist: MERGED** as PR #349 (64bdf50, 04:02). `broker_response_recorded` and
  `execution_recorded` declared from the two real samples each (no client id, no token, no free text); a non-empty
  payload keeping no declared key is refused; migration 0015 with a real downgrade (round 1's raising downgrade failed
  the replay tests in the local mirror and left the shared test DB at 0013 - restored). Tier A: round 1 REVISE (MAJOR:
  `reconciliation_recorded` silently emptied), round 2 PASS. Session types: unproven until GC-3's login.
- **Item 5 - W-081 AC-1/AC-3/AC-4 verified on main** (fresh Sonnet verifier, PASS; AC-3's "shown as a planning
  estimate" half has no renderer yet - GC-2c with the review screen). Evidence `evidence/W-081/`.
- **CI flake #344 found and fixed: MERGED** as PR #348 (a16212b, 03:21). Second round of the class -> an independent
  Opus investigation proved it on a failing CI run: an ANALYZE during the scale test's uncommitted 601k-row seed records
  0 rows, and on the 6th execution asyncpg's prepared lookup switches to a generic plan that times out. Not the egress
  gate (149 audit events on the store thread; Python idle 4.9 of 27 s). Fix: `plan_cache_mode = force_custom_plan`;
  the test now reproduces the zero-row statistics on purpose and asserts they happened.
- **Item 5b (hook false block):** workaround used twice (stale snapshots deleted after confirming no verifier ran);
  the fix moves to GC-2c (finding `liveness-from-a-file-nobody-deletes`, 2 occurrences, kit issue #113).
- **Item 8 - GC-2c:** written from these results, independently reviewed (review recorded verbatim in
  `docs/process/gc-2c-contract-review-2026-10-17.md`, each finding accepted or rejected), marked NEXT.

## Misses (each recorded the same turn)
- A gate and its push sent as parallel calls -> a commit with a risen ratchet was pushed (new finding
  `gate-run-in-parallel-with-its-action`).
- Briefs did not warn builders about the producer-inventory scan (sentence-shaped text) after W-091 hit it -> W-092
  hit it too.
- Builders over budget: W-091 88/80, W-092 122/75 and 96/75, ADR-058 97/60, investigation 85/80.
- The mirror's migration tests moved the shared test DB to 0013 (new finding `branch-migration-tests-move-shared-db`);
  restored to main's head 0014.

## Open / deferred
- #338 (negative balance blocks a closing basket), #344 follow-up (whole-table hash per batch under zero-row stats).
- OQ-10 (owner): breakeven columns vs charges.

## Scorecard
CI runs = GitHub workflow runs on the branch after 01:20 IST (about 4 per push). Tool calls = used / budget.

| Item | Review rounds | CI runs | Local full-suite runs | check_brief | Idle > 10 min | Budget overruns (tool calls) |
|---|---|---|---|---|---|---|
| RUNNING marker (#342) | 0 | 3 | 0 | - | 0 | 0 |
| 1 W-091 adapter (#343) | Tier A 2 (REVISE MAJOR -> PASS) | 17 (red: my pushed ratchet rise; producer inventory; flake) | 0 | y | 0 | **1**: 88/80 |
| 2 W-092 eligibility (#346) | Tier A 2 (REVISE MAJOR -> PASS) | 9 (red: flake) | 0 | y | 0 | **2**: 122/75, 96/75 |
| 3 ADR-058 (#347) | Tier A 1 (PASS) | 9 | 0 | y | 0 | **1**: 97/60 |
| 4 W-017 (#349) | Tier A 2 (REVISE MAJOR -> PASS) | 14 | 0 (one mirror run of the 14 migration files - the shared-DB miss) | y | 0 | 0 |
| 5 W-081 re-verify | verifier 1 (PASS) | in docs PR | 0 | y | 0 | 0 (30/30) |
| #344 flake (#348) | independent investigation + Tier B 1 (PASS) | 8 + 24 diagnostic | 0 | y | 0 | **1**: investigation 85/80 |
| 8 GC-2c + handover | contract review 1 (7 findings accepted) | docs PR | 0 | y | 0 | 0 |

Broken rules recorded the same turn: a gate and its push as parallel calls (`gate-run-in-parallel-with-its-action`,
new); the producer-inventory scan not named in briefs after its first hit; four builder budget overruns
(`builder-budget-is-prose`); the shared test DB moved by a branch's migration tests (`branch-migration-tests-move-shared-db`,
new); `caller-supplied-verdict-trusted` hit again (6th) - its mechanism is GC-2c item 5b.
