---
work_item: W-067
ac: AC-4
requirement: REQ-051
ac_fp: "c10fbfcc1676"
result: pass
verified_by: "verifier (opus, fresh context, 2026-10-10: AC-3 at 90633d0, AC-4/AC-5 re-check at 1dd86dc)"
builder: "builder (sonnet; rounds 1-3, 2026-10-10)"
date: '2026-10-10'
commands: "(verifier 2, at 1dd86dc) git -C <wt> diff 90633d0 HEAD --stat; python -m pytest -q -rs -p no:cacheprovider tests/history/test_finalize_keeps_live.py tests/history/test_recorder_queue.py tests/test_no_wall_clock_asserts.py; OFO_HISTORY_SCALE_INSTRUMENTS=40 python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_finalize_job.py tests_app/test_history_finalize_start.py tests_app/test_history_finalize_scale.py tests_app/test_history_nonblocking.py --durations=8; python tools/ac_fp.py REQ-051 AC-4 --yaml; (verifier 1) gh run view 38023353316 --log"
---

AC: AC-4
result: pass
commands: (verifier 2, at 1dd86dc) git -C <wt> diff 90633d0 HEAD --stat; python -m pytest -q -rs -p no:cacheprovider tests/history/test_finalize_keeps_live.py tests/history/test_recorder_queue.py tests/test_no_wall_clock_asserts.py; OFO_HISTORY_SCALE_INSTRUMENTS=40 python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_finalize_job.py tests_app/test_history_finalize_start.py tests_app/test_history_finalize_scale.py tests_app/test_history_nonblocking.py --durations=8; python tools/ac_fp.py REQ-051 AC-4 --yaml; (verifier 1) gh run view 38023353316 --log
observed: Head 1dd86dc; diff vs 90633d0 only work/W-067.md. All 4 AC-4 files exist. Domain 13 passed; app 10 passed, 0 skipped; SCALE instruments=40 bars=15000 total=3.3s. CI full size (verifier 1): SCALE instruments=1603 bars=601125 total=46.8s batches=33 per_batch_max=1.64s (bounds 600 s / 45 s). Behaviour: a minute without a Kite candle keeps the LIVE bar and the day is FINAL (ADR-067); an empty Kite answer is FINAL; a fetch error stays PROVISIONAL with errors={'fetch_failed': 1}; refused before 16:00 IST with 0 Kite calls; every compared minute equals Kite's candle (source kite/backfilled, 15:09 gap from Kite for all 8); PostgreSQL bars equal the in-memory store's; second run counts None, xmin unchanged, no Kite call.
attack: Boundary times 15:59:59 / 16:00 refused then final; fetch error provisional and named; empty Kite answer final with live bars kept; second run no rewrite (xmin); partial-failure resume leaves first-run row versions untouched. Verifier 1 mutations M1 (day-level refusal for an uncovered instrument), M2 (drop the live bar), M4 (start 15:30), M5 (writer on the feed thread) each turned tests red; code unchanged since.

Recorded by the orchestrator from the verifier's returned block.
