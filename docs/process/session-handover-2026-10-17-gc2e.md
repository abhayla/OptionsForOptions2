# Session handover 2026-10-17: goal contract GC-2e (live-order preparation) - DONE

Ran 2026-10-17 17:25 IST under `/goal`. Contract: `goal-contract-GC-2e-2026-10-18.md` (cap 6 h -> 23:25 IST, tail
from 21:55). Next: **GC-3** (`goal-contract-GC-3-2026-10-19.md`, marked NEXT) - the owner-present live 1-lot run on a
trading day; independently reviewed (NOT READY -> 10/10 findings applied -> re-checked):
`gc-3-contract-review-2026-10-17.md`.

## DONE (merged on main)
- **RUNNING marker:** PR #363.
- **Item 1** - base confirmed: #358 (W-096) and #361 (W-100) merged (`gh pr view`, `git log origin/main`).
- **Item 2, W-101 test-only Execute/return replay** (#365): `EXECUTE_REPLAY=1` refused outside `APP_ENV=test` before any
  router; recorded 2026-10-16 replies behind both routes; seed (test DB name only; Pro grant on the database clock);
  the replay module is imported only after the switch check and reads fixtures lazily. Core proof in CI on
  2026-10-17: `POST /strategies/1/execute 200`, `POST /strategies/1/execution/return 200`, 1 passed. Tier A REVISE
  (MAJOR: proof could pass only on 2026-10-16; MAJOR: production start-up read a test fixture) -> fixed.
- **Item 3, W-102 the full cost in the Execute reply** (#368): signed net premium (BUY pays -217.75), charges from the
  engine's calculator at the stored rates (entry 23.70; exit 24.01 = Zerodha's own `charges.total` in the real exit
  reply), Zerodha funds + margin from the one `_context` read, `figures_read_at`. Exit margin shows 0.00 per ADR-099.
  Tier A PASS (3 MINOR).
- **Item 4, W-103 audit events on both routes** (#367): `order_prepared` declared (migration 0017, real downgrade,
  refused once rows exist), written in the `record_plan` transaction; return route writes `broker_response_recorded`
  per order and `execution_recorded` once per trade, database clock. Tier A PASS; 1 MINOR applied (frozen pre-0017
  type list). Three CI reds: empty-migration guard, function-body pins (0017 now publishes its own pins; the test reads
  the head's), PR-body path.
- **Item 5, W-104 the Execute screen** (#372): live socket held before Execute; orders + cost strings as returned; the
  OWNER's click posts `basket.api_key`/`basket.data` to exactly `https://kite.zerodha.com/connect/basket` in a new tab;
  "Check with Zerodha"; `/execution/returned` page. **Core proof (contract):** CI job `execute-screen-e2e` green on
  fdbbe37 (run 39037011194). Tier A PASS (4 MINOR, all applied).
- **Item 6, W-105 basket return** (#369): research found Kite returns the browser to the SAME registered redirect URL
  as login (F-41) - our callback would have shown a login error after real orders. Fix: a no-`state` hit lands on
  `/execution/returned`, no token exchange, nothing stored; the callback's access-log line drops the whole query.
  Tier A REVISE (MAJOR: `request_key` logged in clear) -> fixed, re-check FIXED.
- **Item 7, W-106 holdings read** (#366): `GET /portfolio/holdings` on the read door; eight fields kept and compared
  (review MAJOR: `used_quantity` etc. were missing - a same-day sale could read as "unchanged"); fail closed.
- **Item 8, audit store stamps its own time:** (#373) `audit_store.append` takes no time from its caller and reads `clock_timestamp()` after the lock; all four callers updated (catalogue, entitlement, Execute, return). Tier A PASS; its 2 MINOR test gaps closed with a sentinel-clock test that goes red if the app clock is used or the read moves before the lock. Side effect: the old `order_audit` read its time before the lock, so a >60 s lock wait could have tripped the trigger - removed.
- **Item 9, `repo_scan` marker** (#364): `pytest -m repo_scan tests` runs every repo-wide scan (909 tests, ~60-117 s);
  named-list + shape collection check; `check_brief.py` requires `-m repo_scan`. It caught one scan-shaped helper in
  W-103 locally before CI - its first real catch.
- **Item 10:** GC-3 written, independently reviewed (verbatim record), all findings applied, re-checked; docs batch 1
  (#371) + this close-out PR.

## PARKED / CARRIED (by name)
- **OQ-13** (W-104 branch, `owner-questions-2026-10-17.md`): a strategy saved without planned entry prices dead-ends
  on the Execute screen (ENTRY and EXIT). GC-3 avoids it by saving from the builder while live.
- **OQ-11, OQ-12** + the wordings "Back from Kite" and "Not available from Zerodha": owner wording questions.
- **#370 (deferred):** intermittent `strategy-save-draft.spec.ts:71` e2e failure (2 of ~10 PR runs; main green).
- The GC-2e carry-over list (contract section "Carry-overs") - none done this run, all still open.

## Misses (each recorded)
- Four wrong rules in the orchestrator's briefs (finding `brief-rule-from-memory`, 14th occurrence): undeclared audit
  keys "refused" (spec: dropped; caught before dispatch), exit margin "as given" (ADR-099: 0), two requirements on one
  card, "no regenerated files" (openapi.json is test-checked). Mechanism this run: builder-brief lines for openapi.json
  and migration guards.
- The verifier-type reviewer's write-guard quarantined a parallel builder's work card (finding
  `verifier-guard-watches-every-worktree`, 4th occurrence); reviewers then ran as read-only Explore agents.
- Integrator misses: no CI mirror on W-103 before its PR (empty-migration red), and no ratchet after merging main into
  W-101 (PLR2004 red).
- Every builder appended a row at the same spot of `coverage-stages.yaml`: one-line conflict on every landing
  (run-discipline C2, shared file in feature PRs).
- `land.py` could not take an agent id and failed after its own update-branch: both fixed (#371) with tests.
- Builders over budget (tool calls used / budget): W-101 93/72 (first round), W-102 131/60, W-103 110/72, W-104 99/76; within budget: W-105 44/50, W-106 42/45, repo-scan marker 45/45, item 8 47/50. The over-budget four were the Tier A items whose briefs carried wrong rules or whose work waited on the verifier gate.

## Scorecard
CI runs = GitHub workflow runs per branch (`gh run list --branch`, all workflows). Tool calls = first round used / budget.

| Item | Review rounds | CI runs (failed) | Local full-suite runs | check_brief | Idle > 10 min | Budget overruns |
|---|---|---|---|---|---|---|
| RUNNING marker (#363) | 0 | 3 (0) | 0 | - | 0 | 0 |
| 1 base confirmed | - | - | 0 | - | 0 | 0 |
| 2 W-101 replay (#365) | Tier A 1 (REVISE) + CI as re-check | 33 (5) | 0 | y | 0 | 1: 93/72 |
| 3 W-102 cost (#368) | Tier A 1 (PASS) | 18 (2) | 0 | y | 0 | 1: 131/60 |
| 4 W-103 audit (#367) | Tier A 1 (PASS) + MINOR round | 26 (8) | 0 | y | 0 | 1: 110/72 |
| 5 W-104 screen (#372) | Tier A 1 (PASS) + MINOR round | 17 (4) | 0 | y | 0 | 1: 99/76 |
| 6 W-105 basket return (#369) | research + Tier A 1 (REVISE) + re-check | 16 (1) | 1 integrator domain pass | y | 0 | 0 |
| 7 W-106 holdings (#366) | Tier A 1 (REVISE) + re-check | 12 (0) | 1 integrator domain pass | y | 0 | 0 |
| 8 audit store clock (#373) | Tier A 1 (PASS) + MINOR round | 9 (1) | 0 | y | 0 | 0 |
| 9 repo_scan marker (#364) | Tier B 1 (REVISE) + fix | 8 (1) | 0 | y | 0 | 0 |
| 10 docs + GC-3 (#371 + close-out) | GC-3 review 1 (NOT READY -> applied) + re-check | 4 (0) so far | 0 | - | 0 | 0 |

"Local full-suite runs": the integrator ran the domain suite (no DB) twice through `atool.py` (W-106, W-105), per the
GC-2e process rule; no local full app (DB) suite ran. CI failures were mostly one-cause repeats: the shared
`coverage-stages.yaml` row conflict and the new-issue stage check, a stale `openapi.json`, the migration guard and
pins, PR-body path, two ratchet rises after merging main, and two intermittent e2e flakes (#370).
