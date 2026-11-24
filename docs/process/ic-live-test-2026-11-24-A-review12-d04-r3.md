## D-04 round 3 review (2026-11-24): commits 50d875b, 619dfd9, ba2c825

Owner direction 24 Nov ("take your call"): one more round beyond the two-round rule (see review 11 header). Reviewer:
fresh-context helper, read-only. `tests/test_spot_clock_scan.py` 19 passed; `pytest tests -k "guard or entry_type or
adjustment"` 1918 passed. All 8 `entry_type` call sites now pass exactly (tracked, listed); no spot-taking caller
remains in backend/.

Findings and the orchestrator's classification:
1. `routes/tracking.py:437-447` `_playbook_type` and `routes/outcome.py:974` call `type_of(legs, live_spot, gap)`.
   Classified NOT the D-04 class: tracking's call only decides whether the strategy has a playbook, so the generic
   0.5% detection is hidden (F-71 / GC-ADJ2 1C); it sets no plan maximum and no rules (ADR-318 point 4). outcome's call
   classifies a planned, not yet entered trade, where the current shape is the entry shape. Deferred MINOR: after a
   reduce, tracking reads the current shape for that hide decision.
2. MINOR `adjustment_plan.py:344-348`: the `judge_spot` read is now unused as data and kept only for the spot-clock
   gate (gate edits are out of scope in this run); it was read there before this round too, so the route's failure
   modes are unchanged. Deferred: drop the scan's plan-route entry and then the read (owner decision).
3. MINOR `adjustment_check.py:157-166`: classification without spot uses the strike midpoint, with a gap probe when that
   fails; this is the stated D-04 intent and is pinned by tests.
4. MINOR tests: the check route and the worker are covered by an AST arity test, not behaviourally.

Covers the D-04 class (every path reads the plan maximum and rules from the entry shape the same way): yes.
