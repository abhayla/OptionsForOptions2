# Brief: GC-MU step 4 round 2 - one state builder for the screen and the background check

Core: the background check's state is built by the SAME public function the screen uses (`ofo_app.adjustment_check.state_of`), fed with the shared per-option figures, so a rule on max profit / max loss / margin fires in the background exactly as on the screen.
Proof: step 1 of this brief - on scenario ADJ-02 the background state and the screen's `state_of` state for the same prices are equal field by field (one assert on the whole dataclass), and the core test (one record within 1 s, no client) still passes.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 2/2 (last round; what is not green after this is PARKED)
Class: round 1 built a SECOND state builder (`light_state`, `backend/ofo_app/background.py:172-201` at 90bbcead) that copies `state_of` (`backend/ofo_app/adjustment_check.py:140-180`) and drops fields: `max_loss`, `max_profit`, `margin`, `atm_iv`, `prev_close` are always None there. Population: every playbook trigger that reads one of those fields (grep the system playbooks' triggers for them); before: never fires in the background; after: same verdict as the screen. The two red guards (`test_no_order_placement`: 5 private names; `test_no_wall_clock_asserts`: `tests_app/test_background_worker.py:133`) are symptoms of the same copy plus one test shortcut.
Proof (class): the field-by-field equality test above, plus one test per dropped field with a trigger that reads it (fires on the screen state -> fires in the background).
Findings checked: staleness-by-last-change-age, dependent-tests-not-run-stale-later
Threat model: in scope - the background verdict differing from the screen's for the same prices (a second state builder); a worker that places or sends an order (REQ-115 AC-2); a check on a stale price; a restart re-opening a record; a full scenario-table call from a background check (REQ-166 AC-2). Out of scope - the feed's wanted-token key (step 4b), the admin Settings store (GC-SET; stand-in kept), alerts through the Notifier.
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Sensibull: n/a - server background role, no screen.
Reference: none - searched background checks, playbook triggers (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - reuses this repo's own `state_of`.
Tier: A (fresh Opus verifier follows; mutation tests required).

## Where
Same worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-bg`, branch `build/gcmu-bg`, on top of 90bbcead. Still do NOT edit `backend/ofo_app/adjustment_check.py`, `playbook_store.py`, `live_market.py`, `paper_monitor.py`, or `feed_bus.py` (another builder adds the background wanted-token key there now as step 4b: `feed_bus.write_background_want(client, user_ref, tokens)`; do not call it yet - it is wired after both merge). Commit there only, never push.

## Do, in order
1. CORE: delete `light_state`. Build a `MarketInputs` (`backend/ofo_app/routes/adjustment.py:94-107`: `chain` rows from the price read's leg quotes, `leg_greeks` from the SHARED figures via `FeedScope.call`, `forward`/`years`/`vol` from the shared forward/expiry model, `now`, `feed`/`last_close` as the read has them, None with its reason otherwise) and a `SpotAnswer`, then call the public `check.state_of(tracked, market, spot, margin, rates, fresh=True, body=watched.body)`. `margin`: the background has no margin read - pass None and say so in the report (the same as a screen whose margin read failed). Measure what `state_of` -> `price_after` computes per strategy (time it in a test on ADJ-02, 100 calls) and confirm it is NOT the full scenario table; the existing "no full table" test must still pass unchanged in meaning. If `price_after` IS the full table, STOP and report the measurement (do not work round it).
2. Public names, no private imports: in `backend/ofo/outcome/service.py` add public `solved_iv` / `unit_greeks` (the private names stay as aliases for their callers); in `backend/ofo_app/routes/adjustment_check.py` add public `sync_records` (same). Nothing imports `_engine_legs` / `_tighten` any more (state_of uses them inside its own module). REPORT both shared-file changes with line ranges.
3. `tests_app/test_background_worker.py:133`: the restart "within 60 s" check uses the injected clock (cycles counted against the clock), never wall time.
4. Tier A mutants first, on a scratch copy (at most 5, each turns a test red): check runs on a stale price; speed read once at start instead of per cycle; valve never steps back; restart re-opens a recorded opportunity; background path calls the full table. Plus the new one: a background state that drops `max_profit` (set it None) - the equality test must go red.
5. Run in full: `tests_app/test_background_worker.py`, `tests_app/test_background_cycle.py`, `tests_app/test_paper_order_door.py`, every test file that imports `service.py`'s IV/Greeks or `_sync_records` (grep), guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `tests/test_reach_check_real.py`, `python scripts/ruff_ratchet.py`. DB files through `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-bg python -m pytest -c pytest-app.ini tests_app/<file>.py -q -rs`, one at a time. Logs to a file, tail only. Memory is tight: no full suites, no npm.

## Standing items
- Answer states for the price read stay as round 1 tested them (fresh, stale, disconnected, no price for one leg, market closed).
- Money exact Decimal (ADR-008). No new duplicated literal; ruff baselines must not rise; no regenerated files.
- Still NOT DONE and stays in the report: Notifier alert part of REQ-115 AC-6; REQ-165 AC-6 (screen reading the worker's latest result).
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-bg.
