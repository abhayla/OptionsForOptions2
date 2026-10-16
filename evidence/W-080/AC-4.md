---
work_item: W-080
ac: AC-4
requirement: REQ-073
ac_fp: "acbaab536416"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus/sonnet, worktree agents, rounds 1-10 + integration)"
date: '2026-10-16'
commands: "MSYS_NO_PATHCONV=1 python v2/mut.py <wt> <method> <path> (7 templated mutants); placement_in partial-segment probes; python v2/att.py <wt>; pytest tests/test_no_order_placement.py tests/test_kite_http_guard.py (restore) - at 26eff25, scope per ADR-098"
---

AC: AC-4
result: pass
commands: mutation runs of templated allow-list entries (POST /{variety}/iceberg, PUT /orders/{x}/{y}, DELETE /orders/{seg}/{oid}, POST /{kind}/{name}, POST /orders/{v}, POST /{p}, POST /{s}/{t}/{u}); partial-segment probes; att.py runtime attacks; restore test run
observed: test_allow_list_holds_no_placement_modify_or_cancel_path FAILED for all 7 mutants (check_call admitted POST /orders/iceberg for 3 of them, so the test is what catches them); partial-segment templates (/{x}rders/iceberg, /o{a}s/{b}, /g{x}/triggers, /gt{x}/triggers/{y}, PUT /{x}s/iceberg/{y}) all flagged; att.py: every route REFUSED or KiteCallRefused, only the Proactor default event loop reached the network, which ADR-098 puts out of scope ("native-code event loops"); restore 156 passed, git status clean. Earlier rounds (orchestrator and Tier A reviews, 2026-10-16): un-forged bypasses all refused at runtime; forged code objects are out of scope per ADR-098; Kite itself refuses API order placement from this app (no static IP, ADR-100).
attack: templated and partial-segment allow-list entries with POST, PUT and DELETE; runtime connect/urllib/http.client/httpx/threads/asyncio/multiprocessing to 192.0.2.1. The only template not flagged, /orders{x}, matches no real Kite write path.

Recorded by the orchestrator from the verifier's returned block.
