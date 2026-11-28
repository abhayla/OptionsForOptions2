## D-04 round 2 review (2026-11-24): commits cea53cf, f135690, and test changes 0802084, 38debbf

Reviewer: fresh-context helper, read-only. `pytest -q tests -k "guard or entry_type or adjustment"` 1918 passed.
Verdict: covers the class: no. D-04 PARKED after two rounds (common rules, section 3 step 8).

Findings:
1. MAJOR `backend/ofo_app/background.py:1882`, `routes/adjustment_check.py:442`, `routes/adjustment_plan.py:348`,
   `routes/playbooks.py:482`: these four callers still pass the live spot to `check.entry_type`, while the server limit
   (`paper_limit.py:42`) and now the offer path (`routes/adjustment.py:591`) pass None. `strategy_type` uses spot as the
   reference level and falls back to the middle of the strikes only without it, so a shape near a type boundary can
   read playbook A on the check route and the worker and playbook B (or the current-shape fallback) on the server.
   Same class as the A4 finding. Next step: one shared spot-free entry-type call used by all six callers, plus a test
   that offer, check, worker and server agree for a basket at the plan maximum.
2. No regression for other guards: spot is used only to classify; guards are read from the playbook body.
3. All `read_guards`/`guards_of` call sites are on the new path.
4. Fallback verified on the offer path (same function and arguments as the server). MINOR: the offer's `listed` comes
   from `check.listed_of(ctx)`, the server's from its own argument; same source not confirmed.
5. 0802084 OK: ADR-318 (5); the test's purpose (why text naming both records) is unchanged. The add-refused case must
   be covered elsewhere (it is: `tests_app/test_d04_*` and the paper limit tests).
6. 38debbf OK: REQ-159 AC-6 buys first. MINOR: the expectation copies the production sort; a fixed expected price list
   would be stronger.
