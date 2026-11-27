STATUS 21:05 | part 1: done | part 2: item 1 built, gate run before push | next push ~21:30 | blocker: none

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

## Tasks, models, minutes

| task | model | minutes |
|---|---|---|
| read, set up, 2 measured runs, recipe | Sonnet (main) | in progress |
| review of the last fix and equivalence claim | Opus (Tier A, `reviewer`) | 14 |
| item 1: tools check, cloud services, db_run cloud mode | Sonnet (main) | about 55 |

## To file (not filed)

- Pure rename no longer refused (MINOR-2), data-file match too loose (MINOR-1), SIGTERM leaves children (MINOR-3).
- Fresh cloud container has no `ruff`, `fastapi`, `sqlalchemy`, `frontend/node_modules`: four lanes lost a full gate run to it.
