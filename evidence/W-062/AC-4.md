---
work_item: W-062
ac: AC-4
requirement: REQ-051
ac_fp: "c10fbfcc1676"
result: pass
verified_by: "verifier (sonnet, fresh context, round 4)"
builder: "builder (sonnet, rounds 1-4)"
date: '2026-10-08'
commands: "python -m pytest -q -p no:cacheprovider tests/history; python -c store script; grep of backend/ofo/history for gap comparisons"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/history; python -c store script; grep of backend/ofo/history for gap comparisons
observed: Every minute-vs-gap test goes through minute_in_gap (store._in_gap, finalize.in_gap); candles in a gap -> BACKFILLED, others KITE; never lowered; FINAL day frozen across the 4 write methods plus a status revert (refused_final=4)
attack: The round-3 failure (gap clipped to end 15:30:00 dropping the 15:30 LIVE bar) now keeps the bar; no comparison bypasses minute_in_gap. Rounds 1-3 failures (finalize ignoring gaps; replace_day_bars writing LIVE into a gap; LIVE over KITE; late gap on a FINAL day; overnight gap) re-attacked and held.

Recorded by the orchestrator from the verifier's returned block.
