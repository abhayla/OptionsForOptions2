# Owner questions, 2026-10-26

## Q1: merge PR #556 (ADR-189, kit 1.14.0 lean process)?

Asked by the night guard's route (L17) at ~00:4x IST; PR #556 stays open and unmerged until answered.
Business call: you set the review and safety level for code that touches real-money orders; only you can accept less
local checking.
Spec basis: ADR-189 amends ADR-178 (3), ADR-181 (1), ADR-171 (8), ADR-112 and ADR-106 (2)(3)(11); each replaced text
is quoted in its SPEC CHANGE section.

Before -> after:
1. Always-loaded text: 23,863 -> 7,715 bytes (CLAUDE.md 17,826 -> 1,678; cap 8,192).
2. Local check before a push: `gate.py`, ~8 min (ruff ratchet, DB-free app tests, OpenAPI compare, frontend
   lint/format/Vitest) -> `tools/ci_local.py`, 57 s measured (kit ci.yml only). App and frontend breaks are now first
   seen in CI.
3. Mutation tests: every builder brief had to run `mutation_gate.py` (check_brief refused without it) -> Tier A guards
   only, at most 5 mutants, not a gate.
4. Reviews: Tier A verifier per PR, Tier B verified at requirement close, independent redesign after a round-2 MAJOR
   -> one checker per item (Opus A / Sonnet B / none C); after round 2 a Tier A CRITICAL/MAJOR parks, anything else
   ships with its findings listed.
5. Row review: 62 KB file (R1-R19, per-row table, meta review every 3rd row, enforced by a test) -> lessons L1-L19
   plus one log entry per item; the test is deleted.
6. ADR-178 tracker: 6.8 KB tracker, a SessionStart hook every session, 935 lines of measuring scripts ->
   `tools/measure_tokens.py` on demand.
7. Evidence: 3 project scripts -> the kit tool behind one wrapper (in-flight refusal kept).
8. Reverses item (3) of ADR-188 on the unmerged chunk-4 docs branch: "The local gate stays for every change, Tier B
   included (ADR-181 unchanged)".
9. Two departures from your message: numbered ADR-189 (188 was taken by the 10-25 speed-rules decision);
   `views/spec-digest.md` regenerated (3 lines) because CI refuses a stale digest.

Options:
- **Approve all, merge (Recommended).** Matches your 2026-10-26 approval; CI green is the last gate. Real case: row 30
  took 276 min, about half of it waiting on gates and reviews.
- Approve, keep local app tests: merge, plus a follow-up so the builder also runs select_app_tests' DB-free files
  before a push (catches app breaks before CI; a few minutes per push).
- Hold the PR: leave #556 open; say which item to change.

Answer: "merge #556" (owner, 2026-10-26 ~01:05 IST; PR #556 merged as 7bd8807a).

## Q2: where does the measure_process record live - row-review.md (ADR-189) or a restored adr-178-tracker.md?

Asked by the night guard's route (L17) at ~02:2x IST by the chunk 4 session A orchestrator.
Business call: two of your instructions conflict and only you choose between them. The chunk 4 session A goal says
"record the measured values in docs/process/adr-178-tracker.md"; your ADR-189 (#556, ~01:05) deleted that file and the
measuring script.
Spec basis: ADR-189 (tracker retired; row-review.md's step-10 log replaces it); ADR-178 (created the tracker).

Facts: the measured values ARE on main in docs/process/row-review.md (#559): chunk 3 session A (a43256ae) context
363k/turn over 627 turns (limit < 250k), 3 rows closed, 0 table prints, 7 Opus dispatches without a safety-set file,
round-2 checkers 8/9/15/17/36 min, 4 local DB runs vs 3 rows, row-10 worst 52 min; this session (c097bcc4) 415k/turn.
Everything else in the goal is met: rows merged or parked with issues (#558 row 31, #560 row 30 AC-1 live half, #561
row 32 marks); handover #559/#562; memory note updated.

Options:
- **row-review.md is the record (Recommended).** ADR-189 wins; nothing to rebuild; the goal counts as met.
- Restore docs/process/adr-178-tracker.md with these values (~15 min docs PR), against ADR-189.

Answer: decided by the spec, not asked (kit 1.15.0 session, 2026-10-26 ~03:00 IST). ADR-189 (merged 7bd8807a at ~01:05)
is the owner's later decision and retires the tracker; row-review.md is the record. The owner's 10-26 prompt says "Ask
me only what the spec cannot answer". Overturn by answering "restore the tracker".

## Q3: may the project opt in to the kit's docs-only CI test list (three record tests, ~13 s per docs PR)?

Business call: ADR-187 (5) records your instruction "do NOT opt in to the docs-only CI test list (1.11.0 item 6) unless
the owner says so"; only you lift it.
Spec basis: ADR-187 (5); ADR-189 (lean CI); finding docs-only-pr-skips-record-scans.

Facts: PR #559 (records only) added passing evidence for W-160 AC-2..4; a docs-only PR runs no test suite, so
tests/test_reach_check_real.py first ran on the push to main and failed ("new 3"). Main stayed red through #559, #562
and #563, and the kit 1.15.0 PR #564 inherited it. PR #565 fixes the instance (three baseline entries). The class fix is
one project file, `.claude/project/ci-docs-only-tests.txt`, listing tests/test_reach_check_real.py,
tests/test_tests_required_exist.py and tests/test_spec_integrity.py: measured 11 passed in 13.29 s locally.

Options:
- **Opt in with those three tests (Recommended).** +13 s per docs PR; a records PR can no longer turn main red this way.
- Stay out (ADR-187 (5) as is). The next records PR that trips a record test turns main red again and blocks every PR
  until someone notices.

Answer: (pending)

## Q4: the step 3 RCA shows classes local app checks would catch; reverse ADR-189 for those triggers only?

Business call: you said "Reversing ADR-189 is my call: if the RCA says so, ask me."
Spec basis: ADR-189 ("the ruff ratchet, app tests and OpenAPI compare now run in CI"); docs/process/ci-reds-2026-10-26.md;
findings db-tests-outside-the-row-red-only-in-ci, e2e-stand-in-drifts-from-server, new-answer-state-without-reader-sweep.

Facts (11 red App-tests PR runs since 10-24, ci-reds-2026-10-26.md):
- 7 database-test reds. 3 named cases were tests the change broke in OTHER files (gate_slots -> test_identifier_and_slots,
  catalogue reply -> test_pinned_clock, migration 0025 -> migration round-trip + shape pins). The selector missed 2 of
  the 3 (domain module, migration) and is fixed on fix/app-test-selector-misses; it already named test_pinned_clock.
  The bigger cause: the real selections were 17, 55 and 81 files, over atool.py's 12-file cap (it refuses and defers to
  CI), and under ADR-189 nobody runs them before the push anyway. So a selector fix alone prevents none of the 3.
- 5 Playwright reds: 1 alias import (now fixed by a static check, no app test needed), 2 new answer state (a repo test,
  no app test needed), 2 e2e stand-ins left on the server's old behaviour: only running those specs catches them.
- No red since 10-24 was lint, format, OpenAPI or build, so ADR-189's general choice still holds.
- Cost of a red: median 9.0 min CI plus a fix round. Cost of the targeted local run: unmeasured (DB tests go through the
  tunnel to the VPS that also serves IPODhan production, so targeted files only).

Options:
- **Targeted only, in a CI job not on this PC (Recommended).** Keep ADR-189 for every other change. When a diff touches
  a migration, a route reply or a socket message, the builder pushes a draft PR first; CI's app tests (database + the
  Playwright specs) are the check before review, and the row's checker waits for that run. No database tests over the
  tunnel to the VPS that serves IPODhan production (55-81 files is too heavy there). Cost: one CI run (~9 min) moved
  before review instead of after; measured over the next 3 rows (step 5).
- Targeted, locally: the builder runs the selected database files through db_run_fresh.py (17-81 files on the
  production host's database) and the stand-in Playwright specs. Not recommended: it loads the production host.
- Keep ADR-189 as is: CI stays the only catch; rows 27, 29, 30 and 31b each paid at least one red database-test run.
- Full reversal: every push runs the local app gate (the ~8-minute ADR-188 gate). Not recommended: it was removed for
  its cost, and the RCA shows no red it would catch beyond the targeted set.

Answer: (pending)
