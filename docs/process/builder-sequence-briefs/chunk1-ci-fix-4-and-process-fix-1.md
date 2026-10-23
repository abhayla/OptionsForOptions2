# Chunk 1: CI fix 4 + process tools fix 1 (findings from the two findings-only checks, session 5db71e90)

Core: (A) the 18 database-drop guard tests in `tests/orchestrator/test_db_run_fresh.py` run in a CI job again; (B) transcript token totals count each assistant message once.
Proof: (A) the new app-tests.yml step names the file, and a new repo test fails when an importorskip file under tests/ is named in no app-tests.yml step (show it red with the step removed in a scratch copy, then green); (B) a test transcript with one message id on three lines counts its usage once, in both scripts.
Class: (A) test-skipped-in-its-only-ci-job (`knowledge/findings/test-skipped-in-its-only-ci-job.json`): files under tests/ with importorskip/skip-on-dependency that no CI job runs with the dependency installed - 1 before (test_db_run_fresh.py), 0 after. (B) transcript-usage-counted-per-line (`knowledge/findings/transcript-usage-counted-per-line.json`): scripts summing transcript usage per line - 2 before (row_actuals.py, measure_process.py), 0 after.
Budget: 30 min wall-clock, 50 tool calls
Report: evidence-table
Copy from: none - project tooling and CI wiring, no legacy module
Reference: none - tooling, no screen
Tier: B (CI step + orchestrator scripts; no product code)

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-ci-fix`, branch `build/seq-chunk1-cifix` (fast-forwarded to the chunk head by the orchestrator). Commit with `git commit -F <msgfile> -- <your paths>`; do NOT push. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The kit guard blocks shell commands naming `.github`, `spec`, `tools/`, `.claude`, `views`, `factory`: edit `.github/workflows/app-tests.yml` with the Edit tool, and for git use pathspec globs (e.g. `':(glob)**/app-tests.yml'`). If a write is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, then keep editing and report the pending commit.

## Items
A1. `.github/workflows/app-tests.yml`: in a job that runs after `pip install -r requirements-app.txt` (the job that already runs `tests/test_bundle_secret_scan.py`, around line 343), add `python -m pytest -q -p no:cacheprovider tests/orchestrator/test_db_run_fresh.py`. It needs no database URL if its tests are pure (read the file; if some need one, use the job's existing env the same way neighbouring steps do).
A2. Detection: new repo test `tests/test_dependency_skips_have_a_ci_home.py` (mark it `repo_scan` like its neighbours): find every file under `tests/` calling `pytest.importorskip(` (AST, not text grep, so a comment does not count), and assert each file path appears in `.github/workflows/app-tests.yml`. Fail closed: an unreadable workflow file is a failure, not a pass. Prove it red by pointing it at a copy of the workflow without the step (a tmp_path fixture), then green on the real file.
B1. `scripts/orchestrator/row_actuals.py` `transcript_tokens` (~:75-81): count usage once per `message.id` (keep the last line per id; a line with no id counts once). Test: a transcript with one id on three lines + one other id -> total = the two messages' usage.
B2. `scripts/orchestrator/measure_process.py` `read_session` (~:149-163): `turns` and `ctx` count once per `message.id` the same way (reuse one helper; do not copy the dedupe into both files - put it where both can import it, e.g. a small function in measure_process.py that row_actuals imports, or the other way round). Same three-line test for read_session's turns/ctx.
B3. `row_actuals.py` docstring: state that wall-clock keys on commit subjects starting `Row <n>` and that expected sums every row-<n> brief (build + fixes), so the two are not like for like until the commit convention covers build commits.
C1. `scripts/orchestrator/regen.py`: bare `--only` or a second `--only` exits with the usage message (rc 2), no traceback. Test.
C2. `scripts/hooks/agent_brief_gate.py` ~:49: when the brief path does not resolve, write ONE stderr line naming the ref (still allow - fail-open stays). Test asserts the line.
C3. `scripts/orchestrator/make_brief.py`: `tier` must be A, B or C (else exit 1 with the reason, nothing written); an OSError on `--out` exits 1 with the reason, no traceback. Tests.

## Rules
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise (`python scripts/ruff_ratchet.py`); targeted tests only - the files you touch plus `tests/orchestrator/` tests for these scripts and `python -m pytest -q -p no:cacheprovider -m repo_scan tests` once at the end; no regenerated files in the commit. Standing items: (a) n/a - no time-budgeted job; (b) the new CI step runs after the dependency install step - say which line; (c) the repo test fails closed on a workflow it cannot read and finds importorskip by AST; (d) n/a.

Threat model: in scope - a test file under tests/ that skips itself on a missing dependency and so runs in no CI job; a transcript token total that counts one message several times; a brief gate that silently passes an unresolvable brief path. Out of scope - a test skipped by a marker or a `-k` filter, a CI job that is disabled as a whole, and deliberate tampering with a transcript.
Tests: python -m pytest -q -p no:cacheprovider tests/orchestrator tests/test_dependency_skips_have_a_ci_home.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests

## Report (under 300 words)
Evidence table, one row per item A1-C3 (command + result line), plus the A2 red-then-green proof, ruff ratchet, and the commit sha(s).
