# Row 9 part B finish: REQ-113 (W-137) - show the capped state, one read for the session expiry, prove every B guard

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; R13-R16).
Size: S, 5 files, 3 items
CI: app job `api` step (`tests_app/test_feed_caps.py`, `tests_app/test_feed_session_expiry.py`,
`tests_app/test_feed_user_isolation.py`, `tests_app/test_bus_socket.py`; vars: TEST_DATABASE_URL,
OFO_REQUIRE_DB_TESTS=1, BROKER_TOKEN_KEY, REDIS_URL) - locally with REDIS_URL at the stand-in (F-58); DB files through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Expected (orchestrator, before dispatch 08:00 IST): 30 min / ~110k (R5: a small follow-up, fresh agent).

Core: a user over Zerodha's cap is told live prices are not available - never a silent gap.
Proof: step 1 is a test in `tests_app/test_bus_socket.py` failing first: the feed's status key says `capped`; the API's
quotes for that user read not live and the feed phase reads `capped` (today the status carries it and nothing reads it).

Spec basis: REQ-113 AC-6: "a subscription beyond the cap is refused and logged, never silently dropped." REQ-113 AC-8:
"At the daily 06:00 session expiry (ADR-053) the process closes that user's sockets". ADR-170 (a 4th connection is
refused and logged, and that user's screens say live prices are not available).
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 9dd50d9b (or later: the
orchestrator may commit briefs with `git commit -- <its paths>`). Commit ONLY your own paths with `git commit -F <msg>
-- <your paths>` as its own call; never `git add -A`, `stash`, `checkout --`, `reset`, `restore`; do NOT push. Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09b-finish`.

## What to do (the part B builder's own open items)
1. Capped is shown: the API side reads the status key's `capped` flag (BusSocket / the provider's feed state, the same
   path as `connected: false`): that user's quotes read not live, `feed_phase` returns a capped word, and the broker
   status page shows it with a plain fix text from the ONE text home (BrokerSettingsPage's `live_feed_*` map gets
   `live_feed_capped`: "Live prices are not available: Zerodha's connection limit for this app is reached." - wording
   per ADR-170). If `feed_phase` words are an allow-list somewhere, extend it there.
2. One read for the session expiry: the part B code reads the expiry in a second query, so a login replacing the
   session between the two reads can leave a user "ended" until their next login. Read the session id, user and expiry
   in ONE query (`broker_token_store.py`), and decide on that row only; a test interleaves a replacing login between
   the old two reads (a fake connection or a DB test) and shows the new session is not ended.
3. Prove every part-B guard: in scratch copies, run these mutants and name the killing test of each: truncate instead
   of refuse (cap), no per-key connection cap, expiry never reached, an ended session reconnects, the per-user task
   isolation removed (one shared task / shared exception handler), Redis down at feed start crashes, no session at
   start exits instead of idling, capped not read (item 1), the two-query race (item 2). Every one red; list them.
Then run the brief's `Tests:` line and `-m repo_scan` in full and report both result lines.

Attack list: (each names its test file)
1. A capped user's quotes are not live and the status page says the capped text (`tests_app/test_bus_socket.py`).
2. A login replacing the session between reads is not marked ended (`tests_app/test_feed_session_expiry.py`).
3. 3001 instruments refused and logged, none dropped (`tests_app/test_feed_caps.py`).
4. A 4th connection refused and logged (`tests_app/test_feed_caps.py`).
5. Killing user A's socket leaves user B's ticks flowing (`tests_app/test_feed_user_isolation.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the token store's answer states for the one expiry read - row present and live, present and expired, absent, replaced mid-check, DB unreachable - each in `tests_app/test_feed_session_expiry.py` with what it does.
Threat model: in scope - a capped user shown nothing or an old price as live, a valid new session marked ended; out of scope - Zerodha changing its caps.
Findings checked: caller-supplied-verdict-trusted, wall-clock-assertion-flakes-under-load
Reviewer checklist: capped read on the same path as connected:false; text from one home; one query decides; every
listed mutant red; full guard line and repo_scan green; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
