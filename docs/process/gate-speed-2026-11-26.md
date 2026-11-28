# Gate speed, 26 Nov 2026: results, equivalence table and adoption steps (lane G)

Spec basis: ADR-189 (delivery) and `docs/process/runbook.md` "Before a push" (the gate `scripts/orchestrator/prepush.py`);
ADR-191 (docs-only changes still run the records tests). Process documentation only: no product code, no spec decision
rows. Branch `chore/gate-speed-1126`. Data: harness comparison, 12 seeds, old gate = `prepush.py` at `049406e4`, new gate =
`prepush.py` at `b323efd3`.

## Summary

On the branch head (`b323efd3`, a 418-file diff against main) the gate went from 1784.1 s to 713.1 s: 2.5x faster, same
result (PASS, same marker). A small code commit went from 593.9 s to 469.7 s and a frontend-only commit from 1154.8 s to
538.6 s. Red runs reach their first red line in 0.1 to 1.2 s instead of 416 to 473 s (the old gate only reported
anything after the preflight finished). The honest note on the docs lane: a docs-only change saves little (609.2 s to
445.9 s, and most of that is the parallel run, not the lane), because on a docs-only change the selectors already ran no
code-only stage; the lane skips nothing and only adds the `tests_app` files that read docs paths. Equivalence: 12 of 12
seeds give the same TOTAL and the same marker decision in both gates, with 0 step mismatches. One seed
(`app_fail` v2) shows a gap both gates share: neither runs a changed `tests_app` test file. The comparison's own verdict line
reads "NOT EQUIVALENT (2 problem(s))" and both problems are that `app_fail` seed being invalid (the old gate passes it).
Reviewed by an independent Opus pass: PASS, no MAJOR finding. The Windows branch is proven only by mocks.

## What changed

Commits on `chore/gate-speed-1126` touching the gate, its tests, the runbook and the findings, newest first
(`git log --oneline 2ed05a7..HEAD -- scripts/orchestrator tests/orchestrator docs/process/runbook.md knowledge/findings`):

```
d9a30615 Gate equivalence harness: every seed run starts with no build output left by the previous one
d76efb84 Gate equivalence harness: the mutation test no longer depends on a seed already in the tree
1b2b678a Findings index: regenerate after merging the fix branch (193 findings)
2356a087 Merge remote-tracking branch 'origin/fix/ic-live-test-1123' into chore/gate-speed-1126
b323efd3 prepush: review round 1 (docs lane skips nothing; lane on the start sha; Ctrl-C kills the tree)
a6cd6a1b prepush: docs-only lane, and a proxy-variable NOTICE
d36b8e5b prepush: --jobs N runs the long stages side by side
5ede8cb9 prepush: run the seconds-long checks before the long stages
318cd033 Finding: an owner question asked without the requirement that answered it; coverage rows for new issues
049406e4 Gate equivalence harness: drop unused noqa (ruff ratchet)
d1b949e8 Gate equivalence harness and seeded-failure commits (lane G)
f7887c4d Runbook: fast pre-check before every prepush run (owner, 26 Nov; 12 failed gate runs that day)
```

- **Cheap-first order (5ede8cb9).** the seconds-long checks (ruff ratchet, coverage, alembic guard) run
  first, then frontend lint and build when `frontend/` changed, then the long stages. A red cheap check is on screen in
  seconds.
- **`--jobs N` / `PREPUSH_JOBS` (d36b8e5b).** The preflight, ci_checks, domain tests, app tests and vitest run side by side.
  The option wins over the variable; default is the CPU count; below 1 or not a number is a usage error (exit 2).
  `--jobs 1` is the plain serial loop, kept as the reference.
- **Preflight fail-fast with process-tree kill.** A red preflight stops the steps not yet started and kills the running
  ones with their whole process tree (Ctrl-C does the same and writes no marker; on Windows via taskkill).
- **Per-step temp roots.** Every child gets its own temp root `<tempdir>/ofo-prepush-tmp/<repo hash>/<step>` in both
  modes, so parallel steps do not collide.
- **Structural marker check.** The marker is written only when every planned step has a passing result, the tree was
  clean from start to end, HEAD did not move and no untracked file sits under backend/, tests*/, scripts/ or frontend/src/.
- **Mode in the marker.** The marker records `mode` (jobs and lane).
- **Proxy NOTICE (a6cd6a1b).** The gate prints a NOTICE naming any proxy variable it finds set.
- **Docs-only lane (a6cd6a1b, fixed in b323efd3).** When every path changed between the merge base and the start sha is a
  records file, the report and marker say `docs-only (<n> files)`. After review round 1 the lane skips NOTHING (it used
  to skip ruff_ratchet and alembic_guard, which could write a marker the old gate refused if either was red for
  environmental reasons) and adds the `tests_app` files that read a docs-folder path. The lane is decided on the start sha,
  not the live HEAD, and a branch that edits `tools/change_scope.py` runs the full lane.
- **Harness and findings.** `d1b949e8`, `049406e4`, `d76efb84`, `d9a30615` build and fix the equivalence harness;
  `f7887c4d` is the earlier fast pre-check rule this work replaces; `318cd033`, `1b2b678a` are findings/coverage upkeep.

## Equivalence

**Method.** 12 seeded commits (clean_code, ruff, coverage, money_scan, domain_fail, app_fail, vitest_fail, lint_fail,
alembic_heads, docs_clean, docs_spec_break, frontend_clean), each a sibling commit on `b323efd3` inside a scratch clone
whose `origin/main` was set to `b323efd3`, so each seed's merge-base diff is the seed alone and both gates saw identical
inputs. Runs were serial, one gate at a time, on a 4-core / 15 GB cloud container, each with the owner-approved prefix
`env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy -u TEST_DATABASE_URL
-u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL -u OFO_REQUIRE_DB_TESTS` (the container's HTTPS proxy turns
`tests_app/test_kite_broker_reader.py` attack2's expected EgressRefused into "HTTP Error 400"; issue #754). Per seed the
harness compares each step's PASS/FAIL and the TOTAL line plus marker.

Things that went wrong on the way, kept so the next run is not surprised:
- Seeds were first built on `origin/main` `d387d4cd`, which itself fails the gate's preflight interface layer (2 mypy
  call-arg mismatches, `tests_app/test_stored_chain_real.py:144` "Too many positional arguments for ChainCatalogue /
  FuturesCatalogue"), so every run stopped there. Rebuilt on `b323efd3`, which passes the full old gate.
- `domain_fail` / `app_fail` v1 used `assert 1 == 2`, which also raised ruff PLR0133 (preflight red); rebuilt as v2
  `assert <module> is None`.
- The first new-gate pass on six seeds was invalid: the harness reused one checkout and a `frontend/dist` left by a
  previous seed made preflight layer 0 red in 0.1 s. Re-run from no dist (the state of the old runs); the harness now
  resets `frontend/dist` before every seed (`d9a30615`).
- The lint_fail seed's domain_tests is red in BOTH gates because our own harness test
  `test_mutations_edit_a_copy_of_the_tree` fails on a tree that already carries a seed (fixed in `d76efb84`).
- A builder worktree under `.claude/worktrees` doubled every ruff count and made preflight red (issue #755).

**Table** (commit x step x old x new). "-" = the step did not run. Where the old gate's preflight was red it stopped there
and ran nothing else, so the new gate's extra rows are "new-only". Rows marked "stopped" are new-gate steps killed by the
preflight fail-fast: each one's own log ends `FAIL: stopped: preflight failed` (checked for money_scan app_tests and
alembic_heads domain_tests; alembic_heads app_tests is a real red, `1 failed` in
tests_app/test_alembic_migration_guard.py::test_real_versions_pass).

| commit | step | old | new | note |
|---|---|---|---|---|
| clean_code (5ea874f9) | preflight | PASS | PASS |  |
| clean_code (5ea874f9) | ci_checks | PASS | PASS |  |
| clean_code (5ea874f9) | domain_tests | PASS | PASS |  |
| clean_code (5ea874f9) | app_tests | PASS | PASS |  |
| clean_code (5ea874f9) | ruff_ratchet | PASS | PASS |  |
| clean_code (5ea874f9) | coverage | PASS | PASS |  |
| clean_code (5ea874f9) | alembic_guard | PASS | PASS |  |
| clean_code (5ea874f9) | TOTAL | PASS marker=yes | PASS marker=yes |  |
| ruff (9b992110) | preflight | FAIL | FAIL |  |
| ruff (9b992110) | ruff_ratchet | - | FAIL | old stopped at preflight; new reports it |
| ruff (9b992110) | coverage | - | PASS | old stopped at preflight; new reports it |
| ruff (9b992110) | alembic_guard | - | PASS | old stopped at preflight; new reports it |
| ruff (9b992110) | app_tests | - | PASS | old stopped at preflight; new reports it |
| ruff (9b992110) | domain_tests | - | PASS | old stopped at preflight; new reports it |
| ruff (9b992110) | ci_checks | - | PASS | old stopped at preflight; new reports it |
| ruff (9b992110) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| coverage (defd1144) | preflight | FAIL | FAIL |  |
| coverage (defd1144) | ruff_ratchet | - | PASS | old stopped at preflight; new reports it |
| coverage (defd1144) | coverage | - | FAIL | old stopped at preflight; new reports it |
| coverage (defd1144) | alembic_guard | - | PASS | old stopped at preflight; new reports it |
| coverage (defd1144) | domain_tests | - | PASS | old stopped at preflight; new reports it |
| coverage (defd1144) | app_tests | - | PASS | old stopped at preflight; new reports it |
| coverage (defd1144) | ci_checks | - | PASS | old stopped at preflight; new reports it |
| coverage (defd1144) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| money_scan (8200b0f9) | preflight | FAIL | FAIL |  |
| money_scan (8200b0f9) | ruff_ratchet | - | PASS | old stopped at preflight; new reports it |
| money_scan (8200b0f9) | coverage | - | PASS | old stopped at preflight; new reports it |
| money_scan (8200b0f9) | alembic_guard | - | PASS | old stopped at preflight; new reports it |
| money_scan (8200b0f9) | domain_tests | - | PASS | old stopped at preflight; new reports it |
| money_scan (8200b0f9) | ci_checks | - | PASS | old stopped at preflight; new reports it |
| money_scan (8200b0f9) | app_tests | - | FAIL | stopped (killed with the red preflight; ends within 1 s of it); old stopped at preflight |
| money_scan (8200b0f9) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| domain_fail (b4454c28) | preflight | PASS | PASS |  |
| domain_fail (b4454c28) | ci_checks | PASS | PASS |  |
| domain_fail (b4454c28) | domain_tests | FAIL | FAIL |  |
| domain_fail (b4454c28) | app_tests | PASS | PASS |  |
| domain_fail (b4454c28) | ruff_ratchet | PASS | PASS |  |
| domain_fail (b4454c28) | coverage | PASS | PASS |  |
| domain_fail (b4454c28) | alembic_guard | PASS | PASS |  |
| domain_fail (b4454c28) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| app_fail (3ee9ff2a) | preflight | PASS | PASS |  |
| app_fail (3ee9ff2a) | ci_checks | PASS | PASS |  |
| app_fail (3ee9ff2a) | domain_tests | PASS | PASS |  |
| app_fail (3ee9ff2a) | app_tests | PASS | PASS | SEED-INVALID: old gate PASSES it (shared gap, see below) |
| app_fail (3ee9ff2a) | ruff_ratchet | PASS | PASS |  |
| app_fail (3ee9ff2a) | coverage | PASS | PASS |  |
| app_fail (3ee9ff2a) | alembic_guard | PASS | PASS |  |
| app_fail (3ee9ff2a) | TOTAL | PASS marker=yes | PASS marker=yes | SEED-INVALID: old gate PASSES it (shared gap, see below) |
| vitest_fail (2197eda5) | frontend_build | PASS | PASS |  |
| vitest_fail (2197eda5) | preflight | PASS | PASS |  |
| vitest_fail (2197eda5) | ci_checks | PASS | PASS |  |
| vitest_fail (2197eda5) | domain_tests | PASS | PASS |  |
| vitest_fail (2197eda5) | app_tests | PASS | PASS |  |
| vitest_fail (2197eda5) | ruff_ratchet | PASS | PASS |  |
| vitest_fail (2197eda5) | coverage | PASS | PASS |  |
| vitest_fail (2197eda5) | alembic_guard | PASS | PASS |  |
| vitest_fail (2197eda5) | frontend_lint | PASS | PASS |  |
| vitest_fail (2197eda5) | frontend_unit | FAIL | FAIL |  |
| vitest_fail (2197eda5) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| lint_fail (51538468) | frontend_build | PASS | PASS |  |
| lint_fail (51538468) | preflight | PASS | PASS |  |
| lint_fail (51538468) | ci_checks | PASS | PASS |  |
| lint_fail (51538468) | domain_tests | FAIL | FAIL |  |
| lint_fail (51538468) | app_tests | PASS | PASS |  |
| lint_fail (51538468) | ruff_ratchet | PASS | PASS |  |
| lint_fail (51538468) | coverage | PASS | PASS |  |
| lint_fail (51538468) | alembic_guard | PASS | PASS |  |
| lint_fail (51538468) | frontend_lint | FAIL | FAIL |  |
| lint_fail (51538468) | frontend_unit | PASS | PASS |  |
| lint_fail (51538468) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| alembic_heads (4903d9c3) | preflight | FAIL | FAIL |  |
| alembic_heads (4903d9c3) | ruff_ratchet | - | PASS | old stopped at preflight; new reports it |
| alembic_heads (4903d9c3) | coverage | - | PASS | old stopped at preflight; new reports it |
| alembic_heads (4903d9c3) | alembic_guard | - | FAIL | old stopped at preflight; new reports it |
| alembic_heads (4903d9c3) | ci_checks | - | PASS | old stopped at preflight; new reports it |
| alembic_heads (4903d9c3) | app_tests | - | FAIL | old stopped at preflight; new reports it |
| alembic_heads (4903d9c3) | domain_tests | - | FAIL | stopped (killed with the red preflight; ends within 1 s of it); old stopped at preflight |
| alembic_heads (4903d9c3) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| docs_clean (d03a3f55) | preflight | PASS | PASS |  |
| docs_clean (d03a3f55) | ci_checks | PASS | PASS |  |
| docs_clean (d03a3f55) | domain_tests | PASS | PASS |  |
| docs_clean (d03a3f55) | app_tests | PASS | PASS |  |
| docs_clean (d03a3f55) | ruff_ratchet | PASS | PASS |  |
| docs_clean (d03a3f55) | coverage | PASS | PASS |  |
| docs_clean (d03a3f55) | alembic_guard | PASS | PASS |  |
| docs_clean (d03a3f55) | TOTAL | PASS marker=yes | PASS marker=yes |  |
| docs_spec_break (d69967d0) | preflight | FAIL | FAIL |  |
| docs_spec_break (d69967d0) | ruff_ratchet | - | PASS | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | coverage | - | PASS | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | alembic_guard | - | PASS | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | domain_tests | - | PASS | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | app_tests | - | PASS | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | ci_checks | - | FAIL | old stopped at preflight; new reports it |
| docs_spec_break (d69967d0) | TOTAL | FAIL marker=no | FAIL marker=no |  |
| frontend_clean (1034304b) | frontend_build | PASS | PASS |  |
| frontend_clean (1034304b) | preflight | PASS | PASS |  |
| frontend_clean (1034304b) | ci_checks | PASS | PASS |  |
| frontend_clean (1034304b) | domain_tests | PASS | PASS |  |
| frontend_clean (1034304b) | app_tests | PASS | PASS |  |
| frontend_clean (1034304b) | ruff_ratchet | PASS | PASS |  |
| frontend_clean (1034304b) | coverage | PASS | PASS |  |
| frontend_clean (1034304b) | alembic_guard | PASS | PASS |  |
| frontend_clean (1034304b) | frontend_lint | PASS | PASS |  |
| frontend_clean (1034304b) | frontend_unit | PASS | PASS |  |
| frontend_clean (1034304b) | TOTAL | PASS marker=yes | PASS marker=yes |  |

**Verdict.** 12/12 seeds give the same TOTAL and the same marker decision in old and new; 0 step mismatches (a step that
ran in both gates never differs). Every difference in the table is a "new-only" row, i.e. the new gate reports the
other red/green steps the old gate never reached because it stopped at a red preflight. `app_fail` is a shared gap:
both gates PASS it and write a marker over a failing `tests_app` test (see "To file"), so the harness prints SEED-INVALID
twice and the line "NOT EQUIVALENT (2 problem(s))".

## Timings before and after

TOTAL lines, read from the raw outputs (`old-gate-on-b323efd.txt`, `new-gate-on-b323efd.txt`, `equiv2/old-*.txt`,
`equiv2/new-*.txt`). 4 cores, one gate at a time.

| run | old | new | gain |
|---|---|---|---|
| branch head `b323efd3` (418-file diff vs main) | 1784.1 s | 713.1 s (steps sum 2099.5 s, jobs 4) | 2.5x |
| clean_code (small code commit) | 593.9 s | 469.7 s (steps sum 605.7 s) | 1.26x |
| frontend_clean (frontend-only) | 1154.8 s | 538.6 s (steps sum 1341.9 s) | 2.1x |
| docs_clean (docs-only) | 609.2 s | 445.9 s (steps sum 638.1 s) | 1.37x |

Two figures in the lane brief differed by 0.1 to 0.2 s from the raw TOTAL lines (frontend_clean old 1155.0 / new 538.7;
docs_clean old 609.4); the table uses the raw lines.

Seconds to the first red line (old = the preflight FAIL line, the first output the old gate gave; new = the first FAIL line's own time):

| seed | old (preflight FAIL) | new (first FAIL line) |
|---|---|---|
| ruff | 429.2 s | ruff_ratchet 0.5 s |
| coverage | 435.0 s | coverage 1.2 s |
| alembic_heads | 472.5 s | alembic_guard 0.1 s |

The new gate's TOTAL for these red runs is still about 440 s (the preflight is the long pole and its own failure is what ends
the run), but the person sees the cause in the first seconds and can stop.

## What stays serial and why

- The cheap checks (ruff ratchet, coverage, alembic guard) and frontend_lint: seconds each; running them first is the
  point, so they gain nothing from parallelism.
- The frontend_build prefix (5.2 s on the head run): the build must precede every reader of `frontend/dist` (the
  preflight and the domain tests' bundle scan), so it runs before the parallel block.
- Reference mode `--jobs 1` / `PREPUSH_JOBS=1` is the plain serial loop. Honest limit: `--jobs 1` was proven by unit tests,
  not by a real gate run in this lane; every real run above used jobs 4.

## Why the docs-only lane saves little

The selectors already narrow a docs-only change: domain tests narrow to the records tests, the code app selection is
empty, and there is no frontend step. So there is almost nothing to skip. The real cost on a long branch is the branch's
code diff against main (the head run is a 418-file diff, the docs_clean seed a 1-file diff). A "since the last proven
sha" variant (run only what changed after the last marker) was considered and rejected: docs-reading tests that were
picked because of code changes would not re-run when only a doc they read changed, which is the failure the lane must not
create. The review (MINOR 2) also showed that skipping ruff_ratchet and alembic_guard could write a marker the old gate
refused, so the lane now skips nothing.

## Plan for item 4 (no code written; groundwork was static, nothing run)

Goal: run the long stages' own test files in parallel inside a stage (pytest-xdist), to move below the 713 s.

- **Suites:** app_tests (693.3 s on the head run, the critical path), domain_tests (524.6 s), then ci_checks (127.5 s) if its
  pytest part qualifies. vitest already runs files in parallel (`frontend/vite.config.js:41-49`, `testTimeout` 15000 raised
  after a load flake).
- **Floor:** steps sum 2099.5 s / 4 cores = about 525 s versus 713 s now. The gain is bounded by that floor on 4 cores
  (larger on more cores). pytest-xdist is NOT installed.
- **Must measure before any change:**
  1. Collision candidates: `tests_app/test_execute_replay.py:209-210` sets `os.environ` `EXECUTE_REPLAY=1` / `APP_ENV=production`
     at import without monkeypatch (a process-wide leak, order-dependent under xdist).
  2. 16 test files run git: check `cwd=` the real repo versus a tmp dir.
  3. Session fixtures at `tests_app/conftest.py:309` and `tests/scenario/scenario_fixtures.py:89` would rebuild per worker:
     measure the cost times the worker count.
  4. 87 `repo_scan` files re-parse the tree per worker.
  5. `tests_app` per-file DB clone uses the pid in the name (CI-safe), confirm under workers.
  6. No serial markers exist; the files that need one must be found by running, not by reading.
- **Steps, in order:** (1) in a scratch clone, `pip install pytest-xdist` there only; (2) run app_tests with `-n 2` then `-n 4`
  and compare pass lists with the serial run, file by file; (3) run it three times to catch order dependence; (4) fix or
  mark the leaks found (start with `test_execute_replay.py`); (5) repeat for domain_tests; (6) only then wire `-n` into the gate
  behind `--jobs`, keep `--jobs 1` serial; (7) rerun the 12-seed harness for equivalence.
- **Do not install until measured:** the measurement in step 2 decides whether the gain over the 525 s floor justifies
  the added flake risk; a failing `-n 4` run that passes serially stops the item.

## Adopting the new gate

1. Merge `chore/gate-speed-1126`.
2. Run `python scripts/orchestrator/prepush.py` (default jobs = CPU count).
3. Force the reference serial mode with `--jobs 1` or `PREPUSH_JOBS=1`.
4. In a cloud container, prefix the proxy-unsetting line (below).
5. The marker body now carries `mode` (jobs and lane); a marker written by the old gate has none.

Cloud containers need the proxy variables unset for the check (owner approval 26 Nov; the gate prints a NOTICE when
they are set):

```
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy python scripts/orchestrator/prepush.py
```

The equivalence runs also unset `TEST_DATABASE_URL`, `TEST_ADMIN_DATABASE_URL`, `ALEMBIC_DATABASE_URL` and
`OFO_REQUIRE_DB_TESTS`, because the host serves prod.

## To file as deferred issues (not filed here; the no-filing rule applies)

Spec basis for all: ADR-189 and runbook "Before a push" (the gate is the delivery proof); none of these changes what the
product does.

- **(a) origin/main red at the preflight interface.** Evidence: `tests_app/test_stored_chain_real.py:144` "Too many
  positional arguments for ChainCatalogue / FuturesCatalogue" (2 mypy call-arg mismatches) on `d387d4cd`. Done when: main
  passes the preflight interface layer.
- **(b) The gate never runs a changed `tests_app` test file.** Evidence: the `app_fail` seed got a marker over a failing
  `tests_app` test in BOTH gates (`select_app_tests` diffs only `backend/`). Done when: a change to a `tests_app` file
  selects that file and the `app_fail` seed goes red in the harness. **Fixed in the commit that adds `tests_app_selection` to `select_app_tests.py`**: the CLI diff now covers `tests_app/`; evidence: `tests/orchestrator/test_select_app_tests.py::test_the_cli_selects_a_failing_test_appended_to_a_tests_app_file_when_backend_is_unchanged` (throwaway git repo mirroring the seed prints the file). Review round 2: a changed or deleted `tests_app` module (test files included) also selects every test importing it, transitively; conftest/`__init__` select their subtree; renames are delete + add; quoted path names exit 3; computed imports are not followed. The harness re-run of the seed is not done here.
  Gate proof (lane G, 26 Nov): the same failing test appended to `tests_app/test_abs_delta_intrinsic.py` on top of
  the fix (commit ed36019d, scratch clone with origin/main = that commit), run through the new gate: `FAIL app_tests
  1.6s` (`FAILED tests_app/test_abs_delta_intrinsic.py::test_equiv_seed_fail`, `1 failed, 7 passed`), `TOTAL FAIL
  431.5s ... marker not written`. The same seed on b323efd3 (before the fix): `app_tests 0.1s PASS`, marker written,
  in both gates. Selector tests against the pre-fix select_app_tests.py: `12 failed, 30 passed`; after: `42 passed`.
  Tier A review round 1 found one MAJOR (a changed test module did not select the test files importing it: 151
  tests_app files import another test module) and three MINORs; all fixed in review round 2 (2a04ee4d: importers to a
  fixed point, quoted names fail closed, `--no-renames`, `__init__.py` selects its subtree). Round 2 was not
  re-reviewed (two-round limit).
- **(c) `alembic_migration_guard` does not detect a second head.** Evidence: the `alembic_heads` seed went red only
  through its empty `upgrade()`. Done when: a second head alone turns the guard red.
- **(d) A change to `docs/api/openapi.json` runs no frontend step** although `frontend/vite.config.js` references it
  (review NIT, both gates). Done when: that change runs the frontend lint, build and unit steps.
- **(e) The Windows kill path is proven only by mocks.** Evidence: review note; no run on a real Windows host. Done when:
  one real Windows run shows Ctrl-C and a red preflight kill the process tree.
- Already filed before the no-filing rule: #754 (proxy turns the attack2 EgressRefused test into "HTTP Error 400"), #755
  (a builder worktree under `.claude/worktrees` doubles ruff counts). Both still need stage rows.

## Known limits

- The Windows branch of the kill path is mocked only (e).
- `--jobs 1` is unit-tested, not run for real in this lane.
- The 4-core container is the only host measured; gains differ on other CPU counts.
- Harness runs were serial, one gate at a time; running two gates at once on one host would slow both.
- The report line of a stopped step reads `FAIL <step> <s>s`; only its log says `stopped: preflight failed`.
- The docs lane's gain is small by design.

## Documentation-only path on by default: proof (28 Nov 2026)

Owner decision 28 Nov 2026, 09:55 IST: "turn on the faster path for documentation-only pushes" (documentation only; the
"changed since last pass" mode for code stays off until after Monday 30 Nov). Commit `196536ed` made the docs-since-pass
lane the default and narrowed its list to markdown inside a records folder. Measured the same day on a 2-job run of the
full gate for that commit (it changes code, so it ran in full): `TOTAL PASS 1376.5s (steps sum 2159.6s, jobs 2)`, marker
written, push accepted. This paragraph is the next commit and changes this one documentation file only, so its gate run
is the proof of the short path (the lane line, the stages run and the wall time are in the lane's report).
