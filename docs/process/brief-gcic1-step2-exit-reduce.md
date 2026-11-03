# Brief: GC-IC1 step 2 - REQ-155 AC-1 / AC-8, ADR-238: exit and reduce approaches A-24, A-25, A-26, A-27, A-35

Core: the approach builder builds the five exit and reduce approaches the approved iron condor playbook lists but never shows (A-24, A-25, A-26, A-27, A-35), each priced by the one engine as a full After through the existing pricing path, each refusal naming its reason, exactly as defined in ADR-238.
Proof: step 1 of this brief - on ADJ-02 and ADJ-13 each new approach's trades, After legs and Compare cost equal the generator's engine-free figures to the paisa (tests/test_adjust_scenarios.py style), and the approaches route returns them as columns (one app test).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a second exit builder beside A-31 (one code path, ADR-238 (1)); a partial close that leaves a fractional lot; A-27 reading a limit other than T-09's current-stage threshold; A-35 offered before its time; a money figure computed outside the engine (ADR-008); S-11 (adjustment limit reached) dropping one of these exit and reduce approaches. Out of scope - roll approaches (step 3), non-trade approaches A-23 / A-37 / A-38 (step 4), the Compare layout (columns come from the API as today).
Sensibull: n/a - server-side approach builder; the Compare screen renders the new columns through its existing layout (Sensibull has no adjustment comparison in the study).
Reference: none - searched take profit, partial close, buy back cheap shorts, time exit
Copy from: `docs/process/legacy-reuse.md` has no row for adjustment approaches (checked). Reuse inside this repo, listed below.
Tier: A (money; fresh Opus review follows; mutation tests required).
Size: M, about 12 files, 5 items
CI: the backend unit job runs `tests/` (builder, generator cases, template pins, settings registry); the app job runs `tests_app/` under `pytest-app.ini` (approaches route); vars: TEST_DATABASE_URL (CI postgres service; locally db_run_fresh sets it)

## Where
`git switch -c build/gcic1-s2 <sha given in the dispatch>` inside your agent worktree (feature/adjustments, never main, never push). DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py -k <name>`
One file at a time; long output to a log file, tail only.

## Decision it builds to
`spec/decisions/ADR-238.md` (read all five parts; they fix the legs, the limits and every refusal). REQ-155 AC-1 / AC-8, REQ-156 (Compare cost), REQ-157 (S-11 filter is the caller's), REQ-168 AC-1 (user preferences).

## Reuse (grep before any new function; report each as reused / new-with-reason)
- `backend/ofo/adjustment/approaches.py` `build_approach`: one branch per approach; `_Builder.close(leg, lots)` makes a closing trade + ClosedLeg; A-31's branch is the close-all; A-28 closes one side; A-29 shows whole-lot partial closing and its refusal. A-24 and A-35 MUST reuse A-31's close-all (factor it into one helper both call), not copy it.
- `APPROACH_IDS`, `KINDS`, `NAMES` (labels already exist in `ADJUSTMENT_APPROACH_LABEL_TEXT`; check, do not add a duplicate label).
- Compare cost and the After: `backend/ofo_app/adjustment_check.py` `priced_approach` / `price_after`, and `backend/ofo/adjustment/compare.py` ordering by `APPROACH_IDS`.
- T-09's measure and threshold: `backend/ofo/adjustment/playbook_eval.py` `short_premium` (step 1a) and the playbook's `triggers["T-09"]` stage values (iron condor weekly Rs 3 / 3 / 2, `cmp: le`). A-27 reads the current stage's T-09 threshold.
- The expiry-day rule already names A-27 through T-09's current-stage threshold (step 1a fix round). Reuse that same reader for the A-27 builder; do not add a second one.
- Guard `time_exit` (iron condor 14:30) in the playbook `guards`: A-35's time; read through `guards_of_body`.
- New user preferences through the settings registry exactly as `adjustments.reduce_divisor` is done (`backend/ofo/settings/registry.json`, `backend/ofo/adjustment/preferences.py` KEYS / `Config` / `from_values`), with defaults 50 and 80 (ADR-238 (2), (3)). If the Preferences tab lists registry keys automatically, check it shows them; if it needs a frontend line, add it.
- The generator's independent copy: `tests/adjust_scenarios_gen.py` `hand_approaches` (extend it for the five; written independently of the builder, never importing it) and `EXIT_REDUCE`.

## Do, in order
1. CORE (failing tests first): the five branches in `build_approach` per ADR-238, inputs the builder lacks today (T-09 threshold of the stage, `time_exit`, the check's HH:MM) passed in explicitly by the caller, never read from a clock or a global. Generator expectations on ADJ-02 and ADJ-13 for all five; builder == generator to the paisa.
2. Refusals and warnings per REQ-155 AC-8 for each: A-25 fractional lots (name the leg), A-26 not decayed enough (state the decay), A-27 no short at or below the threshold (name it), A-35 before the time (name it). New user-visible text in `backend/ofo/errors/explanations.py`, pinned in `tests/errors/template_pins.json` as pending owner read; decision-support wording (ADR-003).
3. Wire into the route and the screen check: the approaches route and `cheapest_offered` see the new ids (they already filter by the playbook's `applicable` list; confirm S-11 keeps all five as EXIT_REDUCE). One app test on the approaches route returns the five columns for ADJ-02.
4. Run in full every changed test file, `tests/strategy/test_templates.py`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files (compare against the base commit for pre-existing errors).

Standing items:
- B4 (d) answer states for each approach's inputs: leg price stated / absent (absent -> refused naming the leg, as today); T-09 off or missing in the playbook -> A-27 refused "no limit in this playbook", never a default; `time_exit` missing -> A-35 refused, never a default; lots 1 / 2 / 3 / 4 for A-25 at 50%; entry price 0 for A-26 (refused, no division by zero).
- Money exact Decimal (ADR-008); planned prices by the existing ADR-068 (1) rule; no float. No new duplicated literal; ruff / mypy baselines must not rise; generated aggregates out of this branch except the regenerated `system_playbooks.json` and the new or changed scenario files.
- Run every DB test LAST, after the final refactor.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s2.

Attack list:
1. A-24 or A-35 trades differ from A-31's on the same position (they must be identical): test equality.
2. A-25 at 50% on 3 lots closes 1 lot (floor) instead of refusing: test refuses.
3. A-26 decay computed from the wrong leg (the tested short) or against LTP instead of entry: ADJ case where only the untested short decayed 80% -> offered; tested decayed -> not.
4. A-27 threshold from the wrong stage (Early Rs 3 used on the last day): test last-day 2.50 not named, Early 2.50 named.
5. Mutants (scratch copy only, at most 5): A-25 floor instead of refuse; A-26 `>` for `>=`; A-27 reads the Early stage always; A-35 ignores the time; A-24 builds its own close-all list missing one leg. Each turns a test red; report mutant -> test name.
