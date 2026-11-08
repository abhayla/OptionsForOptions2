# Brief: GC-IC1 step 1b - REQ-159 AC-4: the before-weekend and before-holiday carry check (action 0) raises one record at 15:00 with engine figures

Core: (built on step 1a, merged first) the iron condor playbook's switched-on `beforeWeekend` and `beforeHoliday` day rules (`at: 15:00`, `action: 0`, carry check) raise one record at their time through the same alert gate, carrying the S-06 content: the overnight margin and the whole-trade P&L if spot gaps 2% up and 2% down at the next session's open, priced by the engine.
Proof: step 1 of this brief - a new generator case on a Friday (a real session day before a weekend, taken from the calendar) run through the REAL background Worker with a pinned clock on a fresh DB: 14:59 -> 0 records; 15:00 -> exactly 1 carry-check record whose gap figures equal the generator's independently computed values to the paisa; a Wednesday case with Thursday a normal session -> 0 records. Rows counted by SQL.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, check-clock-read-once-per-batch
Spec quote: REQ-159 AC-4 "Each carries a time and one action: carry check, show reduce or exit, show add-hedge, pause, tighten every"
Threat model: in scope - a weekday assumed to be a session when the holiday list has no row for that year (must read "holiday list not known", never fire and never assume); a carry check opening a record every check after 15:00 (gate edge); gap figures computed by a second formula instead of the engine (ADR-008, finding engine-input-chosen-per-caller); a margin the broker did not state shown as a number. Out of scope - the other day-rule kinds (away, event, dom, date, afterBreak), action 4 tighten (exists), action 5 (step 1a), the editor screen.
Sensibull: n/a - server-side rule and record content; the record renders in the existing inbox (no layout change in this step).
Reference: none - searched carry check, overnight margin, gap loss; the what-if screen's open difference records are untouched: this step reuses only its valuation function, not its screen
Copy from: none in `docs/process/legacy-reuse.md` for a carry check (checked). Reuse step 1a's day-rule function and record path; write no parallel evaluator.
Tier: A (fresh Opus review follows; mutation tests required).
Size: M, about 8 files, 1 item
CI: the backend unit job runs `tests/` (pure day-of-week and gap figures, generator case, template pins); the app job runs `tests_app/` under `pytest-app.ini` (worker proof); vars: TEST_DATABASE_URL (set by CI's postgres service; locally db_run_fresh sets it)

## Where
Branch `build/gcic1-s1b` from ff4babc7 (feature/adjustments with step 1a merged). Commit there only, never push, never touch main. DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py -k <name>`
One file at a time; long output to a log file, tail only.

## Decisions it builds to (technical calls made by the orchestrator, recorded here)
- Day kinds from `backend/ofo/market_calendar.py` (NSE F&O holiday data). Before-weekend = today is a session and the next session is after a Saturday (the generator's `day_type` rule). Before-holiday = today is a session and the next calendar weekday is a listed holiday. A year with no holiday rows (`NO_CALENDAR`) -> the rule is not checked, with the reason "holiday list not known"; never assume a weekday is a session.
- Gap figures: whole-trade P&L (booked plus open legs) with spot at S x 1.02 and S x 0.98, valued at the NEXT session's open. REUSE, do not write a new valuation: the what-if path `backend/ofo/scenario/views.py` `scenario_values(level_set, inputs, view, rates=, at=)` (its docstring: it values a what-if time through the one engine estimate function, never a second formula) with `at` = the next open from `backend/ofo/market_calendar.py` `next_open(now)`, and the existing whole-trade helpers (`backend/ofo/engine/whole_trade.py`) for booked P&L. If those cannot take a +/-2% level, extend them; never a parallel formula (ADR-008). The screen and the worker both call the same function.
- Before writing ANY new function, grep for one that already does the job (day kinds: `market_calendar.next_open` / `market_status`; the generator's `day_type` shows the rule) and name it in the report as reused, or why not. The generator computes the expected values separately (Fraction arithmetic over its own `option_row`-style leg values) and stores them in the case's `expected` block.
- Overnight margin: the broker-stated margin read the check already has (`state == "stated"`); otherwise the record says margin not known. Never a computed stand-in.

## Do, in order
1. CORE (failing test first): the carry-check day rules produce yes/no readings through step 1a's function and `gate_readings`; True from `at` on a matching day; no reading before the time, on other days, or with no calendar for the year.
2. Record content: the carry check record carries the two gap P&L figures and the margin (or its not-known reason). New user-visible words go into `backend/ofo/errors/explanations.py`, pinned in `tests/errors/template_pins.json` marked as pending owner read; decision-support wording (ADR-003).
3. Generator: Friday case (and one before-holiday case on a real listed holiday from the calendar data), plus the Wednesday no-fire case, with engine-free expected figures.
4. Worker proof as stated above; screen parity test (pure).
5. Run in full every changed test file, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `tests/strategy/test_templates.py`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files.

Standing items:
- B4 (a) no new loop with its own time budget; the carry check is part of the existing per-strategy check.
- B4 (d) answer states: calendar row present / year missing / day is a holiday itself; spot stated / absent; IV per leg stated / absent (absent -> gap figures not known with a reason, never a zero); margin stated / not stated / read failed. Each tested.
- Each check reads its own `now`; the domain takes `now` from the caller.
- Exact Decimal money (ADR-008), paisa rounding as the engine does; no float. No regenerated aggregate files. ruff / mypy baselines must not rise.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s1b.

Attack list:
1. Year missing from the calendar: rule fires anyway (assumed session) -> test expects no reading and the reason.
2. A Thursday before a Friday holiday counted as before-weekend AND before-holiday: two records for one evening -> state what happens and test it (one record per rule id is correct; both rules are switched on).
3. Gap figures valued at expiry (intrinsic) instead of the next open: the Friday case's figures differ from the generator's -> red.
4. Records reopen after 15:00 on every check: count stays 1 across 5 checks.
5. Mutants (scratch copy only, at most 5): use today's time to expiry instead of the next session's; drop the NO_CALENDAR guard; swap +2% and -2%; float in the gap maths; fire at 14:59. Each turns a test red; report mutant -> test name.
