# Brief: GC-IC1 fix - REQ-155 / REQ-165: live spot refused as a future tick on the adjustment routes (2nd occurrence of freshness-judged-on-request-start-clock)

Core: the one spot-reading rule (`backend/ofo/marketdata/spot_source.py` `_time_problem` / `_feed_age_problem`) accepts a reading stamped up to 2 s after the caller's clock (the skew window PR #427 chose), so every caller, not one route, stops refusing a fresh quote as "tick_in_future".
Proof: step 1 of this brief - a failing unit test first: a REST reading stamped 1.0 s after `now` resolves to that spot (today: REASON_FUTURE); 2.5 s after `now` is still refused. Then, after merge, the orchestrator re-runs POST /api/strategies/82/adjustment-approaches on the live app (today at 10:57 three calls in a row answered spot None with reasons absent / tick_in_future / absent while GET /api/market/indices served NIFTY 23,658.75 at 10:57:56).
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: freshness-judged-on-request-start-clock, check-clock-read-once-per-batch, staleness-by-last-change-age
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - a fix in one route only (the class recurs in the next route; this is the 2nd occurrence); a skew window so wide that a genuinely wrong timestamp (hours ahead, a time-zone error) is accepted; the feed's stale window changed by accident. Out of scope - the feed subscription of the index (the feed source answered absent: separate, not this fix), the screen clock.
Sensibull: n/a - server-side freshness rule.
Reference: none - searched tick in future, clock skew, spot freshness
Copy from: PR #427's rule (freshness judged with a -2 s skew to 60 s window) - reuse its window value, do not invent another.
Tier: B (one rule, unit-tested; the orchestrator re-runs the live proof).
Size: S, about 3 files, 1 item
CI: the backend unit job runs `tests/marketdata/` (or wherever spot_source's tests live: grep); no DB; vars: none

## Defect-fix contract
- RCA: `spot_source._time_problem` refuses any stated reading with `at > now` (zero tolerance), and the adjustment routes read `now` before the REST quote returns, so a quote stamped in the same second as (or just after) the request start is always "in the future".
- Class: every caller of `spot_source.resolve_spot` (the adjustment approaches and check routes, the background worker, the scenario routes: grep `resolve_spot`) x every source with a stated time (feed, rest_quote). Before: refused whenever the quote's stamp is after the caller's clock. After: accepted within 2 s skew; refused beyond.
- Failing test first (above).
- Fix at class level: one named constant for the skew window in spot_source (reuse PR #427's value: grep the execute gate for it and share ONE constant if it lives elsewhere), applied in `_time_problem` and `_feed_age_problem`.
- Proof: the unit tests plus the live re-run by the orchestrator.
- Detection: update knowledge/findings/freshness-judged-on-request-start-clock.json: occurrences += the 2026-11-03 adjustment-approaches case (strategy 82), detection checks += the new spot_source test, note: the rule now lives in the shared spot reader.

## Where
`git switch -c build/gcic1-spot-skew <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). No DB tests needed.

## Do, in order
1. Failing tests (1.0 s ahead accepted; 2.5 s ahead refused; a reading stamped 5 h 30 min ahead, the time-zone error shape, refused).
2. The fix with one shared constant.
3. The finding update above.
4. Run the spot_source test file, `python -m pytest -q tests/adjustment` (log to file, tail), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states: stated + fresh / stated + up to 2 s ahead / stated + over 2 s ahead / no time / naive time / stale (feed) / not finite; each tested.
- B8: the protection lives in the shared reader every caller passes through, not in a route.
- ruff / mypy baselines must not rise; no regenerated aggregates (the findings INDEX is regenerated later in a batch).
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-spot-skew.

Attack list:
1. Window applied only to rest_quote, not to the feed: test both.
2. A 5.5 h future stamp accepted: must be refused.
3. A feed reading stamped 1 s ahead counted as negative age that bypasses the stale check: test the stale rule still applies to old readings.
4. Two different skew constants (execute gate vs spot_source): grep; one constant.
5. Mutants (scratch copy, at most 5): window 0; window unbounded; window only for rest; stale check removed; window as minutes not seconds. Each turns a test red; report mutant -> test name.
