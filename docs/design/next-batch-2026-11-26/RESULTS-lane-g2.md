STATUS 22:08 | part 1: done | part 2: item 1 pushed; items 2 (resume, on) and 3 (docs-since-pass, opt-in) built, reviewed once, measured; items 4, 5 (build), 6 not built | final push 22:20 | blocker: none

# Lane G2: gate speed, part 1 (27 Nov 2026)

**ADOPT:** on a lane branch cut from `origin/integration/nb-1126` (or any branch that contains it):

```
git fetch origin chore/gate-speed-1127
git merge --no-edit origin/chore/gate-speed-1127      # fast-forward on an untouched lane branch; clean merge otherwise
env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy \
    -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL -u OFO_REQUIRE_DB_TESTS \
    python scripts/orchestrator/prepush.py            # jobs = CPU count; add --jobs 1 for the old serial order
```

`chore/gate-speed-1127` = `integration/nb-1126` + a merge of Lane G's `chore/gate-speed-1126` (the only conflict, the generated
`knowledge/findings/INDEX.md`, is already resolved by regenerating it with `tools/build_findings_index.py`). If a lane's own
branch also changed `INDEX.md` and the merge conflicts there: run `python tools/build_findings_index.py .`, `git add`, commit.
Fresh container: the gate needs `ruff==0.15.12`, `mypy`, `fastapi`, `sqlalchemy`, `frontend/node_modules`; install with
`pip install -r requirements-dev.txt -r requirements-app.txt` and `cd frontend && npm ci` BEFORE the first run (a missing ruff
fails the gate at 0.1 s, fail-closed, as designed).

What a lane sees: the seconds-long checks first (ruff ratchet, coverage, alembic guard, frontend lint/build) with a PASS/FAIL
line each, then preflight / ci_checks / domain / app / vitest side by side, one line per finished step, `TOTAL PASS|FAIL <s>`,
and the marker only on an all-green, clean-tree run. Red preflight kills the still-running steps. Fall back: `--jobs 1`
(serial reference order) or `git merge` back out; nothing else in the repo depends on the new gate.

## 1b. Measured on today's base (`origin/integration/nb-1126` = 206a9f06), one run each, same container, run one after the other

4 cores, 15 GB, proxy and DB variables unset as above. Logs: `/tmp/fast.log`, `/tmp/cur.log` (tails read).
"fast" = nb-1126 + gate-speed merge (0a3cb379), "current" = nb-1126 as it is.

| stage | current (s) | fast (s) | note |
|---|---|---|---|
| frontend_build | 4.2 | 4.1 | |
| ruff_ratchet | 0.6 | 0.6 | fast gate prints it first |
| coverage | 1.3 | 1.3 | |
| alembic_guard | 0.1 | 0.1 | |
| frontend_lint | 7.5 | 7.0 | |
| preflight | 565.7 | 615.4 | stage seconds grow when 4 stages share 4 cores |
| ci_checks | 130.0 | 133.8 | |
| frontend_unit (vitest) | 130.0 | 335.9 | slower under contention |
| domain_tests | 581.4 | 622.5 | |
| app_tests | 954.6 | 1076.6 | the long pole |
| **TOTAL** | **2375.4** | **1089.8** | 2.18x; sum of fast steps 2797 s over 4 cores |

Honest reading: Lane G claimed 2.5x on its own head; on today's base it is 2.18x (about 22 minutes saved per full push).
The floor is the longest single stage (app_tests, about 1000 s) unless that stage is split: that is part 2.

## 1a. Independent review (Opus reviewer, read-only, about 14 min, 45 tool calls)

Verdict **ADOPTABLE**, no MAJOR finding. Checked: new app-test selection was a superset of the old in 60 random diffs
(0 losses); every injected red (preflight red, runner raising, rc None, vitest timeout, ci_checks -9, selector rc 3, serial mode)
ended exit 1 with no marker; docs-only lane sent 12 of 14 odd shapes (symlink, typechange, exec bit, rename, `change_scope.py`,
`docs/test_x.md`, `spec/conftest.py`, submodule, golden file, empty) to the full lane; marker still keyed to the full sha with a
clean tree. Findings to carry (none blocks adoption):

- MINOR-2 (owner should accept explicitly): a 100%-similarity pure rename of a backend module used to make the old selector exit 3
  (refused); the new selector (`--no-renames`) treats it as delete + add and selects the importers, so the refused set is slightly
  smaller. Risk only if the old name is still imported on a chain reached at run time. Alternative: keep exit 3 when a deleted
  non-route module's blob reappears elsewhere.
- MINOR-1: a changed `tests_app` data file selects by substring match of its name; `check.json` matched `check.json()` in one
  test and missed the real reader `test_d36_adjustment_counts.py` (skips on hosts without a DB anyway). Class fix: also select tests
  that name the file's folder. Not a regression: the old gate selected nothing for any `tests_app` change.
- MINOR-3: SIGTERM/SIGHUP to the gate leaves the long-stage children running (only Ctrl-C kills the tree). No false pass; wastes CPU.
- NIT: binary or quoted path under `tests_app/` blocks the marker (stricter, fine); two gates on the same checkout share step temp
  dirs; `gate-speed-2026-11-26.md` summary still says neither gate runs a changed `tests_app` file (fixed since in 2a04ee4d).
  The last selector fix was proven by unit tests (50 passed), not by re-running the 12-seed harness.

## 1c. Recipe proof on a throwaway branch (`throwaway/g2-adopt` in a scratch worktree)

1. `git switch -c throwaway/g2-adopt origin/integration/nb-1126`, `git merge --no-edit chore/gate-speed-1127`: fast-forward, no conflict.
2. Broke one test on purpose: new `tests/test_money.py` with `def test_g2_deliberate_break(): assert len([]) == 1`, committed (d9b7b9bd).
3. Gate run: first lines `PASS ruff_ratchet 0.5s`, `PASS coverage 1.5s`, `PASS alembic_guard 0.1s`, `PASS frontend_lint 7.6s`; then
   `FAIL domain_tests 643.0s` (log shows `test_g2_deliberate_break`), then
   `TOTAL FAIL 1059.0s (steps sum 2686.7s, jobs 4) marker not written (failed: domain_tests)`, rc=1. No marker file for d9b7b9bd:
   the push hook refuses that commit. REFUSED, as the current gate would.
4. Fix: `git rm tests/test_money.py`, commit (cb9e5467; same tree as merge commit 0a3cb379, which passed in 1089.8 s above).
   The fix-run was started together with the gate run for this RESULTS commit, two gates at once on 4 cores: BOTH went red on
   `frontend_unit` (`Test timed out in 15000ms`, 666 s and 672 s; TOTAL FAIL 1535.7 s and 1530.2 s, no marker). My mistake (a
   known limit of the doc: one gate per host at a time), but also a finding: a load-sensitive 15 s vitest timeout turns a
   busy host into a red gate, and today a red gate restarts from zero. Part 2 item 1 (resume) removes the cost. The
   fix-pass proof on the throwaway is therefore the 1089.8 s PASS on the identical tree plus the next run; it is re-run alone later.

## Finding fixed in this branch: the gate's own test fails when the gate is started in the background

`tests/orchestrator/test_prepush.py::test_a_keyboard_interrupt_in_the_main_thread_stops_the_workers_and_writes_no_marker`
sends SIGINT to itself. A process started with `&` from a non-interactive shell inherits SIGINT as IGNORED and Python then
installs no handler, so the test fails ("DID NOT RAISE") depending on how the gate was launched. Seen in 2 of 5 real gate runs
(the throwaway break run failed it too, next to the planted failure, and the first RESULTS run failed on it alone: TOTAL FAIL
1035 s, no marker), 0 of 23 direct pytest runs from a normal shell. Reproduced: `(trap '' INT; pytest <test>)` = FAIL, normal
shell = pass. The runbook tells lanes to run prepush in the background, so this is a trap for every lane. Fix: the test installs
`signal.default_int_handler` for its duration and restores the old disposition (class fix: every test that sends itself a
signal; `grep -n "os.kill" tests` shows no other SIGINT sender). After the fix: `(trap '' INT; pytest <test>)` passes.

## Part 2, item 1: tools-present check, cloud services (coordinator's order, 27 Nov)

**Which call failed for the four lanes.** `scripts/ruff_ratchet.py:58` runs `sys.executable -m ruff`. The container has a ruff
BINARY (`/root/.local/bin/ruff` and `/usr/local/bin/ruff`, 0.16.9) but not the module in the gate's Python, so the ratchet
failed closed at 0.1 s with `No module named ruff`. A PATH problem is not the cause. Do not "fix" it by calling the binary:
the baseline `scripts/ruff_baseline.json` was counted with the pin `ruff==0.15.12` (requirements-dev.txt) and 0.16.9 counts
differently. The right fix is `python -m pip install -r requirements-dev.txt -r requirements-app.txt` (what the lanes did,
at the cost of a run), so the gate now says so in its first 0.1 s.

- `scripts/orchestrator/tools_present.py` (new), called first in `prepush.main` (after usage errors, before any step): names every
  missing tool with its exact install command, exit 2, nothing runs. Checks: `python -m ruff` present and equal to the pin,
  modules pytest, mypy, fastapi, sqlalchemy, git, and (only when a frontend step is planned, or `--full`) node/npm and
  `frontend/node_modules`. Cost 0.08 s. Proof: `/tmp/v0/bin/python scripts/orchestrator/tools_present.py --frontend` in an empty venv
  prints `TOOLS MISSING (5)` with the fix under each; 10 new tests in `tests/orchestrator/test_tools_present.py` (wrong version,
  missing module, node_modules only when planned, the gate stops with exit 2 before any step, goes on when all present).
- `scripts/orchestrator/cloud_services.sh [--reset]` (new, guarded by `CLAUDE_CODE_REMOTE=true`, otherwise a no-op exit 0): starts
  the installed PostgreSQL 16 (`service postgresql start`) and Redis 7, creates `ofo_test`, the `ofo_app` role with the ADR-048
  attributes (same statements as `app-tests.yml`), runs `alembic upgrade head` as the owner role. Throwaway local passwords
  (the CI values). Run-and-seen-working here: first run 80 s (alembic dominates), second run 51 s (idempotent), `--reset` drops
  `ofo_test*` and rebuilds.
- `scripts/orchestrator/db_run.py`: in a cloud session without the owner's `GLOBAL.env`, uses those local URLs (the owner's PC path is
  unchanged). Proof: `db_run.py . python -m pytest -c pytest-app.ini tests_app/test_audit_store.py`: 105 passed, 1 failed; the
  one failure is `test_ac5_0017_downgrade...` marked `full_chain`, which CI excludes (`-m "not full_chain"`, nightly only).
  Use `-m "not full_chain"` as CI does.
- Not done by this item (owner/coordinator): the gate runs with `TEST_DATABASE_URL` unset, so DB tests still skip inside the gate;
  turning them on would change what the gate runs and needs the owner.

**Proposed, NOT wired: SessionStart hook line for `.claude/project/hooks.json`** (the coordinator decides):

```json
"SessionStart": [ { "hooks": [ { "type": "command",
  "command": "[ \"$CLAUDE_CODE_REMOTE\" = true ] && bash \"$CLAUDE_PROJECT_DIR/scripts/orchestrator/cloud_services.sh\" || true" } ] } ]
```

It adds about a minute to a cloud session start; leave it off for lanes that never run DB tests (they use `db_run.py` only for
migration or store files).

### For the coordinator: environment setup script (each line seen working in this container, 27 Nov)

```
python -m pip install -r requirements-dev.txt -r requirements-app.txt   # ruff==0.15.12, mypy, pytest, fastapi, sqlalchemy (seen: ruff 0.15.12 in `python -m ruff --version`)
(cd frontend && npm ci --no-audit --no-fund)                              # seen: rc=0, node 22 at /opt/node22/bin
bash scripts/orchestrator/cloud_services.sh                               # seen: PostgreSQL 16 + Redis 7 up, ofo_test migrated, 80 s
```

Not run-and-seen: any `apt-get` line (nothing needed: PostgreSQL 16, Redis 7, node 22 are in the image).

## Part 2, items 2 and 3 (built, reviewed once by Opus, fixes applied; one of the two is OPT-IN)

**Item 2, resume (default ON).** `prepush.py` writes a pass record per long step (preflight, ci_checks, domain_tests, app_tests,
frontend_unit) under `.git/ofo-prepush/steps/`, only when the step returned 0, the tree was clean and HEAD had not moved. The key is
the sha256 of: the step, `HEAD^{tree}`, `--full`, the lane, `origin/main`, the merge base with it, the full-pass base, the frontend
change list, Python and Node versions, the digests of `prepush.py` and `merge_preflight.py`, the checkout path, `sys.prefix` and
the installed frontend packages. A failed, stopped or killed step has no record, so a re-run on the same tree starts at the
step that did not pass (`RESUME <step>: passed <time> ...` lines). Any file change changes the tree hash: nothing is reused across a
change. An amend that keeps the tree (message only) reuses the passes. `--no-resume` ignores the records.
Honest limit: the key is the whole tree, so a lane that fixes the failing test (a new tree) re-runs every step; resume pays
for killed runs, flaky reds, host-load reds (the 15 s vitest timeout) and message-only amends, not for a code fix. Per-step input sets
(for example vitest keyed to `frontend/` only) would widen it, but nobody has proved what each stage reads, so it is not built.
Tests: `tests/orchestrator/test_prepush_since_pass.py`, 32 passed (resume after a failed step restarts at that step; a new commit, a
moved `origin/main`, a dirty tree, a stopped step, a HEAD that moved during a step each get no reuse).

**Item 3, docs-since-pass lane (OPT-IN: `--since-pass` or `PREPUSH_SINCE_PASS=1`; default OFF until re-reviewed).** When every path
changed between this branch's last FULL-pass marker (or a docs-since-pass marker that names its full-pass `anchor`) and the start sha
is a records file (same strict rules as the existing docs-only lane: added/modified/deleted, plain mode, no rename, symlink,
submodule, `tools/change_scope.py`), on a committed tree, the gate runs: the cheap checks, ci_checks, preflight WITHOUT its two
Python-only layers (mypy interface, collect) but with the build check and every scan, the domain tests the kit selects against the
anchor plus every `tests/` file that reads a docs path (directly, or through a `scripts/` or `tools/` module that names one), the
`tests_app` docs readers, and the frontend steps exactly as the full lane plans them. Anything else, any doubt, no marker (fresh
container), `--full`, a classifier change: the full lane. The marker records `anchor`.
Opus review of items 2 and 3 together (about 12 min, 32 tool calls): first verdict REVISE. MAJOR F1: tests reading records files went
unselected (19 `frontend/tests` files read `spec/decisions/ADR-*.md`; `tests/test_reference_register_real.py` reads docs through
`scripts/orchestrator/reference_register.py`): fixed (frontend steps planned as in the full lane; modules under `scripts/` and `tools/`
count as readers). MINOR F2 (record saved when HEAD moved), F3 (merge base missing from the key), F4 (classifier vouching for itself
through an older anchor), F5 (gate files, checkout and packages missing from the key), F6 (lane on a dirty tree), F7 (temp-file race,
non-dict JSON): all fixed with a test each. NOT re-reviewed after the fixes, which is why the lane is opt-in.
Residual risk to read before enabling it by default: a test that reads a records file by a route the reader scan cannot see
(environment-variable path, computed glob, a repo-wide `rglob`) is not selected in this lane; the previous gate ran it when the
branch also had code changes. The repo_scan tests and every generated-view check still run in the lane, which covers the
repo-wide walkers it knows of.

### Measured (27 Nov, 4 cores, same container, one gate at a time; logs `/tmp/*.log`, tails read)

| stage | before: current gate (s) | after: fast gate, code push (s) | after: docs-since-pass (s) | how |
|---|---|---|---|---|
| ruff_ratchet, coverage, alembic_guard | 2 | 2 | 2 | unchanged, now first |
| frontend_lint + build | 12 | 11 | 11 | unchanged |
| preflight | 566 | 615 (4 stages share 4 cores) | 477 | since-pass skips interface 49 s + collect 28 s; scans kept |
| ci_checks | 130 | 134 | 124 | kept in full |
| domain_tests | 581 | 623 | 129 | kit records selection against the full-pass commit + docs readers |
| app_tests | 955 | 1077 | 66 | docs-reading `tests_app` files only |
| frontend_unit | 130 | 336 | 164 | planned as in the full lane (review F1) |
| **TOTAL** | **2375** | **1090** (1052 and 1138 on the next two commits) | **490** | stages side by side; docs lane as above |

| scenario | before (current gate) | after | what did it |
|---|---|---|---|
| (i) code push | 2375 s | 1052 to 1138 s | Lane G's parallel stages (adopted); resume adds nothing on a first run |
| (ii) docs-only or decision-row push, after a full pass on the branch | 2375 s (the gate diffs against `main`: 418 files) | 490 s with `--since-pass` (opt-in); 1052 s without | docs-since-pass lane; the floor is preflight's repo scans 477 s, not 2 minutes |
| (iii) re-run on the same tree after a failed or killed run | 2375 s | 12.4 s when the five long steps had passed (measured); only the failed step re-runs otherwise | resume. A code fix is a new tree and runs everything |

The coordinator's target for (ii), about 2 minutes, is NOT met: 490 s. What is left is preflight's three serial repo-scan runs
(`tests -m repo_scan` 230 s, `tests_app -m repo_scan` 175 s, guard files 117 s) plus frontend_unit 164 s. The scans read the
whole tree, so cutting them needs proof of which `repo_scan` tests read records files; running the three groups side by side
would bring preflight to about 230 s without removing anything (not built, time).

**Items not built (time), with what I measured:**
- Item 5, preflight (615 s on the 27 Nov base): interface 49 s + collect 28 s + scans 538 s. The scans are three serial pytest runs:
  `tests -m repo_scan` 1580 tests 230 s, `tests_app -m repo_scan` 484 tests 175 s, guard files 39 tests 117 s. On a big diff the
  domain stage runs all of `tests/` (10,419 tests) and the app stage most of `tests_app`, so the first two are run twice. Safe cut: pass
  `--no-domain-scans` when the domain selection is the whole `tests/` (nothing removed: the tests still run in domain_tests), and the
  same for `tests_app` when the app selection covers the repo_scan files; then run the remaining scan groups side by side. Estimate:
  about 400 s of CPU per code push; wall time moves only slightly because app_tests (about 1000 s) is the critical path.
- Real lever on a code push: split app_tests (pytest-xdist, not installed; Lane G's plan lists the collision candidates). Not started.
- Item 4 (select tests since the last full-pass marker, behind a switch, with a 12-seed miss-rate proof): not started.

## Rule for lanes (item 7), from my own 27 Nov runs

My lane ran 12 gate runs in about 5 hours: 4 were measurements the task asked for, 3 were wasted (two gates started at once on 4
cores both died on the 15 s vitest timeout, 1535 s and 1530 s; one died on the Ctrl-C test above, 1035 s), 5 were pushes. Rule:
1. One gate at a time per host. Never start a second one, a build or a full pytest while it runs.
2. Before the first gate of a round: `python scripts/orchestrator/tools_present.py`, then `python scripts/ruff_ratchet.py` and the
   test files you touched. Minutes, not 18.
3. One push per lane per build round; decision rows batched into one commit.
4. A red stage: read the failing lines, fix, and re-run the SAME stage by hand first; start the gate only when it is green.
   A killed or red run on an unchanged tree resumes at the failed stage (resume is on by default).

## Tasks, models, minutes

| task | model | minutes |
|---|---|---|
| read, set up, 2 measured runs, recipe | Sonnet (main) | in progress |
| review of the last fix and equivalence claim | Opus (Tier A, `reviewer`) | 14 |
| item 1: tools check, cloud services, db_run cloud mode | Sonnet (main) | about 55 |
| items 2 and 3: resume, docs-since-pass lane, review fixes, tests | Sonnet (main) | about 70 |
| review of items 2 and 3 | Opus (Tier A, `reviewer`) | 12 |
| gate runs (measurements, 5 pushes, 3 wasted) | machine | about 200 |

## To file (not filed)

- `scripts/orchestrator/gate_equivalence.py` never clears `.git/ofo-prepush/steps/` between its runs: with resume on, a second "new" run would resume the first run's passes (review F5); pass `--no-resume` there before the next equivalence run.
- Pure rename no longer refused (MINOR-2), data-file match too loose (MINOR-1), SIGTERM leaves children (MINOR-3).
- Fresh cloud container has no `ruff`, `fastapi`, `sqlalchemy`, `frontend/node_modules`: four lanes lost a full gate run to it.
