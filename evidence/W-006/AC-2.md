---
work_item: W-006
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments/test_catalogue.py; python - (attack script on the full real Zerodha list, 110,411 rows); git merge-tree --write-tree origin/main HEAD; trial merge then python -m pytest -q -p no:cacheprovider"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments/test_catalogue.py; python - (attack script on the full real Zerodha list, 110,411 rows); git merge-tree --write-tree origin/main HEAD; trial merge then python -m pytest -q -p no:cacheprovider
observed: 19 passed; 4618 in scope; drop all NIFTY/SENSEX REFUSED; first 25/50% and last 25/50/75% REFUSED; nearest NIFTY expiry roll-off (277 rows, 15.2%) ACCEPTED, 2 nearest (479) ACCEPTED; SENSEX nearest (304) and 2 nearest (600) ACCEPTED; empty REFUSED; force ACCEPTED; entries stay 4618 (never deleted); NIFTY opt lot 65 tick 0.05 gap 50, NIFTY fut tick 0.1, SENSEX lot 20 gap 100; all 44 kind combos consistent; merge clean, 58 passed
attack: dropped each underlying, cut the file at 25/50/75% from both ends, rolled off 1 and 2 nearest expiries per underlying, empty list, force=True: all correct. Residual (deferred): a partial truncation up to 50% of one underlying is accepted by design threshold. Verified after 3 rounds (round 1 verifier: tick_size crash, placeholder provenance, no guard; round 2: guard global; round 3: per-underlying).

Recorded by the orchestrator from the verifier's returned block.
