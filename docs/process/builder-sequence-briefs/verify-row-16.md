# Verifier brief: builder sequence row 16 (REQ-038 versions after execution on the app path / W-144), full check

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked file
in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\verify-16`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, current head
(row 16 merged, plus CI fix 3). Spec: `spec/requirements/REQ-038.md` AC-1..AC-5 and the decisions it cites (ADR-016..ADR-019,
ADR-062, ADR-064, ADR-069, ADR-075, ADR-085). Build brief (what was asked, and its attack list 1-6):
`docs/process/builder-sequence-briefs/row-16-REQ-038-versions-app-path.md`. Row 16 commits: `git log --oneline -40` on
the chunk branch, grep "row 16" / "REQ-038" / "strategy_versions".
Code: migration 0022 (`backend/ofo_app/alembic/versions/`), `backend/ofo_app/strategy_store.py`,
`backend/ofo_app/routes/strategies.py`, `backend/ofo_app/execution_return.py` (or where the return path lives),
`backend/ofo/strategy/versions.py`, `backend/ofo/errors/templates.py`, `tests_app/test_strategy_versions_app.py`.

Attack first (hands-on):
1. The "has a fill" check fails closed: an unreadable store or an open plan is never treated as "not executed".
2. After a fill, an edit makes version 2 proposed; version 1 stays active, its stored definition byte-identical.
3. A proposed version never becomes active on confirm alone, nor on an unreconciled return; only confirm AND a
   reconciled return. A return for a DIFFERENT version/plan does not activate this one.
4. The broker's actual state wins (AC-4): the recorded actual equals the broker position; version not active.
5. Restore of a pre-execution entry after a fill is refused with the template; nothing written (check every table).
6. Migration: up and down are real (not empty; `python scripts/alembic_migration_guard.py`), grants for `ofo_app`
   (ADR-048), and the down drops what up made. Concurrency: two edits racing after a fill cannot both make "version 2"
   (look for a unique constraint or lock; name it, or report its absence as a finding with severity).
7. Known limit from the handover: the Execute route will not build an adjustment plan while units are held, so a
   proposed version cannot reach `active` in the live app yet. Confirm or refute this with file:line, and say which
   AC it leaves unproven end to end.
8. Mutation: run `python scripts/orchestrator/mutation_gate.py` with the ready mutants file
   `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\row16\mutants.json`
   (read the gate's `--help` first). These mutants' tests are DB tests: if the gate needs a DB, do not run it; instead
   report per mutant whether the named test asserts the mutated line (read the test), and mark "DB part: CI #525".
   Add at least two mutants of your own for guards you find that the file misses.

Database: run NO database test locally. CI on draft PR #525 runs every DB test; the orchestrator reads it. List every
DB-backed test your ACs depend on as "DB part: CI #525". Do NOT call Kite live.

Reference: screen 119 - copy nothing; RD-114 is a SPEC CHANGE record waiting for Q282 and is NOT judged here.

Why Opus: Tier A - a migration, and the version state decides which definition the order path executes (ADR-019);
the reconciliation path (broker state wins) is in the safety set.
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per AC: `{"row": 16, "req": "REQ-038", "ac": "AC-n", "result": "pass" | "fail" |
"partial", "commands": "...", "observed": "... file:line", "attack": "..."}`. Then, in under 300 words: each
fail/partial with severity (CRITICAL/MAJOR/MINOR), the smallest fix and the files it touches; and anything not checked.
Tests (DB-free only): python -m pytest -q -p no:cacheprovider tests/strategy tests/reconciliation; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_openapi_drift.py
Budget: 35 min wall-clock, 32 tool calls (the verifier's turn limit is 40; batch commands)
Report: evidence-table
