# Brief: GC-IC1 fix round 5 (after the second independent review) - REQ-155 AC-1: hold the whole delta reach of a roll in the one second pass

Core: the approaches route's single second pass holds every strike a delta-based roll can land on (for each short, on its expiry and the next: from the short outward to one strike past the first strike whose MODEL delta is at or under the target, plus the same range shifted by the wing width), so A-05 / A-04 on a far expiry are priced, or refused for a true reason (debit limit, not listed, never ticked), in at most one more wait.
Proof: step 1 of this brief - a failing test first with a fake fan-out that quotes ONLY held ids and a target four strikes past today's fixed 200-point reach: today A-05 and A-04 come back "has no price" (wing landing never held); after the fix both are priced after exactly one second pass, with the wing landing held. After merge the orchestrator re-runs strategy 82 live (13:55 today: A-05 refused for 25,250 CE, A-04 for 24,800 CE Jan; Kite quoted all 8 target contracts in 0.69 s through planned-entry, so the quote is not the problem).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 5 (after a second independent review; the class's 4th red)
Findings checked: live-subscription-lost-on-release-reacquire, engine-input-chosen-per-caller, check-greeks-need-chain-screen-open
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a model price used as a planned price (FORBIDDEN: ADR-068 (1) planned entry = LTP, else the bid / ask mid; ADR-020 Q185 no fake prices; the model only chooses WHICH strikes to hold); a hold that grows without bound (cap the reach: at most N strikes per short, N a named constant, e.g. 30, with a test); a third read; the A-02 "past its wing" refusal or the A-05 debit-limit refusal changing. Out of scope - which price the Compare uses for a quiet strike (owner question parked), the worker path (#642), wording.
Sensibull: n/a - server-side data holding.
Reference: none - searched delta reach, roll landing, second pass
Copy from: none; the reviewer's design below.
Tier: A (approaches money path; the orchestrator's live proof decides; a further red = park with the evidence).
Size: M, about 6 files (reader, route, tests, finding), 1 item
CI: the app job runs `tests_app/test_adjustment_readers.py` and the route's pure tests under `pytest-app.ini`; the backend unit job runs `tests/adjustment`; vars: none (no DB)

## Second independent review (2026-11-03 13:5x, accepted)
1. Root cause: `roll_distance` walks one strike per pass. Pass 1 holds up to wing + 200 (`adjustment_readers.py:324-327`); no held strike fits the 0.25 target, so the first unheld strike (24,750) is a gap and is the only id sent to pass 2; pass 2 holds 24,750, it fits, distance 750, the wing lands on 25,250, never held -> "no price". On the next expiry the walk hits the next gap (24,800). One bounded pass can never catch up.
2. The wing landing is never in the hold: the reach is fixed in points, the move is delta-based (750-800 points on far expiries).
3. Refuted: Kite slowness (8 targets ticked in 0.69 s), missing next-expiry ids.

## Where
`git switch -c build/gcic1-delta-reach <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). NO DB tests.

## Do, in order
1. Failing test (fake fan-out quoting only held ids) as in the Proof.
2. `delta_reach_ids(listed, position, model, target, expiry)` in `backend/ofo_app/adjustment_readers.py`: for each short on its expiry and the next, walk listed strikes outward from the short using the engine's Black-Scholes delta at a conservative IV (the highest IV the frozen chain model has for that expiry's quoted strikes); stop at the first strike whose model delta is at or under the target, add one more strike; return that range plus the same range shifted by the wing width (and for A-04 the next-expiry equivalent); capped at N strikes per short.
3. The route's second pass holds `unpriced_ids` UNION `delta_reach_ids(first-read models)` in ONE hold; no model -> today's behaviour. Still one second pass.
4. Tests: wing landing held; mutants (no wing shift; no +1 strike; no cap) each turn a test red; A-05 debit-limit refusal and A-02 past-its-wing refusal unchanged.
5. Run `tests_app/test_adjustment_readers.py`, `tests_app/test_background_cycle.py`, `python -m pytest -q tests/adjustment`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.
6. Bump knowledge/findings/check-greeks-need-chain-screen-open.json (or the class the reviewer named) with this occurrence and the new detection test.

Standing items:
- B4 (a) one more wait at most (`LEG_WAIT_S`), whatever the reach size.
- B4 (d) answer states: model present / absent (today's behaviour); target reached within the cap / not (refused, named); a strike in the reach not listed (skipped).
- No model price is ever a planned price (ADR-068 (1)); exact Decimal; engine owns the delta.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-delta-reach.

Attack list:
1. A model price leaks into a Trade price: grep and a test asserting every trade price came from a quote.
2. The reach includes thousands of strikes (no cap): capped, tested.
3. A third read: still at most one second pass.
4. A-02 refusal "past its wing" changes: unchanged (test).
5. Mutants (scratch copy, at most 5): no wing shift; no +1; no cap; model IV lowest instead of highest; next expiry skipped. Each turns a test red; report mutant -> test name.
