# Row 10: REQ-118 Zerodha rate limits for read calls (W-138) - every Kite REST call waits its turn, a 429 cools down

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13-R16).
Size: M, 11 files, 5 items
CI: kit tests job (`tests/broker/test_rate_limit.py` (new), `tests/test_kite_http_guard.py`, `tests/test_egress_gate.py`;
vars: none); app job `api` step (`tests_app/test_kite_reads.py`, `tests_app/test_kite_margin_client.py`,
`tests_app/test_rate_limit_door.py` (new), plus every `tests_app` file importing a changed module (R13); vars:
TEST_DATABASE_URL only) - DB files through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`,
started FIRST in the background with `-o faulthandler_timeout=60` (R16).
Expected (orchestrator, before dispatch): measure 1 min (done) + build 60 min / ~170k + verify 20 min / ~170k +
orchestrator 10 = ~90 min / ~420k.

Core: every Kite REST call passes ONE limiter at the door, and a 429 puts its group into Kite's 10 s cooldown.
Proof: step 1 is `tests_app/test_rate_limit_door.py` failing first: a loopback fake Kite server (test mode allows a
loopback Kite URL, `kite_http.py:88-91`) answers the REAL door (`ofo/broker/kite_http.py` urllib path AND
`ofo_app/kite_http.py` httpx path): (a) 5 quote reads issued at once reach the server no faster than 1 per second; (b)
a 429 on a positions read -> nothing is sent to that group for 10 s, then the read is retried, at most twice, then it
fails as busy. No recorded Kite 429 exists (Measure: none in `tests/fixtures`); the reply shape is Kite's documented
status code (F-60), so this proves our handling, not Kite's body - say so in the test docstring.

Spec basis: REQ-118 AC-1: "The limits per endpoint group (quotes, historical, margins, orders and triggers, reads) are
configuration with the Zerodha source and date". REQ-118 AC-3: "is refused at once with "Zerodha is busy - try again in a
moment", never queued without bound." REQ-118 AC-4: "is retried after the wait Kite indicates, at most twice". F-60
(Kite: quote 1 req/s, historical 3 req/s, all other endpoints 10 req/s; a 429 starts a 10 s sliding cooldown; scope of
the read limits unstated). ADR-017 (verify Kite's limits at build; no automatic order retry), ADR-094 (margin gate fails
closed).
Copy from: legacy-reuse map row `market_data/rate_limiter.py` (COPY; the map's note: set Kite limits, the legacy had 3
req/s, verify against Kite's docs) - adapt its bucket, set the limits from F-60, never from the legacy values.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (head = after row 9 closes;
`git log --oneline -3` first). Commit with `git add <paths>` (never `-A`); do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row10`.

## What to build (orchestrator decisions, technical, recorded)
1. ONE limiter (`backend/ofo/broker/rate_limit.py`, standard library): a bucket per endpoint GROUP, groups an
   allow-list - `quote`, `historical`, `other` (orders and triggers are not built: no group, and a call that would need
   one is refused). Limits in ONE registry with source URL and date (extend `order_limits_registry.py`, F-60 values:
   quote 1/s, historical 3/s, other 10/s). Scope: the stricter reading, ONE bucket per group for the whole app (F-60:
   Zerodha does not say per user), keyed by api key. Injected clock; never `time.sleep` in tests.
2. The door applies it (structural, run-discipline C8): BOTH door modules (`ofo/broker/kite_http.py` `open_url` ~:164
   and `ofo_app/kite_http.py` doors ~:257, :317) take a slot from the limiter before the socket call, mapping each
   allowed path in `kite_endpoints.py` to its group (an allow-list map; an unmapped path refuses). Callers (R15, each
   named in your report and covered): `kite_reads.py:208`, `kite_margin.py:117`, `kite_history.py:33`,
   `ofo/instruments/downloader.py:22`, `kite_client.py:76`. The repo test (AC-2) proves every door entry point calls the
   limiter (fail closed on a door it cannot resolve).
3. Bounded wait (AC-3): a USER action (quotes, margin, positions/orders reads behind a route) waits at most 5 s for a
   slot, else it is refused at once with "Zerodha is busy - try again in a moment" (the text in ONE home, the errors
   templates); a BACKGROUND job (catalogue load, history finalize, the positions read after a reconnect) waits up to
   30 s. The queue is bounded (a fixed number of waiters per group; more are refused busy).
4. 429 (AC-4, F-60): the group enters a 10 s cooldown during which NOTHING is sent to it (so the sliding window is not
   extended); a READ is retried after the cooldown, at most twice, then fails as busy and the caller's fail-closed rule
   applies (the margin gate blocks, ADR-094); a user action whose remaining 5 s cannot cover the cooldown is refused
   busy at once (AC-3 wins for user actions). A call that CREATES something at Zerodha is never retried - today that is
   `POST /session/token` (`kite_client.py:76`): a 429 or timeout there fails at once (AC-5's rule on the one write that
   exists; trigger writes are not built: deferred).
5. Counting and alert (AC-6): 429s counted per group and user (logged by group, user ref and count - never a token);
   three or more in one minute for the app raise ONE alert through a Notifier client behind an adapter (ADR-029):
   `POST {NOTIFIER_URL}/notify {project, severity, title, body, type, dedupeKey}` (shared Notifier gateway; URL and key
   from the environment, never in the repo); tests use a fake; with no `NOTIFIER_URL` the alert is logged as not sent
   (an alert failure never blocks a read).

Attack list: (each names its test file)
1. 5 quote reads at once reach the fake server no faster than 1/s; 10 "other" reads no faster than 10/s
   (`tests_app/test_rate_limit_door.py`).
2. A user action that would wait > 5 s is refused at once with the busy text; the waiting queue never grows past its
   bound (`tests/broker/test_rate_limit.py`).
3. A 429 -> nothing sent to that group for 10 s; retried at most twice; then busy; the margin gate then blocks
   (`tests_app/test_rate_limit_door.py`, `tests_app/test_kite_margin_client.py`).
4. A 429 or timeout on `POST /session/token` is never retried (`tests_app/test_rate_limit_door.py`).
5. A door entry point that skips the limiter fails the repo test; an unmapped Kite path is refused
   (`tests/test_kite_http_guard.py`).
6. Both door modules share ONE bucket per group: 1 quote via urllib + 1 via httpx in the same second -> the second waits
   (`tests_app/test_rate_limit_door.py`).
7. The third 429 in a minute raises exactly one alert; a fourth in the same minute raises none; no token in any log or
   alert body (`tests/broker/test_rate_limit.py`).

Standing items: (a) background jobs (catalogue load, history finalize) get their own bounded wait and never take a user action's slot ahead of it - a test shows a user quote read still gets a slot while a background burst is queued; (b) n/a: no CI step changes; (c) the door-coverage repo test fails closed on a door it cannot resolve and names the limiter by import source, not by identifier text; (d) Kite's answer states for a limited call - 200, 429, other 4xx, 5xx, timeout, connection refused, malformed body - each listed in `tests_app/test_rate_limit_door.py` with what it does (only 429 starts a cooldown; only reads retry; timeouts never retry a write).
Threat model: in scope - a call that skips the limiter, a burst that breaches Kite's limit, a retry that extends the cooldown, a retried write, an unbounded queue, a token in a log or alert; out of scope - Kite changing its limits without notice (the registry's date says when they were read).
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted, wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later
Reviewer checklist: one limiter, one registry with source + date; the door applies it in both modules; group map an
allow-list; fake clock; every caller named and tested (R15); each guard deleted in a scratch copy has a killing test;
busy text from one home; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise;
targeted tests only; no regenerated files in the PR (a changed API reply model regenerates `docs/api/openapi.json`).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
