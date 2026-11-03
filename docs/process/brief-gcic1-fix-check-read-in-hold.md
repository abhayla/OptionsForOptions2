# Brief: GC-IC1 fix round 3 (after independent review) - REQ-155 / REQ-165: the screen check reads its quotes INSIDE the hold

Core: `read_market` takes one frozen read (option quotes of the held contracts AND the index quote) while the hold is still on, and never asks the provider again after the release, so the chain model gets its spot and forward and every held strike has Greeks; the approaches' landing strikes are priced in one bounded second pass.
Proof: step 1 of this brief - the test fake is made to behave like the live book (its `unsubscribe` clears `held`, so a released contract's quote is gone, as `QuoteBook.park` does live); the round-2 test then goes RED on 690ebe52; after the fix it is green. After merge the orchestrator re-runs strategy 82 live: T-03 checked with a delta near the paper book's (24000 CE about -29.7 per position = about 0.46 per unit), A-05 `step_basis: delta`, and A-05 / A-01 either priced or refused at delta, never "has no price".
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 3 (after the independent review; the class's 2nd red)
Findings checked: live-subscription-lost-on-release-reacquire, engine-input-chosen-per-caller, check-greeks-need-chain-screen-open
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - any provider read after the hold's release (the defect); a roll that silently picks a strike past a gap in the held strikes (a wrong roll); a second pass that waits more than once; holds never released; a second hold rule beside the paper book's. Out of scope - T-11's entry ATM IV (issue filed separately), the paper book's own Greeks function, the background worker path.
Sensibull: n/a - server-side data path.
Reference: none - searched hold and read, parked quote, roll strike search
Copy from: `backend/ofo_app/routes/paper.py` `_hold_until_ready` and its read at ~322-330 (the F-3 fix: read before release). Share ONE hold-and-read helper; do not write a third.
Tier: A (market data path, approaches money; fresh review only if the orchestrator's live proof fails).
Size: M, about 5 files, 4 items
CI: the app job runs `tests_app/test_adjustment_readers.py` under `pytest-app.ini` (pure, fake provider); the backend unit job runs `tests/adjustment` (approaches); vars: none (no DB)

## Independent review this round is built on (2026-11-03, accepted by the orchestrator)
1. MAJOR: `adjustment_readers.py:253-255` releases the hold in `finally` -> `fanout.py:66-78` -> `kite_provider.py:221-223` parks it -> `feed_health.py:246` drops it -> `feed_health.py:297-299` answers None; then `adjustment_readers.py:320-321` re-reads the spot -> `chain_values.py:139-142` SPOT_REFUSED -> `forward.py:139-140` no forward -> no Greeks for ANY strike, `_atm_vol` None. Rounds 1 and 2 (window holding) could never fix this.
2. MAJOR: `approaches.py:304-318` `roll_distance` searches only quoted strikes; with holes in what is held it refuses "no strike at delta" or silently picks past the hole.
3. MAJOR: the Compare's after-Greeks come only from `leg_greeks` (`compare.py:432`): every landing strike nobody holds has none, and is "has no price".
4. Test gap: the fake's `unsubscribe` (`test_adjustment_readers.py:153-154`) never clears `held`, so both earlier rounds' tests passed against a book that never parks.
(Deferred: T-11 entry ATM IV only filled in scenario mode -> separate issue; paper vs check Greeks functions differ -> information.)

## Where
`git switch -c build/gcic1-check-hold <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). NO DB tests (the orchestrator runs DB tests one job at a time).

## Do, in order
1. Fake fixed first (unsubscribe clears `held`; a read of a released contract answers None, like `QuoteBook.park`); show the round-2 test RED on the current code; add a test that drives the real `QuoteBook.park` if it is constructible without the network.
2. One hold-and-read helper (shared with the paper book's `_hold_until_ready`): it returns a frozen snapshot (option quotes + index quote) taken while held; `read_market` builds everything (chain model, forward, Greeks, ATM vol, feed spot reading) from that snapshot only. Grep that no provider read remains after the release.
3. Strikes the roll searches, in the same single hold: for each short, every listed strike of its type from the short to the spot (inward) and out past its wing by `roll_points_without_delta` (outward), plus the window and the legs. A test: a gap in the held strikes makes `roll_distance` refuse naming the gap's strike, never pick past it.
4. Landing strikes: the approaches route gets from the builder the target contracts it could not price, holds those once (at most one more `LEG_WAIT_S`), and recomputes. A test that the second pass happens at most once and its hold is released.
5. Run `tests_app/test_adjustment_readers.py`, `tests_app/test_background_cycle.py`, `python -m pytest -q tests/adjustment`, the paper route's pure tests if the shared helper touches it, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.
6. Bump knowledge/findings/live-subscription-lost-on-release-reacquire.json: occurrence 2026-11-03 (adjustment check, strategy 82), detection += the fixed fake and the read-after-release test; note the shared helper.

Standing items:
- B4 (a) total wait per check stays bounded: one hold wait + at most one second-pass wait, each `LEG_WAIT_S`.
- B4 (d) answer states per contract: quoted at once / quoted after the wait / never quoted (unpriced, named) / no token / feed absent / provider disconnected; and the index: quoted / not (no forward, named reason, never a guess).
- B8: the guarantee is structural (one helper returns a frozen read; nothing reads the provider after release), not a detector.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-check-hold.

Attack list:
1. Any provider call after the release in `read_market`: a test with a fake that raises on any read after unsubscribe.
2. A gap in held strikes: roll refuses naming the strike, not picks past it.
3. Second pass loops (recompute -> new unpriced -> hold again): at most once.
4. Hold leaked on an exception in the second pass: released.
5. Mutants (scratch copy, at most 5): read spot after release; fake that never parks (the round-1/2 shape); roll search skipping the gap check; second pass unbounded; window-only hold without the roll range. Each turns a test red; report mutant -> test name.
