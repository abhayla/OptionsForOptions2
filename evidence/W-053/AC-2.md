---
work_item: W-053
ac: AC-2
requirement: REQ-053
ac_fp: "834f1e9cc934"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "gh run view 36982261090 --log; gh run view 36981310576 --log; git diff 4f0101f 4044a52 -- tests_app/test_catalogue_store.py backend/ofo_app/catalogue_store.py; git show 4044a52:tests_app/test_catalogue_store.py; git show 4044a52:backend/ofo_app/models.py; grep W-053 PROOF on both logs; Read REQ-053.md"
---

AC: AC-2
result: pass
commands: as above (tests read from CI logs and source; no local PostgreSQL; ac_fp supplied by the orchestrator because the kit guard blocks the verifier's tools/ run)
observed: CI run 36982261090 (final commit 4044a52) "219 passed in 11.54s". (1) Real-file proof (network test, unchanged between 4f0101f and 4044a52): "file rows=107237 in_scope=4970 table=4970"; per-type counts NIFTY/NFO CE 951=951, PE 967=967, FUT 3=3, SENSEX/BFO CE 1523=1523, PE 1523=1523, FUT 3=3; 5 named contracts equal field by field with Decimal strike/tick (e.g. NIFTY26O0620050CE strike 20050.00 tick 0.0500 lot 65 expiry 2026-10-06). (2) Expired roll-off keeps all 22 rows, 4 unlisted, first_seen_at unchanged; app role DELETE/TRUNCATE/UPDATE/INSERT -> "permission denied for table catalogue_contracts"; owner delete refused by the trigger (test asserts the catalogue SQLSTATE). (3) Q244: "refused removing NIFTY26O0620050CE (expiry 2026-10-06); rows before=4970 after=4970 identical=True". (4) Q257: "revise NIFTY26OCTFUT lot_size row=75 history=[(12468226,'NFO','lot_size','65','75', <db time>)]" with changed_at between two database clock reads; strike and instrument_type changes refused, rows identical, history=0. (5) No eligibility column; currently_listed is presence in Zerodha's list only. (6) App role INSERT/UPDATE/DELETE on catalogue_term_changes -> permission denied; owner UPDATE/DELETE refused by trigger "term-change history is append-only".
attack: Final-commit audit fix did not weaken the proof (real-file test untouched, PROOF lines identical in substance). History forgery: no app grants, owner blocked by triggers, mutation test present, rewrite rules refused by the allowlist. Float leakage: Numeric(12,2)/(10,4), Decimal asserted. Strike revision refused as identity; lot revision accepted with history. Gaps, not failing: the owner-delete refusal has no separate log line (relies on the test assertion and 219 passed); ac_fp not re-derived by the verifier.

Recorded by the orchestrator from the verifier's returned block.
