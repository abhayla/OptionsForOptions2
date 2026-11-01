# Brief: GC-MU close - make the full gate green on build/gcmu (8 repo-wide findings)

Core: every one of the 8 repo-wide checks that `prepush.py --full` found red on build/gcmu 4d57ac29 passes for the right reason, and the order-path guard is never weakened.
Proof: step 1 of this brief - `tests_app/test_order_closure_all_routes.py` green with the Compare route's chain to the order modules broken (or pinned with a reason the mutation test still enforces), and the health->execute_plan mutation still refused.
Budget: 75 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 350 words), then the next command to run
Round: 1/2
Class: repo-wide scans the per-item builders never ran (each ran its own files): import-graph allow-lists, a generated OpenAPI file, coverage staging and artifact lint. Population: the 8 items below; before: 4 gate steps red (ci_checks, domain_tests 3, app_tests 5, coverage 7); after: TOTAL PASS.
Proof (class): the exact failing tests below green on the merged head, plus every mutation test in those files still red when its guard is removed.
Findings checked: staleness-by-last-change-age, dependent-tests-not-run-stale-later
Threat model: in scope - any route or worker reaching order code (ADR-002, REQ-115 AC-2); a stored contract reaching a feed key without `resolve`; an allow-list widened without a reason. Out of scope - the settings store (GC-SET), CI workflows, anything on main.
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Sensibull: n/a - repo guards, no screen.
Reference: none - searched order closure, allow-list (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - fixes this repo's own guards and modules.
Tier: A (order-path guard; the orchestrator re-runs the mutation tests and the gate).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-gatefix`, branch `build/gcmu-gatefix` (from build/gcmu 4d57ac29). Commit there only, never push. Do not edit `adjustment_check.py`, `playbook_store.py`, `live_market.py`, `paper_monitor.py` (another session edits them). `frontend/node_modules` is a junction: never delete it.

## The 8 items (gate logs: `C:\Users\itsab\AppData\Local\Temp\prepush-gxh104k_\*.log`)
1. ORDER CLOSURE (do first): `tests_app/test_order_closure_all_routes.py::test_ac6_every_route_reaches_order_code_only_through_the_shared_paths_and_its_pinned_edges` and `::test_ac6_mutation_health_importing_execute_plan_is_refused_with_its_chain`. New chain: `ofo_app.routes.adjustment -> ofo_app.adjustment_readers -> ofo_app.adjustment_check -> ofo_app.playbook_store -> ofo_app.strategy_store -> ofo_app.execute_plan` (and `-> execution_plan_store`), from GC-MU A1's `read_guards` (`backend/ofo_app/adjustment_readers.py:133-145`, a function-local import of `adjustment_check`). Prefer BREAKING the edge (e.g. read the guards through a small reader that does not import adjustment_check, or pass the resolved playbook body in from a caller that is already allowed). Only if that is impossible without editing the read-only files: add a pinned edge with a one-line reason in the test's existing pin list, and prove the mutation test still refuses health->execute_plan. Never broaden a wildcard.
2. `tests/marketdata/test_scale_classes.py::test_only_the_allow_listed_files_name_the_shared_cache`: add `backend/ofo_app/background.py` to the allow-list with its reason (ADR-220 (1) background role reads per-option figures once through FeedScope, REQ-050 AC-3).
3. `tests/marketdata/test_pipeline_stages.py::test_only_named_modules_import_the_concrete_provider_the_fanout_and_the_quote_store`: `ofo_app.background` imports `ofo.marketdata.feed_health`. Go via what the test names (FanOut) if it fits; else add the module with a reason.
4. `tests_app/test_strategy_tracking_imports.py::test_app_wide_a_stored_contract_reaches_a_feed_key_only_through_resolve`: `backend/ofo_app/background.py:508` imports `catalogue_store`, `feed_mode` (step 4c token lookup). Route the token lookup through the sanctioned `resolve` path the test names (read the test); no allow-list entry for this one.
5. `tests_app/test_liveprices_role.py::test_the_five_roles_of_adr_220_are_named_with_their_start_modules`: the test pins `background: None`; step 4 now ships `ofo_app.background`. Update the pin.
6. `tests/orchestrator/test_select_app_tests.py::test_pr241_diff_selects_both_red_files_within_the_cap`: `tests_app/test_adjustment_opportunities.py` is now also selected. Find why (which changed import made the selector pick it) and decide: if the selection is correct, update the expected set with a comment; if the cap is now exceeded, report.
7. `tests_app/test_openapi_drift.py::test_committed_openapi_matches_the_app`: run `python scripts/generate_openapi.py`, review the diff (only A2/A3 reply fields and the inbox expected), commit.
8. Coverage and artifact lint: stage ADR-230, ADR-231, ADR-232, F-77, F-78, F-79, F-90 in `docs/process/coverage-stages.yaml` the way neighbouring rows are staged (read the file; GC-MU rows go to S6.4); `spec/requirements/REQ-167.md` `layer: 'platform'` -> one of core/foundation/feature/polish (`foundation`: the settings store is a base other features read), `REQ-168.md` `risk: 'medium'` -> `normal`. Report these two spec-file edits (another session owns those requirements).

## Run
Each failing test file above (DB files through `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-gatefix python -m pytest -c pytest-app.ini tests_app/<file>.py -q -rs`; non-DB `tests_app` files run with plain `python -m pytest -c pytest-app.ini`), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `python tools/coverage_check.py .` or the command the coverage log names, `python scripts/ruff_ratchet.py`. NOT `ci_local.py` and NOT the full suites (memory). Logs to a file, tail only.

## Standing items
- Every allow-list entry carries a reason line; no wildcard; each mutation test in a touched file still red when its guard is removed.
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-gatefix.
