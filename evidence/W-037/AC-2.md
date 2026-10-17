---
work_item: W-037
ac: AC-2
requirement: REQ-060
ac_fp: "d4b747da20aa"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "same pytest run; scratch attack.py and attack2.py on tests/fixtures/kite_replies/positions-151006.json, positions-122104.json, instruments-2026-10-16-slice.json"
---

AC: AC-2
result: fail
commands: same pytest run; scratch attack.py and attack2.py on tests/fixtures/kite_replies/positions-151006.json, positions-122104.json, instruments-2026-10-16-slice.json
observed: Domain compare(): flat row dropped (0 mismatches); a position in no strategy is an unexpected broker position blocking no one; a 10-27 leg vs broker 10-19 is an expiry mismatch; an expired leg is awaiting_settlement (ADR-083). Live er.reconcile returns only missing_platform_position, side_mismatch, quantity_mismatch: no strike/expiry kind, no unexpected-position kind for contracts the strategy did not trade, no expiry input, so an expired held leg gone at Zerodha blocks as recon_missing_platform_position (contradicts ADR-083).
attack: real flat row after the exit (qty 0, unrealised -130): both paths 0 mismatches, exit clean; a non-flat row not in the instrument index (INFY CNC 5) refuses the whole read (fails closed); expired leg: domain awaiting_settlement, live path a blocking missing

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
