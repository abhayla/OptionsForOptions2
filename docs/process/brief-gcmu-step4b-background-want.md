# Brief: GC-MU step 4b - the background role's own wanted-token snapshot, merged with the API's by the feed

Core: with NO API snapshot present (no screen open), tokens written by the background role reach the feed's wanted set, so the feed subscribes them.
Proof: step 1 of this brief - a feed_bus test with a fake Redis: only `write_background_want(client, "ua", [101, 102])` written, `refresh_want` -> the relay's wanted set is {101, 102}.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Class: defect found in step 4 round 1 - the feed's wanted set is ONE key per user (`ofo:feed:<user>:want`, `backend/ofo_app/feed_bus.py:7-8, :82, :472-479`) written only by the API process, so a strategy with no open screen never gets a price and the background role (REQ-165) can never check it in real use. Population: every tracked strategy whose legs no open screen wants; before: all of them unpriced; after: all of them subscribed.
Proof (class): the fake-Redis tests below on the real `refresh_want`; no live run (market closed on Sunday).
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Sensibull: n/a - server feed plumbing, no screen.
Reference: none - searched wanted tokens, feed subscription (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - the bus was built new in REQ-113.
Tier: B (Sonnet diff review); the Tier A verifier of step 4 reads it too.

## Where
New worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-want`, branch `build/gcmu-want` (from `build/gcmu`). Change ONLY `backend/ofo_app/feed_bus.py` and new tests. Do not touch `backend/ofo_app/background.py` (another builder edits it now) or `feed_main.py`. Commit there only, never push.

## Do, in order
1. CORE: in `feed_bus.py` add `background_want_key(user_ref)` = `want_key(user_ref) + ":bg"` and `async def write_background_want(client, user_ref, tokens: list[int]) -> None` writing `encode_want(user_ref, tokens)` with `px=WANT_TTL_MS` (same snapshot + expiry rule as the API's). `refresh_want` reads BOTH keys in one round trip (`mget`) and applies the UNION.
2. Answer states, each one test: only the API key; only the background key; both (union); one key expired / absent (the other still applies); one key malformed or another user's (that key counts as nothing wanted, the other still applies - never drops the good one); Redis not answering (last wishes kept, `redis_failed` counted - unchanged behaviour); union above `MAX_WANTED_TOKENS` (refused the same way one snapshot is today - read `decode_want` and keep its rule).
3. Run: the new test file and every existing feed_bus / feed test file that imports `refresh_want` or `apply_want` (grep), through `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py <worktree> python -m pytest -c pytest-app.ini tests_app/<file>.py -q -rs` one file at a time when they need the DB, plain pytest when they do not; `python scripts/ruff_ratchet.py`; ruff on changed files; guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`. Logs to a file, tail only.

## Standing items
- One read path: the union is built inside `refresh_want` -> `apply_want`, never a second subscription path.
- Tests that import `ofo_app` go under `tests_app/`. No new duplicated literal; no regenerated files.
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-want.
