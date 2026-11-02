# Goal contract GC-LIVE3: live-market day, Mon 2026-11-02 (09:00-16:30 IST)

Core: the multi-user background role (feed process + background checker) records a playbook opportunity from REAL ticks
with no browser connected, within 1 s (REQ-165, ADR-220 (1)-(3)); its process wiring has never run for real
(`background.py:563` / `feed_main.py` `_serve` are `pragma: no cover`).
Proof (step D3): three separate crossings, each an opportunity row on ofo_dev whose `created_at` is <= 1.0 s after the
Redis stream entry of the tick that crossed the condition, with no app tab open (tab count 0 for the app origin), plus
the background log line for each check. This is step 1 of the day's real work, right after the cold reads.

DATES (do not mix them): TODAY is Monday 2026-11-02. The nearest NIFTY expiry is Tuesday 2026-11-03 (1 day left).
The next NIFTY weekly is 2026-11-09. SENSEX nearest expiry: read it from `/api/catalogue/SENSEX/expiries`, never assume.
Every time written in any record comes from `date` run in the same step.

## Scope and branch

- Run tree: `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch `feature/adjustments`, LOCAL head
  `555e8302` (= origin `d27db73c` + #633 rounds 1-2 + #628 seed check + one finding occurrence, NOT pushed: its gate run
  was killed by the low-memory reaper 08:34). Every fix today is committed on top of it in this tree.
- Never main, never a PR, no push before step C3. Nothing to main without the owner's explicit OK.
- Paper only. No real order, no basket, no Execute press, no click inside any Kite order panel. The 14 real-order PRs
  of #605 stay parked.
- Every browser step in the owner's VISIBLE Chrome (Claude-in-Chrome), never headless. Nothing captured from Kite or
  the reference product goes into the repo (numbers and verdicts may; screenshots stay in `D:\Abhay\scratch\gclive3\`).
- Out of scope: #623, #625, #588, #614 wording fix, #599, #530, #597 (needs an expiry-day close), #613 (parked),
  #605, #634, GC-SET2 (#632), GC-ADJ3, #629.

## Running the stack (the tree has no `.env`: always the MAIN checkout's scripts with the tree as cwd argument)

- `T=D:/Abhay/Ventures/OptionsForOptions2-OptionsForOptions2-settings`, `M=D:/Abhay/Ventures/OptionsForOptions2`.
- Ports first: `Get-NetTCPConnection -State Listen -LocalPort 8765,5174`; refuse a busy port, stop only by PID.
- API (may already be up from the 08:37 start; check the port's PID first, record it):
  `APP_ENV=development LIVE_MARKET=1 python $M/scripts/orchestrator/dev_run.py "$T" python -m uvicorn --factory
  ofo_app.main:create_app --app-dir backend --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port 8765`
  (background, log to `D:\Abhay\scratch\gclive3\api<N>.log`).
- Vite (background, cwd `$T/frontend`): `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174 --strictPort`.
- Instrument list (last load 30 Oct): `python $M/scripts/orchestrator/dev_run.py "$T" python -m ofo_app.catalogue_load`,
  then NIFTY 2026-11-03 and SENSEX nearest contract counts > 0.
- Feed process and background checker (step A1). Checked 08:5x: the background role (`roles.py:22`,
  `python -m ofo_app.background`) opens a `BusSocket` on `feed_mode.redis_url()`, so it needs `REDIS_URL` and the
  market-data process `python -m ofo_app.feed_main`. `.env` has NO `REDIS_URL` / `FEED_MODE` key: set them inline.
  In bus mode the API opens no Kite socket (`feed_mode.py`): A1 RESTARTS the API with `FEED_MODE=bus
  REDIS_URL=redis://127.0.0.1:6379/0` (stop the old API by its port PID first), then starts, each through
  `python $M/scripts/orchestrator/dev_run.py "$T" ...` with the same two variables (Git Bash syntax `VAR=x cmd`; dev_run.py sets PYTHONPATH itself):
  `python -m ofo_app.feed_main` and `python -m ofo_app.background`. Order: feed_main, API, background. If any refuses
  to start (FeedModeRefused, missing variable), read its message, fix the variable, retry once; second refusal = D2-D5
  are PARKED with the message (one fix round only, then E1). Redis is local on 6379 (listening at 08:2x); `redis-cli
  PING` or a Python `redis.Redis().ping()` first.
- A0 and B1 onward run the API in the default `inprocess` mode; A1-D5 run bus mode (feed_main + API + background).
- DB tests: ONE file at a time, throwaway DB only:
  `python $M/scripts/orchestrator/db_run_fresh.py "$T" python -m pytest -c pytest-app.ini tests_app/<file>.py -q`.
- Kite: if `/api/broker/status` is not connected, ask the owner (one line) to log in once in a PRIVATE window at
  `http://127.0.0.1:8765/broker/zerodha/login`. A login made today is valid until 06:00 tomorrow.

## Memory and heavy work (two reaper kills in 2 days: 11-01 run 3, 11-02 08:34)

- Check free memory (`python D:/Abhay/Ventures/OptionsForOptions2-coord/coord.py mem`) at the start of every block.
  Under 3.0 GB: close app tabs not in use, stop Vite if no screen step is next, and do no builder dispatch until above
  3.5 GB. Never stop another session's process.
- No full suite, no `prepush`, no `ci_local` before 15:40. Builders (Sonnet, Budget/Class/Proof lines, targeted tests
  only, output to a log file) only for a fix that blocks a later step.
- If Claude Code kills a job for low memory: free only this session's idle processes, restart it once; killed again =
  tell the owner and continue with light work.

## Steps (times are targets; a step that overruns by 30 min is cut: record what is left and move on)

The order follows "core first" and the independent review of this contract (2026-11-02 08:5x, Sonnet, FIX FIRST, 8
findings, all accepted):
- bus mode from the start, so every step runs in ONE mode;
- the core proof before T3;
- the API restarted just before 09:15, so the cold reads are honest;
- feed and background stopped once D5 is done, because the DB host also serves production.

| # | When | What | Done when (evidence) |
|---|---|---|---|
| A0 | 08:50-09:12 | Preflight: (1) tunnel up: port 5432 listening and owned by `ssh.exe`; if not, start it per the runbook DB section. (2) Redis ping. (3) Owner Kite login: one line asking, private window; then `/api/broker/status` reads live_market_data connected. (4) catalogue_load, then contract counts. (5) Vite up. (6) Free memory. (7) Paper-only check: read how Execute is reached (the `routes/execute.py` route and its UI button), and write in the log that no step below calls it | status lines with times, PIDs, counts; the Execute route path named as "not called" |
| A1 | 09:12-09:15 | Stop the 08:37 inprocess API (by its port PID). Start in bus mode, in this order: `feed_main`, then the API (`FEED_MODE=bus`), then `background` (see "Running the stack"). Keep NO app tab open | 3 PIDs; the feed log shows the Kite socket open; the background log shows its first cycle |
| A2 | 09:15-09:25 | Cold reads, the API's first answers with no app tab open: `GET /api/leg-picker/strikes?underlying=NIFTY&expiry=2026-11-09&width=10`, `POST /api/strategies/leg-edit` (`leg_edit.py:351`), and the ready-made load (`ready_made.py:116`). Does any of them say `state: LIVE` with nothing priced (#615 class)? Then open the builder once: does NIFTY spot arrive (#583 I-6)? | per read: time, state, reason, priced count; #615 and #583 comments |
| D2 | 09:25-09:40 | Two paper strategies at TYPED prices: a NIFTY short iron condor (2026-11-09) and a SENSEX short strangle (nearest SENSEX expiry from the catalogue), each with its active system playbook attached | strategy ids; playbook source and version for each |
| D3 | 09:40-10:30 | CORE PROOF. (1) Close every app tab: tab count 0 for 127.0.0.1:5174. (2) Set the paper iron condor's plan value for one playbook rule just beyond the current live figure, so real prices will cross it. Change plan values only; the rule text stays unchanged. (3) Get three separate crossings: re-arm each time by dismissing the record and moving the value again. (4) Per crossing record T_tick, the Redis stream entry id time of the first tick that crosses (`XRANGE` around the crossing), and T_row, the opportunity row's `created_at` on ofo_dev, read through the app route, not through SQL as owner. (5) Verdict per crossing: T_row - T_tick <= 1.0 s is a pass (REQ-165 / ADR-220 (3)). A value in (1.0, 2.0] s is NOT a pass: record it as a finding against the speed rule, with the numbers (the loop sleeps 1 s per cycle, `background.py:524`). Over 2.0 s, or no row, is a FAIL. All three must pass. (6) Also check that the Redis key of the legs' tokens (step 4c) exists with the right count | 3 rows (id, T_tick, T_row, delta), the key and its count, log lines. FAIL: one fix round (builder, targeted tests). Second fail: independent reviewer, then re-plan. Not proven by 11:30: PARKED with the root cause, continue with B1 |
| D4 | during D3 | Calc speeds (REQ-166), from the background log over 5 minutes: recompute count per minute per option (must be <= 60), the valve level each minute (1 / 2 / 5 s), and every transition with its time | the counter values themselves; a line saying "normal" without numbers is not evidence |
| D5 | 10:30-11:00 | Compare screen on the live paper iron condor: (1) cost cells; (2) liquidity limits on real bid/ask (low OI reads "not known": expected, F-78); (3) Adjustments used; (4) Live Strategies card count; (5) the inbox row. Then check that T-19's named approach equals the Compare's cheapest non-refused approach (#633 on real prices). Then STOP background and feed (by PID) and restart the API in the default inprocess mode for the rest of the day | screenshots (390 px and desktop) in scratch; the T-19 / Compare pair; PIDs stopped |
| B1 | 11:00-11:45 | T3 (ADR-220 (4)) on NIFTY 2026-11-09, ATM ±10. Run NIFTY 2026-11-03 (expires tomorrow, noisy) only if time is left. Capture at the same moment, at most 10 s apart: (1) our `GET /api/market/chain`, with the chain tab open so the answer is `LIVE`, saved as `D:\Abhay\scratch\gclive3\ours-<expiry>-<hhmm>.json`; (2) the reference product's chain page text from the owner's Chrome, saved as `ref-<expiry>-<hhmm>.csv` with columns `strike,side,iv,delta,gamma,theta,vega`. Then run `python D:/Abhay/scratch/t3/t3_compare.py --ours <json> --ref <csv> --api http://127.0.0.1:8765`. 3 rounds, about 2 min apart. If the page text is unreadable: take a screenshot and type ATM ±5 by hand | per round: table, worst gap, verdict; a finding F-nn in `spec/findings.md` with the numbers |
| B2 | after B1 | Take the worst gap seen in at least 2 of 3 rounds. At or under Rs 5 per lot per day: T3 DONE. Over Rs 5: ask the owner (AskUserQuestion with a `Business call:` line and `Spec basis: ADR-220 (4)`), with the real numbers, the likely cause (calendar vs trading day, forward vs spot, time-of-day convention) and the recommended option first. A gap seen in only 1 round is noise: say so | the DONE line, or the question and its answer as a decision row |
| C1 | 11:45-12:30 | #560 REQ-078 AC-1, live half. Build a NIFTY iron condor from real strikes via `POST /api/strategies/leg-edit`. Apply Shift +1, Width +1 and Hedge +1 once each, hand-checked against today's strike list. Hand-check max loss to the paisa. Time 50 edits in a row: p95 must be <= 1,000 ms | `evidence/W-158/AC-1.md` with the numbers and the verdict; #560 closed or commented |
| E1 | 12:30-13:15 | #583 I-1 (does a ready-made shape click answer 422?) and I-12 (does a futures leg make the numbers disappear?). Fix only if it reproduces AND fits in one builder round; otherwise comment with the evidence | a #583 comment per item |
| E2 | 13:15-14:45 | #606 GC-TPL: re-test F-65 to F-69 (`spec/findings.md` lines 969-1012) live on the D2 paper strategies, each against its text. Skip GC-TPL L1: it checks the 29 Oct close and is obsolete | per finding: fixed (date and proof line written in findings.md), or open with today's evidence |
| E3 | 14:45-15:25 | Buffer: fixes for blockers; a live paper leg-stop trigger (shows #614's text live); repeat a noisy T3 round | one line per item |
| E4 | 15:25-15:40 | Close watch: the market-closed banner at 15:30, Paper's text after the close (#616), `GET /api/market/indices` after the close | times and answers; #616 comment |
| C2 | 15:40 | (1) Stop this session's processes by PID. (2) Write and COMMIT the handover, with C3 marked "running", BEFORE C3 starts, so no tracked file changes during C3. (3) Get free memory to >= 4.5 GB by closing Chrome tabs; never stop another session's process | PIDs, commit sha, free GB |
| C3 | 15:45-16:30 | (1) Take the heavy slot: `coord.py take-heavy GC-LIVE3 prepush-full-<sha>`. (2) Run `python scripts/orchestrator/prepush.py --full` ONCE on the final head; watch the PROCESS list, since its log stays empty until the end. (3) TOTAL PASS: `git push origin feature/adjustments`, as its own command. Red: 2 fix rounds per class. Killed by the reaper: restart once if >= 4.5 GB is free; killed again means no push today, and NEXT names it | the pass record and the push line, or the red step / the kill named |
| C4 | last | (1) Amend the handover `docs/process/session-handover-2026-11-02-gclive3.md` with C3's result (DONE / PENDING / BLOCKED / PARKED / NEXT); commit it after the push, or after the failed run. (2) Memory note and coord note. (3) Issue comments: #615, #583, #560, #606, #616, #633, #628. (4) Remove the `-fix633` / `-fix628` worktrees with wt-rm.ps1 only once their branches are on origin (counts printed) | files committed; no process of this session still running |

## Failure budget and stops

- 2 fix rounds per class, then park (issue labelled `parked` with evidence) and move on. A second red of the same class
  -> independent reviewer (fresh context, different model) before round 3.
- Genuine stops only: a credential only the owner holds (Kite login), a business call (B2 gap, anything users see that
  departs from the spec), an irreversible act. Everything technical is decided and recorded.
- Touch no tracked file while `prepush` runs; no `gh_issue.py --stage` then either.
- Findings and defect classes are registered the turn they are proven (`spec/findings.md` F-nn; defect classes in
  `knowledge/findings/`, regenerate the index only via the approved wrapper + `--check`).

## Definition of Done

- [ ] A0-E4 (incl. D2-D5, B1-B2, C1) each DONE, or cut/PARKED with an issue and what is left; T3 DONE or the owner's answer recorded.
- [ ] Core proof (D3) recorded for 3 crossings with T_tick, T_row and the delta, or PARKED with the root cause.
- [ ] Every defect found today: fixed (with test) or an issue with the real numbers.
- [ ] C3: TOTAL PASS on the final head and `feature/adjustments` pushed, or the red step named in the handover.
- [ ] C4 handover + memory note; no process of this session left running.

## Known facts (do not re-discover)

- `/api/broker/status` before login reads `connect_zerodha` (expected). Login route: `/broker/zerodha/login` (302 to Kite).
- `ofo_dev` has the newest tables (0034 answers: `/api/system-playbooks/strangle/versions` -> version 2).
- The app DB role cannot read `alembic_version` (permission denied): check tables through routes, not alembic.
- `GET /api/market/chain` is `LIVE` only while a socket holds the window (#206 rule): keep the chain tab open in B1.
- Chain theta is per calendar day, per unit (`chain_push.py:161`); lot size from `/api/catalogue/NIFTY/contracts`.
- `t3_compare.py` self-test: fake data gives -3.25 and -13.00 Rs/lot/day at lot 65 (hand-checked), rc 3 when over.
- #628: batching already correct since 6a6d8aa3; ADJ-45 now refused by the seed (states 2 adjustments, no history).
- Prepush log stays empty until the end (buffered): watch the process list, not the file.
- Git Bash `$!` is not the Windows PID: find a server's PID by its listening port.
