# Brief: GC-MU A4 - ADR-230 (4): two stops with no combining rule mean "whichever comes first"

Core: a playbook holding both stop values and no `stop_line_rule` shows both values in the plan sheet and the summary.
Proof: step 1 of this brief - a test on a playbook body with `stop_line_pct_of_max_loss` and `stop_line_pct_of_margin` and no rule: the server plan words and the browser plan line both carry both values (red before, green after).
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: playbook bodies with both stop values and no rule - before: plan words show only the loss stop; after: both, in the server (`_words`) and the browser (`planLine`) alike.
Round: 1/2
Spec quote: ADR-230 "the plan sheet and summary show both values"
Sensibull: n/a - the reference product has no playbook stop lines (searched the study for stop line).
Reference: none - searched stop line, whichever comes first; open records: RD-096 (shape detection, not touched)
Copy from: none - no legacy-reuse map row for playbook plan words.
Tier: B.

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-stops`, branch `build/gcmu-stops` (from `build/gcmu`). Commit there only. Never push. `frontend/node_modules` is a junction to the run tree: never delete it, never run `npm ci`/`npm install`.

## The decision (spec/decisions/ADR-230.md decision (4))
Two stops with no combining rule mean whichever comes first; plan sheet and summary show both; trigger behaviour unchanged (each stop already fires on its own).

## Do, in order
1. Failing tests first: server `backend/ofo_app/routes/adjustment_plan.py` `_words` (~line 169) and browser `frontend/src/lib/playbookEditor.js` `planLine` (~line 103). Both values + rule absent -> the either-words. Keep: both + rule equal to the either text -> either-words; only one value -> that value's words; both + a DIFFERENT non-empty rule -> unchanged behaviour (state it in the test name); neither -> no stop words.
2. The summary uses the same browser `planLine` (labels `playbook_summary_stop_either` / `stop_either`, `tests_app/test_playbook_labels_route.py:49`); confirm with a test that the summary shows both. Change the condition in both places (rule absent or empty, or the either text). The two files must agree: one shared expectation table drives the server test and the vitest test (a small JSON fixture both read is fine, under `tests/fixtures/`).
3. Trigger tests unchanged and green: find the stop trigger tests (`grep -rn stop_line tests tests_app`) and run them in full.
4. Run in full each changed test file; `npx vitest run <changed spec>`; `tests/strategy/test_templates.py`; `python scripts/ruff_ratchet.py`; guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`. Logs to a file, tail only.

## Standing items
- One test per answer state above; a skipped test counts as not run; every changed test file run in full.
- A shown-value change: grep every test tree (e2e included) for the old plan text with only the loss words.
- No new wording (reuse `plan_stop_words_either` / `stop_either`); if new text is unavoidable it goes through `backend/ofo/errors/templates.py` + pins and you REPORT it (shared file).
- No new duplicated literal; ruff/mypy baselines must not rise; no regenerated files.
- Commit after each step passes. End the report with the final commit sha on build/gcmu-stops.
