# Brief: GC-IC1 fix - REQ-165 AC-5 / REQ-155: the screen check has no Greeks or ATM IV for an expiry with no chain screen open

Core: the screen's adjustment check (`backend/ofo_app/adjustment_readers.py` `read_market`) holds the same near-the-money strike window of the position's expiry that the background worker holds (`background.Worker._window_tokens_of`: `chain_push.strike_window` around `chain_push.atm_strike`, `settings_calc.chain_strikes_each_side` each side), so the chain model gets its forward and every leg its Greeks, without anyone having the chain screen open.
Proof: step 1 of this brief - a failing test first on `read_market` (fake provider: the expiry's book holds only the 4 position legs; the window strikes quote only once held): before, `leg_greeks` is empty and the vol is None; after, `leg_greeks` has all 4 legs and the vol is stated. After merge the orchestrator re-runs GET /api/strategies/82/adjustment-check live (at 11:12 today T-03 answered not_checked "Delta of a short leg not available" and T-11 "ATM IV not available" while the paper book of the same strategy showed the 24000 CE delta at about 0.46).
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, check-clock-read-once-per-batch, staleness-by-last-change-age
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - a second strike-window rule beside the worker's (one function both call); a hold that is never released (the existing `chain_quotes` always releases: keep that); a check that now waits longer than `LEG_WAIT_S` (3 s) once; the screen and the worker deriving different Greeks for the same leg (they already differ in source: chain model vs shared per-option figures; this fix only gives the screen its inputs). Out of scope - the worker's path, the paper book's Greeks, the chain screen.
Sensibull: n/a - server-side data holding.
Reference: none - searched strike window, chain model forward, leg greeks
Copy from: `background.Worker._window_tokens_of` (`backend/ofo_app/background.py` ~line 675): move its window rule into ONE function (e.g. in `chain_push` or `adjustment_readers`) that both the worker and `read_market` call.
Tier: B (one reader; the orchestrator re-runs the live check).
Size: S, about 4 files, 1 item
CI: the app job runs `tests_app/` under `pytest-app.ini` (reader test, if it needs the app fixtures) or the backend unit job runs `tests/` (if pure with a fake provider); vars: TEST_DATABASE_URL only if a DB test is added

## Defect-fix contract
- RCA: `read_market` calls `chain_quotes(..., own_leg_ids(position, listed), live)`, which holds only the position's legs; the chain model needs near-the-money quotes for its parity forward, so with no chain screen open for that expiry there is no forward, no Greeks and no ATM IV.
- Class: every position whose expiry has no open chain screen (typically every monthly / far expiry) x every rule that reads Greeks or IV on the screen check (T-03 tested short delta, T-11 IV change, T-05, the A-02 / A-05 roll distance by delta). Before: not checked. After: checked.
- Failing test first (above).
- Fix: hold window ids plus own leg ids in `read_market` (one shared window function; the worker calls it too).
- Proof: the test plus the orchestrator's live re-run.
- Detection: a test asserting `read_market` asks `chain_quotes` for the window ids (so a refactor that drops them fails), and register the class in knowledge/findings as `check-greeks-need-chain-screen-open` (class, mechanism with file:line, first_seen = strategy 82 today, detection = the new test).

## Where
`git switch -c build/gcic1-check-window <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). NO DB test runs in this brief (the orchestrator runs DB tests one job at a time on the shared server; a parallel job exhausts the role's connections). If a test needs the DB, write it and name it in the report as not run.

## Do, in order
1. Failing test (fake provider), then the shared window function, then `read_market` holds it.
2. The worker calls the same function (its behaviour unchanged: its existing pure tests, if any, stay green).
3. The finding file.
4. Run the pure test files touched, `python -m pytest -q tests/adjustment` (log to file, tail), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (a) the window hold reuses `chain_quotes`' existing wait (`LEG_WAIT_S`), never a longer one.
- B4 (d) answer states: spot live / no spot (no window, legs only, as today) / expiry not listed (no window) / window strike with no token (skipped) / feed absent (as today).
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-check-window.

Attack list:
1. Two window rules (worker and screen) after the change: grep; one function.
2. No spot: the window is empty and the check still answers for the legs (no crash, no wait).
3. The hold is released on timeout and on error (the existing `finally`): test with a provider that raises.
4. A window strike with no token (KeyError path in `chain_quotes`): the legs still get held and quoted.
5. Mutants (scratch copy, at most 5): window not passed; window of the wrong expiry; hold never released; window each-side 0; worker keeps its own copy. Each turns a test red; report mutant -> test name.
