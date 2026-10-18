# Review brief: PR #394 (#381 return route) - Tier A, fresh, adversarial, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first; no suite re-run)
Core: after this PR the return route can never close a plan nothing_placed while Zerodha shows a fill for its tag,
and never closes filled without a trade; nothing else in the route's behaviour changes.
Proof: each finding cites path:line and a command run this turn (gh pr diff 394, targeted pytest on the PR head).
Spec basis: issue #381; REQ-060 AC-6; REQ-058 AC-5; ADR-105; ADR-108 rule 3 (nothing placed while Kite shows a fill is a STOP).
Copy from: none - a review.
Findings checked: state-read-after-await, trust-broker-status-word, fill-not-exactly-once, guard-without-killing-test, test-asserts-implementation-output
Threat model: in scope - the read order of orders vs trades and the new refusal in read_book; out of scope - Kite's own endpoint consistency, other routes.
Why Opus: Tier A - the live return route Monday's real-money run depends on (after GC-3L it merges).
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read: gh pr diff 394 --repo abhayla/OptionsForOptions2; backend/ofo_app/routes/execution_return.py and
backend/ofo_app/return_book.py at the PR head (git fetch origin build/fix-381-257; git show
origin/build/fix-381-257:<path>).
Attacks:
1. Can the new refusal (trade naming an order id absent from orders) fire on a legitimate state and wedge every
   return - e.g. an external (untagged) order's trade, a trade of yesterday's order, an order list paged/truncated by
   Kite? If so, what does the user see and can they get out (finding state-with-no-working-exit)?
2. Reading trades first: can an order fill between the two reads and now be seen as COMPLETE with no trade? Which
   state results, and is it safe (no false filled, no false nothing_placed)?
3. Mutation: confirm the builder's claim that removing the check / swapping the order turns tests red (run them:
   python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py -k 381).
4. Does the edited existing DB test still prove what it proved before?
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: run only the targeted file above)
Report (under 300 words): verdict PASS / REVISE, findings (severity CRITICAL/MAJOR/MINOR, path:line, one-line fix),
covers the class: yes/no, evidence table.
