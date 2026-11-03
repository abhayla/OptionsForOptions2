# Brief: GC-IC1 step 1a (core) - REQ-159 AC-4 / REQ-170: a switched-on expiry-day rule raises one record at its time through the alert gate

Core: the iron condor playbook's expiry-day rule (`when: expiry`, `at: 14:30`, `action: 5`, `close_if_short_within_pct: 0.3`, `on: true`; `backend/ofo/adjustment/system_playbooks.json` playbooks[2]) raises a suggestion record at its time, through the same alert gate (REQ-170) as every trigger. Today it is inert: only `_tighten` (`backend/ofo_app/adjustment_check.py:137`) acts on any day rule.
Proof: step 1 of this brief - a new generator case (expiry-day iron condor, one short within 0.3% of spot), run through the REAL background Worker with a pinned clock on a fresh DB: at 14:29 no record; at 14:30 exactly one record for the expiry rule, naming A-28 for the tested spread and A-27 for any far short whose LTP is below Rs 2; a second case with the short 0.4% away gives zero records. Records COUNTED from the DB table, ids printed.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, check-clock-read-once-per-batch
Spec quote: REQ-159 AC-4 "Each carries a time and one action: carry check, show reduce or exit, show add-hedge, pause, tighten every"
Threat model: in scope - a day rule bypassing the alert gate (writing a record directly); the screen and the worker computing the day rule differently (one function for both, finding engine-input-chosen-per-caller); a rule firing before its time or on a non-expiry day; a rule re-opening every check after 14:30 (the gate's yes/no edge must hold it to ONE record per episode); a rule firing with no spot (must read None = not checked, never True). Out of scope - the carry check (action 0, step 1b), pricing A-27 (step 2 builds its builder; here the record only names it), the other day-rule kinds (away, event, dom, date).
Sensibull: n/a - server-side rule evaluation, no screen change in this step (the reference product shows no expiry-day auto rule in the study).
Reference: none - searched expiry day rule, day rules, close if short within
Copy from: none in `docs/process/legacy-reuse.md` for day rules (checked: no row for playbook day rules). Reuse the existing paths named below; write no parallel evaluator.
Tier: A (fresh Opus review follows; mutation tests required).
Size: M, about 8 files, 1 item
CI: the backend unit job runs `tests/` (pure evaluator, gate parity, generator case, template pins); the app job runs `tests_app/` under `pytest-app.ini` (worker proof); vars: TEST_DATABASE_URL (set by CI's postgres service; locally db_run_fresh sets it)

## Where
Create your branch inside your agent worktree: `git switch -c build/gcic1-s1a 37824fb9` (feature/adjustments head; NOT main). Commit there only, never push, never touch main. DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(throwaway DB migrated to head; the shared ofo_test is at 0030 and fails every 0031+ table; never `db_run.py`). One file at a time; `tests_app/test_background_worker.py` takes ~14 min whole, so run it with `-k <name>`. Long output to a log file, read only the tail.

## How the pieces connect today (read these first, do not re-survey)
- `backend/ofo/adjustment/playbook_eval.py`: `StrategyState` (line ~60; `tighten_percent`, `hhmm`, `days_left`, `shorts`, `spot`), `evaluate()` (~565) -> `Evaluation` (`results`, `clear`, `values: RuleValue`).
- `backend/ofo/adjustment/gate_readings.py`: the ONE function turning an Evaluation into `alert_gate.step` readings. A yes/no rule reads True/False with no ladder (ADR-237 (1): re-arms at a false close).
- `backend/ofo/adjustment/alert_gate.py`: pure gate; candle closes; edge not level; daily cap / quiet time -> Held.
- `backend/ofo_app/adjustment_check.py`: `state_of` builds the StrategyState for BOTH the screen and the worker; `_tighten` is the only day-rule reader.
- `backend/ofo_app/background.py:893` `_gate_step(w, now, preset, gate_readings.readings(ev))` writes records.
- Holiday / session days: `backend/ofo/market_calendar.py` (`market_status`, `NO_CALENDAR`). Not needed for the expiry rule; step 1b uses it.
- Scenario generator: `tests/adjust_scenarios_gen.py` (`build`, `day_type`, `is_session`, `hand_*` engine-free figures), cases in `tests/fixtures/adjust_scenarios/ADJ-*.json`. Add new cases through the generator, never by hand-editing JSON. Regenerate only the new case files.

## Do, in order
1. CORE (failing test first): a day rule becomes a rule the evaluator reports, with its own stable rule id (suggested `day:<when>:<index in day_rules>`). For `when: expiry` with `close_if_short_within_pct` P: on expiry day (`days_left == 0`) at or after `at`, the value is True when any short leg's strike is within P% of spot (|strike - spot| / spot * 100 <= P, exact Decimal), else False; before `at`, on a non-expiry day, or with no spot it gives NO reading (None, not checked; never False before the time, so no false clear is recorded either). It goes out as a yes/no `RuleValue` through `gate_readings.readings`, so the record is opened ONLY by `alert_gate.step`. The record names the rule's action (index 5, its words from `PLAYBOOK_DAY_RULE_ACTION_TEXT`) and the approaches: A-28 for the spread whose short is within P%, A-27 for any other short whose LTP < the playbook's Rs limit for A-27 (read it from the playbook body / approaches config; if there is no such limit in the body, STOP and report what you found, do not invent Rs 2). One function computes this; `state_of` (screen) and the worker both reach it.
2. Generator: two new iron condor cases on an expiry day: (a) a short within 0.3% of spot, plus a far short with LTP < Rs 2; (b) the same with the nearest short 0.4% away. Engine-free expected values in the case (`expected` block: rule fires yes/no, the approaches named).
3. Worker proof (the core proof above) in `tests_app/test_background_worker.py` (or a new `tests_app/test_day_rules_worker.py` if cleaner): pinned clock 14:29 -> 0 rows; 14:30 (after the candle close the preset needs) -> 1 row; later checks the same day -> still 1 row; case (b) -> 0 rows. Count rows with SQL against the records table.
4. Screen parity: the screen check (`evaluate_stored` / `state_of` path) gives the same yes/no for the same case and time (pure test, no DB).
5. Wording: any new user-visible text goes into `backend/ofo/errors/explanations.py` (catalogue) and is pinned in `tests/errors/template_pins.json` marked as pending owner read (same marker as the GC-ALERT1 pins); run `tests/strategy/test_templates.py` (AC-5 shape-name guard) and ADR-003 wording (decision support, never advice: the action label from the catalogue, never a sentence telling the user to exit).
6. Run in full every changed test file, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files.

Standing items:
- B4 (a) no new pass takes the job's whole time budget; the day-rule check is per strategy inside the existing check, no extra loop.
- B4 (d) answer states for the inputs the rule decides on: spot stated / absent; short LTP stated / absent; playbook rule present / switched off / malformed (missing `at` or `close_if_short_within_pct` -> not checked with a reason, never a crash and never True); calendar not needed here. Each tested.
- Clock: each check reads its own `now` (finding check-clock-read-once-per-batch); the domain never reads a wall clock, it takes `now` / `hhmm` from the caller.
- Money and percentages exact Decimal (ADR-008); no float. No new duplicated literal; ruff / mypy baselines must not rise; no regenerated aggregate files in this branch.
- Do NOT change `_tighten`'s behaviour (action 4); keep it working and its tests green.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s1a.

Attack list:
1. Fires at 14:29:59 (time compare wrong way or on minute rounding): test 14:29 -> no reading.
2. Fires on the day before expiry: test days_left = 1 -> no reading.
3. Opens a record every check after 14:30 (bypasses the gate or re-arms on every True): count stays 1 across 5 checks.
4. Spot missing reads as False (records a clear) or True: test -> None.
5. 0.3% boundary: a short exactly 0.3% away fires; 0.3001% does not (exact Decimal).
6. Mutants (scratch copy only, at most 5): drop the time check; use `<` for `<=` on the percent; write the record directly instead of through the gate; read the wrong short (long legs); hard-code Rs 2. Each must turn a test red; report each mutant -> test name.
