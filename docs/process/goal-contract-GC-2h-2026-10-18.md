# Goal contract GC-2h (Sun 2026-10-18 night): first build-ahead run of the tracker; nothing product merged

Chain: `goal-chain.md`. Tracker: `build-ahead-tracker.md` (ADR-112). Written 2026-10-18 ~23:05 IST from the owner-approved
build-ahead plan; revised ~23:35 after its full fresh Opus review (GO WITH FIXES: 2 CRITICAL, 3 MAJOR, 4 MINOR, all
accepted - review record in the GC-2h handover). **Owner needed: NO.**
**Cap: the lock time + 7 h, and never later than 2026-10-19 07:30 IST** (GC-3L locks at 08:30; the delta's 08:30
fallback covers `lock/gc-2h`). Chain rule 4b: no close-out before cap - 45 min while an item has an allowed next step.

Core: an execution plan left open from an earlier trading day is never left open and never guessed: the next day it is
auto-closed ONLY when Zerodha's net position shows its orders changed nothing; every other case is a recorded,
sticky mismatch that blocks the strategy until a recorded resolution (ADR-109 (2): a strategy owns "exactly the fills of
orders this app placed"; outside lots are attached "never automatically"; ADR-111: a hand close on Kite "reports a
mismatch and blocks the strategy").
Proof: `tests_app/` cases on the real 2026-10-16 replies (`tests/fixtures/kite_replies/`, plan OFS1V1L0 BUY 65) with
DERIVED next-day replies (orders [] and trades [] as Kite returns them the next day), the base being the net of the
strategy's OTHER stored plans, not 0:
- earlier-day open ENTRY, net = base -> closed `nothing_placed`; net = base + 65 (or + 30) -> recorded mismatch (NOT
  `filled`: the 65 cannot be told from outside lots), strategy blocked;
- earlier-day open EXIT (ADR-111's carry-over) with net = held -> closed `nothing_placed` (the EXIT did not fill; a new
  EXIT can be created); net 0 -> recorded mismatch, lifted only by ADR-109 (4)'s "Kite flat -> mark exited" action;
- the contract expired overnight -> recorded mismatch (or ADR-083 settlement), never `nothing_placed`;
- a same-day open plan is untouched (ADR-110 pending still applies: today's tags are in today's book).
A real next-day positions reply is captured with `probe.py` at GC-3F (Wed 2026-10-21) as the pre-merge real-data proof
(tracker row #352-proof).

## Main stays frozen for product code until GC-3L ends
Every code item ends as an open draft PR (HOLD), CI green (a flake re-run to green, never accepted red), reviewed. Only
the close-out docs PR merges. TRACKER is tooling but is also held (keeps GC-3L's docs-only head shortcut simple) - its
check runs from its branch at close-out.

## Items (tracker ids), in this order
0. Take `lock/gc-2h` (chain rule 2). `git pull` main.
1. **#380-1 migration first** (Tier A, own PR): stored mismatch record + sticky block lifted only by a recorded
   resolution (Q222) + standalone store (REQ-060 AC-7) + a close reason for an earlier-day plan the positions cannot
   settle (`unresolved_from_positions`, with the resolution source) so the plan closes, one-open-plan stops blocking,
   and the mismatch record carries the block. DB test file via `db_run.py`, that file only. Draft PR, HOLD.
2. **#352-1 next-day resolution** (Tier A, the core; fresh Opus builder, fresh Opus review, at most 2 rounds), stacked
   on #398 + item 1. Never closes from the book alone (keep `execution_return.classify`'s rule, `:23-24`, `:117-118`).
   Builds the cases in the Proof. "Adopt the next-day net as the strategy's fill" is NOT built: parked as owner question
   OQ-GC2h-1 (`Business call:` it decides what a strategy holds) in `owner-questions-2026-10-19.md`. Draft PR, HOLD.
3. **Small Tier A defects**, one stacked PR per area, failing test first, fresh Opus review each:
   - #338: a reduce-only basket needing 0 margin is never blocked by a negative balance (real closing reply
     `margins-basket-exit-150717.json`);
   - #353: the Kite allow-list is checked per calling module;
   - #63 + #43 + #255 (ADR-092, OQ-2 answered "Never split anywhere"): both ProposedOrder builders
     (`reconciliation/resolution.py:343`, `rules/actions.py:46`) and Complete / Retry / exit BLOCK above the stored
     freeze limit with the reason and the limit, never slice; the 1,755 placeholder is removed; the review lists no
     slices.
4. **TRACKER** (Tier B): `scripts/orchestrator/tracker_check.py` (stdlib) + test. Fails when: a row's PR/issue state on
   GitHub contradicts its status (held/merged vs PR state; a `closed` row whose issue is open; an open status whose
   issue is closed); an open issue has no row; a row was deleted (compare Ids with the tracker at `origin/main`); a
   status word is outside the closed list; a non-closed row has no contract (contracts `owner`, `stage-5` are allowed
   names). `--offline FIXTURE` for tests. Draft PR, HOLD.
5. **#403 + BUDGET** (Tier C/B, only if time): local Windows pytest past EgressRefused (pytest-metadata
   `platform.platform()`; the eslint-run test); the budget gap goes to the kit handoff file as a new item if it is a
   kit hook.
6. **Close-out** (cap - 45 min, or earlier only when items 1-4 are PASSED-and-held or parked with no next step): tracker
   rows updated + `tracker_check.py` green (run from its branch); main clean; worktrees released (files + packages
   counted); handover `session-handover-2026-10-19-gc2h.md` (<= 40 lines; the review record); goal-chain: GC-2h
   DONE/PARTIAL, GC-3L NEXT; GC-3F draft step 1 gains GC-2h's held PRs in stack order; one docs PR via `land.py`; lock
   deleted; prompt, 5-line summary, scorecard, evidence table.

## Rules (checkable)
Every brief passes `check_brief.py` and carries Core/Proof, `Copy from:`, `Findings checked:` (grep the registry; at
least caller-supplied-verdict-trusted, state-with-no-working-exit, guard-as-forbidden-list where relevant), `Threat
model:` for a guard, `Budget:` (builder <= 80 tool calls; Explore/verifier/reviewer <= 32), `Report: evidence-table`,
the B4 standing items, Class/Proof on a fix, and the 2026-10-18 lessons (quote the AC text; list every stored-data
state - plan open/closed/exited, same-day/earlier-day, fills stored or not, other strategies, standalone, expired
contract; register a new ApiModel in `tests_app/test_response_door.py`; `coverage.py . --check` before a push).
`check_pr_spec_block.py --body-file` before every `gh pr create`. Windows pytest: `-p no:metadata`. No Kite call, no
write to ofo_dev, DB tests targeted only (the VPS PostgreSQL also serves IPODhan production).

## Stops
None needs the owner. A product merge before GC-3L ends, a Kite call, or an owner decision not in ADR-092/105/109/110/111
-> park that item (owner question file) and continue with the next.
