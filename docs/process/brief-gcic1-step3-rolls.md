# Brief: GC-IC1 step 3 - REQ-155 AC-1 / AC-8, ADR-239: roll approaches A-02, A-04, A-06

Core: the approach builder builds the three roll approaches the approved iron condor playbook lists but never shows (A-02, A-04, A-06) exactly as ADR-239 defines them, each priced by the one engine as a full After through the existing pricing path; A-04 reads the next listed expiry's chain.
Proof: step 1 of this brief - on ADJ-02 and ADJ-13 each new approach's trades, After legs and Compare cost equal the generator's engine-free figures to the paisa; A-04 on a case whose next expiry has no chain rows is refused with the reason; the approaches route returns the three columns (one app test).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a second roll-distance rule beside `_Builder.roll_distance` (one rule, ADR-239 (1)); A-02 landing a short at or past its wing; A-04 pricing the next expiry with the current expiry's chain or forward; A-06 bypassing the REQ-078 landing / step rule; a roll that skips the roll debit guard (ADR-230); money outside the engine (ADR-008). Out of scope - exit and reduce approaches (step 2), day rules on two-expiry positions (#640), the Compare layout.
Sensibull: S-107 per-leg strike arrows are the model for A-06's one-strike step (already built as REQ-078 in leg_edit); no new screen.
Reference: none - searched roll the tested side, roll up and out, shift a leg
Copy from: `docs/process/legacy-reuse.md` has no row for adjustment approaches (checked). Reuse inside this repo, listed below.
Tier: A (money; fresh Opus review follows; mutation tests required).
Size: M, about 10 files, 3 items
CI: the backend unit job runs `tests/` (builder, generator cases, settings registry); the app job runs `tests_app/` under `pytest-app.ini` (approaches route, next-expiry chain read); vars: TEST_DATABASE_URL (CI postgres service; locally db_run_fresh sets it)

## Where
`git switch -c build/gcic1-s3 <sha given in the dispatch>` inside your agent worktree (feature/adjustments with step 2 merged; never main, never push). DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py -k <name>`
One file at a time; long output to a log file, tail only.

## Decision it builds to
`spec/decisions/ADR-239.md` (all three parts), REQ-155 AC-1 / AC-8, ADR-230 (roll debit limit), REQ-078 (strike landing and steps), REQ-168 AC-1 (user preference).

## Reuse (grep before any new function; report each as reused / new-with-reason)
- `backend/ofo/adjustment/approaches.py` `_Builder.roll_distance` (target delta or points), `_Builder.roll`, `_Builder.land` (REQ-078 landing), `_Builder.replace`, `_Builder.close`, `guard_debit`, `adjust_roll_would_cross`. A-02 is `roll_distance` applied to the short only plus a wing check; A-04 is `roll_distance` on the next expiry's rows; A-06 uses `ofo.strategy.leg_edit.step_strike` (or `shift`) for N steps, never its own strike arithmetic.
- The chain the builder sees today holds only the position's expiry. A-04 needs the next listed expiry's rows: extend the existing chain reader the approaches route and `cheapest_offered` use (`backend/ofo_app/adjustment_readers.py`, `adjustment_check.py`), one reader for both; grep for how the route builds `ChainRow`s before writing anything.
- The new preference `adjustments.shift_strikes` exactly as `adjustments.reduce_divisor` and step 2's preferences are done (registry, `preferences.py`, `Config`).
- The generator's independent copy `tests/adjust_scenarios_gen.py` `hand_approaches` (extend it; never import the builder). A next-expiry chain in the scenario via the generator's existing `chain(...)` helper.

## Do, in order
1. CORE (failing tests first): the three branches per ADR-239; generator expectations on ADJ-02 and ADJ-13; builder == generator to the paisa.
2. Refusals and warnings (REQ-155 AC-8): A-02 at or past its wing (name both strikes); A-04 no next-expiry rows / no price (name the expiry); A-06 target not listed (landing rule's own text). New user-visible text in `backend/ofo/errors/explanations.py`, pinned in `tests/errors/template_pins.json` as pending owner read; ADR-003 wording.
3. Wire into the route and the screen check (same as step 2); one app test on the approaches route returns the three columns for ADJ-02.
4. Run in full every changed test file, `tests/strategy/test_templates.py`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files (compare with the base commit).

Standing items:
- B4 (d) answer states: next expiry listed with prices / listed with no prices / not listed; deltas present / absent (points fallback, as A-05); target strike listed / not; debit within the limit / over it. Each tested.
- Money exact Decimal (ADR-008); no float. No new duplicated literal; ruff / mypy baselines must not rise; generated aggregates out of the branch except new scenario files.
- Run every DB test LAST, after the final refactor.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s3.

Attack list:
1. A-02 moves the wing too (then it equals A-05): test the wing strike is unchanged.
2. A-04 prices the new legs with the current expiry's forward or rows: test with a next-expiry chain whose prices differ.
3. A-06 at N = 2 skips an unlisted strike by arithmetic instead of the listing: test with a gap in the listed strikes.
4. A roll over the debit limit is offered: test refused per ADR-230.
5. Mutants (scratch copy only, at most 5): A-02 moves the wing; A-02 wing check `>` for `>=`; A-04 reads the current expiry; A-06 adds N x strike gap instead of stepping the listing; drop guard_debit on A-04. Each turns a test red; report mutant -> test name.
