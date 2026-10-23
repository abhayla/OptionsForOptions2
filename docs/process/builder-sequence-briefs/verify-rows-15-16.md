# Verifier brief: builder sequence rows 15-16 (REQ-028 shape templates / W-143, REQ-038 strategy definition, save and
# versions / W-144), start check, one shared verifier

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked file
in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\verify-15-16`.

Goal contract step 3: rows whose starting state is "built" or "verified" are NOT bypassed. Re-check every acceptance
criterion on today's code, and treat old evidence as a lead, never as proof on its own. Rows 1-14 changed shared code
after these rows were built (row 8 moved snapshot timing, row 9 moved the feed, row 13-14 touched the engine).
Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, current head.
Specs: `spec/requirements/REQ-028.md` (AC-1..AC-5), `spec/requirements/REQ-038.md` (AC-1..AC-5), and the decisions each
cites (ADR-006, ADR-083; ADR-019, ADR-062, ADR-064, ADR-069, ADR-075, ADR-085). Earlier work items, as leads:
W-005, W-012, W-033, W-061, W-071, W-109, W-119 (grep `evidence/` for them).
Code: `backend/ofo/strategy/` (catalogue.yaml, template.schema.json, matching.py, model.py, definition.py,
live_state.py, versions.py, modification.py, stored_form.py, loader.py, builder_history.py),
`backend/ofo/reconciliation/`, and the app's strategy store and routes under `backend/ofo_app/`.

Attack first:
1. REQ-028 AC-3/AC-5: add a NEW named template to a scratch copy of the catalogue (data only). It must be matched with
   no engine code change. Grep for any per-strategy branch in code (`if name ==`, the class names of named strategies).
2. REQ-028 AC-1/AC-4: a 5-leg strategy with two expiries and all six leg types is represented; a shape matching no
   template is a valid Custom Strategy.
3. REQ-038 AC-1: no live field (LTP, bid/ask, IV, Greeks, P&L, margin, timestamps of quotes) is a field of the
   definition object or its stored form. Diff the field sets.
4. REQ-038 AC-5: save a draft with a planned entry price and its capture time per leg, reload it, and compare it
   field-for-field, Decimal exact. A pre-ADR-075 draft (no planned entry) reopens with the ADR-085 message and a
   Reprice button, and nothing is captured until it is pressed.
5. REQ-038 AC-2/AC-3/AC-4: before the first execution, a change is an activity-history entry with restore, not a
   version. After it, every meaningful change is a new version, and old versions are kept. A proposed version is not
   active until confirmed AND reconciled. When the broker's actual fill differs, the broker state wins (find the code
   path and the test that proves it).
6. Delete each guard you find in a scratch copy, and name the killing test, via
   `python scripts/orchestrator/mutation_gate.py`. Results go to your scratch folder.

Database: run NO database test locally. CI on draft PR #525 runs every DB test, and the orchestrator reads it. List
every DB-backed test file your ACs depend on as "DB part: CI #525". Do NOT call Kite live. Known failing, not these rows:
`tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`.

Reference: screens 010, 011, 119 - copy nothing in this check: open difference records RD-090, RD-095, RD-096 (REQ-028) and RD-114 (REQ-038) are NOT judged here; the chunk-1 reference-copy builder builds them (ADR-178 (2)). Judge only the acceptance criteria.

Why Opus: Tier A - REQ-038 AC-3/AC-4 run through `backend/ofo/reconciliation/` (the broker's actual state wins), which
is an order file in the safety set, and the saved planned entry price feeds every P&L number.
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per row per AC: `{"row": 15|16, "req": "REQ-028"|"REQ-038", "ac": "AC-n", "result":
"pass" | "fail" | "partial", "commands": "...", "observed": "... file:line", "attack": "..."}`. Then, in under 300
words: each fail/partial with its severity, the smallest fix and the files it touches; and anything not checked.
Tests: python -m pytest -q -p no:cacheprovider tests/strategy tests/reconciliation; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 35 min wall-clock, 32 tool calls (the verifier's turn limit is 40; batch commands)
Report: evidence-table
