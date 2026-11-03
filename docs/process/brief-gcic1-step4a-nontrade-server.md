# Brief: GC-IC1 step 4a (server) - REQ-155 AC-1, REQ-170 AC-5: non-trade approaches A-23, A-37, A-38

Core: the user-chosen pause (A-38) makes the background worker skip ADJUSTMENT checks of that one strategy until the chosen time, while its stop-losses and paper exits still fire inside the pause (REQ-170 AC-5: risk exits never pass through the alert gate and are never paused).
Proof: step 1 of this brief - on the REAL background Worker with a pinned clock on a fresh DB: strategy paused until 10:30; a T-01 crossing at 10:10 opens no adjustment record; a paper stop crossing at 10:15 still fires its exit; at 10:31 the T-01 crossing (still true) opens one record through the gate. Rows counted by SQL.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, check-clock-read-once-per-batch
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a pause that also silences stop-losses or paper exits (REQ-170 AC-5); a pause with no end (must always carry a time, and expire by itself); a pause read from the wall clock instead of the check's own time; A-23 figures computed outside the engine (ADR-008); a level watch (A-37) built as a second alert system beside the REQ-041 rules. Out of scope - the screen inputs (step 4b), the Notifier.
Sensibull: catalogue-raw.md line 55 (Greeks tab: per-leg delta and a Total; the model for A-23's net delta), line 222 (conditional exit when the index crosses a level; nearest to A-37, which only alerts); the study has no pause feature.
Reference: none - searched pause monitoring, delta neutral, watch a level; RD-124 (REQ-035 AC-1 separate Greeks view) open and untouched: A-23 only reads the existing Greeks total
Copy from: `docs/process/legacy-reuse.md` has no row for these (checked). Reuse inside this repo, listed below.
Tier: A (worker); A-23 / A-37 parts Tier B.
Size: M, about 12 files, 3 items
CI: the backend unit job runs `tests/` (A-23 figures, A-37 rule build); the app job runs `tests_app/` under `pytest-app.ini` (worker pause proof, routes); vars: TEST_DATABASE_URL (CI postgres service; locally db_run_fresh sets it)

## Where
`git switch -c build/gcic1-s4a <sha given in the dispatch>` inside your agent worktree (feature/adjustments, never main, never push). DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py -k <name>`
One file at a time (test_background_worker.py whole takes ~14 min: use -k); long output to a log file, tail only.

## What each approach is (technical calls, orchestrator; ADR-238 / ADR-239 style, recorded in the report)
- A-38 (pause monitoring until a time): the user picks a time today (HH:MM, after now, before the session close); stored per strategy with the user who set it; the worker and the screen check skip that strategy's adjustment evaluation until then and show it as paused with its end time; the pause ends by itself at that time (no action needed) or when the user clears it. Risk exits (REQ-041 rules with an exit action, paper stops) run as before.
- A-37 (alert only, watch a level): the user picks an index level; this creates a REQ-041 rule with action `alert_only` (`backend/ofo/rules/model.py` RuleAction.ALERT_ONLY) on the underlying level, through the existing rules store and evaluation. No new alert path.
- A-23 (delta-neutral helper): figures only, no trade: the position's net delta now (engine Greeks summed over the legs, as the Greeks total) and, to bring it to 0, the lots of the nearest-ATM option of the needed type or the lots of the index future (exact Decimal, rounded to whole lots, the remaining delta after rounding stated).

## Reuse (grep before any new function; report each as reused / new-with-reason)
- Worker paused state: `backend/ofo_app/background.py` (MonitoringStatus.PAUSED, "Monitoring paused", the per-strategy skip paths) and `alert_gate.pause`; a user pause is one more reason in the same path, not a parallel skip.
- REQ-041 rules: `backend/ofo/rules/` (model, conditions, inputs, actions, defaults) and the existing rules routes/store; the existing underlying-level input.
- Engine Greeks: `backend/ofo/engine/model.py` `leg_greeks_unrounded` and the position total used for REQ-035 AC-6; never a new Black-Scholes call.
- Approach columns: `approaches.py` (`APPROACH_IDS`, `KINDS`; A-36 is the existing non-trade column to copy the shape from), the approaches route.
- Storage: a new migration only if no existing per-strategy table fits (check the playbook plan / rule_state tables first); additive, head-based (`alembic`), with its downgrade.

## Do, in order
1. CORE (failing test first): the A-38 worker proof above.
2. A-38 route: set / clear a pause (owner-only on their own strategy; a time in the past or after the close refused with its reason); the screen check returns the paused state and end time.
3. A-37 through the REQ-041 rule store; A-23 figures in the approaches reply as a non-trade column (no After change, like A-36).
4. New user-visible text in `backend/ofo/errors/explanations.py`, pinned in `tests/errors/template_pins.json` as pending owner read; ADR-003 wording (A-23 states figures, never an instruction to buy).
5. Run in full every changed test file, `tests/strategy/test_templates.py`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files (compare with the base commit). A migration: `tests_app/test_migrations*.py` too.

Standing items:
- B4 (a) the pause check is a cheap read per strategy inside the existing cycle (no extra loop, no DB round trip per check if the strategy list already carries it: #636 measured ~0.7 s per round trip from this PC).
- B4 (d) answer states: pause set / none / expired / cleared / set by another user (refused); level stated / not a number / no underlying price; Greeks present / a leg with no IV (A-23 says "not known" naming the leg, never 0).
- Each check reads its own `now`; the domain takes `now` from the caller.
- Money and Greeks exact Decimal (ADR-008). ruff / mypy baselines must not rise; no regenerated aggregates.
- Run every DB test LAST, after the final refactor.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s4a.

Attack list:
1. Paper stop inside the pause does not fire: test it fires.
2. The pause never ends (stored with no end, or compared by date only): test 10:31 opens the record.
3. A pause set at 15:20 for 15:40 (after the close) is accepted: test refused.
4. A-23 lot count truncates instead of rounding to the nearest whole lot, or ignores the lot size: test with lot 65 and 75.
5. Mutants (scratch copy only, at most 5): pause also skips paper exits; pause compared with the wall clock; pause has no expiry; A-23 uses one leg's delta only; A-37 writes its own alert row instead of a rule. Each turns a test red; report mutant -> test name.
