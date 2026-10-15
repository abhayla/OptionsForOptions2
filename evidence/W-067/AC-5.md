---
work_item: W-067
ac: AC-5
requirement: REQ-051
ac_fp: "1784bfe153f0"
result: pass
verified_by: "verifier (opus, fresh context, 2026-10-10: AC-3 at 90633d0, AC-4/AC-5 re-check at 1dd86dc)"
builder: "builder (sonnet; rounds 1-3, 2026-10-10)"
date: '2026-10-10'
commands: "(verifier 2, at 1dd86dc) python -m pytest -q -rs -p no:cacheprovider tests/history/test_finalize_keeps_live.py tests/history/test_recorder_queue.py tests/test_no_wall_clock_asserts.py; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_nonblocking.py ...; in-memory mutation patching Recorder.on_quote to drain(2); python tools/ac_fp.py REQ-051 AC-5 --yaml"
---

AC: AC-5
result: pass
commands: (verifier 2, at 1dd86dc) python -m pytest -q -rs -p no:cacheprovider tests/history/test_finalize_keeps_live.py tests/history/test_recorder_queue.py tests/test_no_wall_clock_asserts.py; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_nonblocking.py ...; in-memory mutation patching Recorder.on_quote to drain(2); python tools/ac_fp.py REQ-051 AC-5 --yaml
observed: test_recorder_queue 6 passed; test_history_nonblocking [advisory-lock] and [table-lock] passed, 0 skipped. Carrying assertions: the feed finishes on its own thread while the store stays blocked (liveness, 60 s limit); every store call ran on 'ofo-history-writer'; after release drain() True, bars_lost == 0, 7 bars in order; with an owner-session advisory lock held, errors == 0 and afterwards PostgreSQL bars == in-memory bars, gaps equal, bars_lost == 0; a full queue drops bars into recorded gaps for the Kite backfill.
attack: Mutation: the feed thread waits on the writer (drain(2) inside on_quote) -> test_a_store_that_blocks_never_blocks_the_feed_thread FAILED in 60.81 s (liveness). Risk noted, not failing: tests_app/test_history_nonblocking.py also asserts max(spans) < 0.1 s (a wall-clock bound); the wall-clock guard does not scan tests_app - deferred as an issue.

Recorded by the orchestrator from the verifier's returned block.
