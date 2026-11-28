# GC-ICLIVE: cloud session setup (learned in Part A, 24 Nov 2026)

Read this before stage 1 of any part. Every value below is a throwaway CI placeholder taken from
`.github/workflows/app-tests.yml`; no real credential belongs here (public repository).

## 1. Local database (common rules, section 2)

PostgreSQL 16 binaries are installed at `/usr/lib/postgresql/16/bin` (not running on a fresh machine). As root:

1. `initdb` a data directory owned by the `postgres` OS user (Part A used `/var/lib/postgresql/16/ofo`), start it on
   localhost:5432 with `pg_ctl -l <log> -w start`.
2. Create the database `ofo_test`, the role `ofo_app` and the REVOKE/GRANT CONNECT lines exactly as the `api` job of
   `app-tests.yml` does (same passwords, `CONNECTION LIMIT 5`).
3. `pip install -r requirements-app.txt -r requirements-dev.txt` (alembic is in them), then
   `alembic -c backend/ofo_app/alembic.ini upgrade head` (about 45 s).
4. Write `/root/ofo-test-env.sh` exporting every variable the `api` job sets for its test step (the three database
   URLs, `PG*`, `OFO_REQUIRE_DB_TESTS=1`, `REDIS_URL`, the Kite and `BROKER_TOKEN_KEY` placeholders) and an idempotent
   `/root/ofo-db-start.sh`.
5. The shared `ofo_test` keeps state between runs: make a template once
   (`create database ofo_h_tpl template ofo_test`) and run each DB pytest on a fresh clone
   (`create database <tmp> template ofo_h_tpl`, grant connect to `ofo_app`, point the three URLs at it, run, drop it
   `with (force)`). `scripts/orchestrator/db_run_fresh.py` expects a Windows path and does not work here.
6. Redis is not running: `redis-server --daemonize yes` when a test needs it.

## 2. The sandbox proxy

The cloud machine sets `HTTPS_PROXY` and friends; CI has none. The egress-gate tests
(`tests_app/test_egress_gate_doors.py`, `tests_app/test_kite_broker_reader.py`) aim at 192.0.2.1 and expect the app's
own gate to refuse; through the sandbox proxy they get a 502 instead and fail. Run every Python gate (pytest,
`tools/ci_local.py`, `scripts/orchestrator/prepush.py`) with
`env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy`. Measured 24 Nov: 4 failed
with the proxy, 127 passed without. npm and npx keep the proxy (the registry needs it).

## 3. The type checker

`prepush.py`'s interface layer runs mypy over every file. CI installs mypy without a pinned version; the cloud machine
had 2.3.1 and flagged a deliberate positional call that the owner's PC did not (fixed with a targeted
`# type: ignore[call-arg]` in 1af71b2). A new finding on an unchanged file is a version difference first.

## 4. Helpers and hooks

- The `builder` agent type runs in its own worktree based on `main`, not on this branch: it cannot see the branch's
  work. Use `general-purpose` helpers, in the main checkout or in a worktree you create from the branch head.
- While a `reviewer` or `verifier` type helper runs, a hook blocks `git add` and commit in the checkout. Use
  `general-purpose` helpers with a read-only brief for reviews when other work must commit meanwhile.
- A hook blocks `;` before a commit, push or merge: chain gates with `&&`, run the commit as its own call.
- A hook blocks `git reset --hard`; move a helper worktree with `git checkout --detach <branch>` instead.
- The `builder` type's hard turn limit is 100: a brief's `Budget` may ask at most 80 tool calls.
- The money scan (`tests/test_money_outside_engine.py`) flags any arithmetic in frontend files; its allow-list is not
  edited in this chain. Write non-money counters without arithmetic (Part A used a per-read token object, c88b8aa).

## 5. The chain

A session prompt cannot open with `/goal`. Each part runs in its own cloud session from a plain-words launch message
and an hourly scheduled check-in on that session (it continues the part if the session is idle and the part is not
DONE). At DONE the part starts the next part's session and its check-in the same way, then deletes its own check-in.
A hard halt (common rules, section 8) stops the chain: write the reason to the progress log and start nothing.
The tracker link travels only in the launch message, never in the repository.
