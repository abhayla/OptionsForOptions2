# Row 16 build: REQ-038 (W-144) - versions after execution on the real app path

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report).
Size: M, about 9 files, 4 items
CI: app tests job `api` (your new `tests_app/test_strategy_versions_app.py` plus `tests_app/test_strategy_store.py`, `tests_app/test_strategy_followups.py`; vars: DATABASE_URL via CI); kit tests job (`tests/strategy/`; vars: none).
Expected (orchestrator, before dispatch): 60 min / ~400k.

Core: once a strategy has an execution plan with any fill, an edit through `PUT /strategies/{id}` creates a NEW
proposed version and keeps every earlier version. The active version changes only after the user confirms AND the
execution return is reconciled.
Proof: step 1 is a failing DB test on the REAL route and store, `tests_app/test_strategy_versions_app.py`:
1. Save a draft and edit it twice: two history entries, no version (AC-2, before execution).
2. Mark one plan filled through the existing execution-return path, then edit: today the edit is a plain history
   entry (start-check finding, `routes/strategies.py:353` -> `strategy_store.update` at `strategy_store.py:221`, no
   execution check). After the fix, the edit is version 2 `proposed`, and version 1 stays `active` and readable.

Spec basis: REQ-038 AC-2: "From the first execution on, every meaningful modification creates a new version".
REQ-038 AC-3: "A proposed version is separate from the active version".
REQ-038 AC-4: "the broker's actual state wins".
ADR-019 (versions after execution). ADR-016 to ADR-018
(Zerodha is the authority; no automatic retry; an unresolved mismatch blocks execution).
Copy from: none - the version rules already exist in this project's domain (`backend/ofo/strategy/versions.py`,
StrategyRecord.propose_execution / confirm / apply_result); this row wires them, it does not rewrite them.
Reference: screens 119 - copy nothing: RD-114 (what a save stores) is a SPEC CHANGE record waiting for the owner (Q282) and is not built here.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-row-16`, branch `build/seq-row-16`, made by the orchestrator from
the chunk head. Commit with `git commit -F <msg> -- <your paths>`, and do NOT push. Put the migration in its own
commit. BINDING: never stop a process by name; stop only PIDs you started. Database: ONE local run only, of your new
file plus the two store files, through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-row-16 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`.
CI runs the rest. If a write is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, then keep editing
and report the pending commit. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\row16`.

## What to do
1. Migration (next number after 0021, its own commit; the store runs as the limited `ofo_app` role per ADR-048, so
   grant it): a `strategy_versions` table (strategy id, number, state `proposed|active|superseded`, the saved
   definition, created_at, confirmed_at, reconciled_at). Widen the `strategies.status` CHECK only if the store needs
   it, and say why.
2. Store and route: `update` and `restore` look up whether any execution plan of the strategy has a fill (use the
   existing execution or plan store read; never a second copy of the rule). Without a fill, they behave as today.
   With a fill, `update` writes a proposed version through the domain `StrategyRecord.propose_execution`, and
   `restore` of a pre-execution history entry is refused with an explanation template (one home:
   `backend/ofo/errors/templates.py`).
3. Execution return: when a plan built from a proposed version returns reconciled (`execution_return.py`), call the
   domain `confirm` / `apply_result`, and only then mark the version active. If the broker's state differs, the
   recorded actual is the broker's (AC-4) and the version is not active until reconciled.
4. Read: `GET /strategies/{id}` returns the active version's definition plus the list of versions (number, state,
   times). Do not change the existing response fields; add a new field.

Attack list: (each names its test file)
1. No fill: edits and restore unchanged, no version row written (`tests_app/test_strategy_versions_app.py`).
2. After a fill: an edit makes version 2 proposed; version 1 is still active and its definition is unchanged byte for byte (same file).
3. A proposed version never becomes active on confirm alone; it becomes active only after a reconciled return (same file).
4. Broker state differs from the proposed version: the recorded actual equals the broker's position, and the version stays not active (same file).
5. Restore of a pre-execution history entry after a fill is refused with the template text; nothing is written (same file).
6. The migration runs up and down on a fresh database, and the `ofo_app` role can read and write the table (`tests_app/test_strategy_versions_app.py` or the existing migration test).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the "has a fill" check fails closed: an
unreadable plan store or an unknown fill state counts as executed (versioned, never a silent overwrite); (d) the
execution return's answer states (complete and matching, complete and different, partial, rejected, unknown or
failed read) each say whether the proposed version becomes active (only on complete and reconciled).
Threat model: in scope - an edit after execution silently overwriting what was executed, a proposed version shown as
active, a broker mismatch hidden; out of scope - the order path itself and any order placement (never send an order;
tests use the existing fakes only).
Findings checked: verified-on-a-module-the-product-does-not-call, dependent-tests-not-run-stale-later, guard-as-forbidden-list
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on the has-a-fill check, the proposed-to-active
transition and the restore refusal before reporting; quote its results file.
Reviewer checklist: every attack on the REAL route + store + migration; the domain rules reused, not copied; the
fill check fails closed; migration grants for ofo_app; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Why Opus: Tier A - the change adds a migration under `backend/ofo_app/alembic/` (safety set), touches the execution
return path, and designs how a version's life crosses the store and the return. That is a multi-file design, not a
fill-in.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
