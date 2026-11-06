# Session handover 2026-11-06 16:48 IST: iron condor end-to-end test (live + test data)

Owner goal (verbatim intent): one full round of end-to-end testing of every option, scenario and screen of the iron
condor as an expert IC trader, paper only; fix only what needs live market data, document the rest; do NOT treat
testing as complete until the round is done. Then the owner does a manual test.

## Standing owner instructions from this session
- Paper only; no real order (real orders = a separate planned round later, owner funds the account first).
- DEVELOPMENT ON HOLD (owner ~14:2x): only update requirements and issues; fix only issues that need live market data;
  no new builds until the owner says "start development".
- Strategy / behaviour questions: decide with my recommendation, write a decision row, tell as information (owner
  14:4x "Why are you asking me? You should go with your recommendation"). Ask only business forks (spend, real orders,
  prod host, legal).
- Everything configurable (ADR-264): behaviours + numbers are settings (admin default, user override, admin lock).
- Test-data first, then live, for T-11 / T-14 and all their related functions (ADR-270).

## The one file to read first
`D:\Abhay\scratch\ic-uitest\ISSUES.md` - 69 numbered issues (state, needs-market, decision), plus every verified
result (live and test data) with numbers. Backups of the 29 deleted IC strategies: `D:\Abhay\scratch\ic-uitest\backup-<id>.json`
(soft-deleted incl. 82 by owner choice; undelete = POST /strategies/{id}/undelete).

## Code and branch state
- Run tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch `feature/adjustments`, head
  087bb25b, NOT pushed (origin is 42924b7b). Merged today (each verified by my own test runs): e34bd754 + 228b95a9
  (strike steps add up, leg-edit DB trips), f56f7a7e (safe paper dialogs, live-price entry prefill), b973d36e (compare
  full-exit prepare, client prop), e63690ce (A-01 OTM delta picks, compare 30 s timeout), b45ecf7a (prepared approach
  opens its strategy's Drafts Mode). Then spec-only commits ADR-255..270 + REQ-077 AC-5.
- Live tree `D:\Abhay\Ventures\OptionsForOptions2-live` at 514113f1 (code as served on 8765; later commits are spec only).
- Main untouched (4119c8c5). Nothing to main without the owner's explicit OK.
- One gate (`prepush --full`) + one push of feature/adjustments is owed at the end of the round. Note issue 69:
  tests_app/test_day_rules_worker.py fails (2) on 42924b7b too, so last night's gate did not run or catch it.

## What runs on this PC now (stop only by recorded PID, never by name/command line - incident 67)
- Redis5 `127.0.0.1:6380` (pid 1608), liveprices (pid 20852), background (pid 1996), API 8765 (pid 4580;
  FEED_MODE=bus, LIVE_MARKET=1, DB_POOL_SIZE=4), vite 5173 (settings tree, OFO_API_TARGET=8765), vite 5174 (-> 8766).
- Scenario test copy on 8766 is STOPPED. Restart: `D:\Abhay\scratch\ic-uitest\restart_scn.ps1 -PathId PATH-xx` (dev_run on
  ofo_dev, APP_ENV=development, OFO_SCENARIO, pool 3; PID kept in scn-launcher.pid). Path runner: `python path_run.py PATH-xx`.
- ofo_dev role `ofo_app` connection limit 10 (owner approved, KEEP 10); live stack uses ~6, test copy ~4: never run the
  test copy and the automated DB suites at the same time (they failed "too many connections").

## Done (evidence in ISSUES.md)
Live: builder (ready-made, edits, steps, multiplier, NIFTY weekly/monthly, SENSEX), charges, payoff/greeks/P&L/chart,
save, Add to Paper, plan, alerts (weekly 13:45, monthly 15:00, SENSEX 14:25, level watch, Friday carry check), act on
alert -> completed, dismiss with reason, compare/prepare, manual rolls + second adjustment, history, pause/clear, exits
(1 leg, part of a leg, 2 legs, all, via compare, leg stop, conditional exit), phone width (6 screens).
Test data (PATH-50 via Chrome; PATH-15/12/13/14/16 via path_run): T-07, T-13 gap, T-11, T-14, T-09, stages, 14:30 time
exit, cheap shorts, carry/holiday rules. Automated suites (16:07-16:37): loop core 1, exits 9, settlement 1, worker
paths 9, level watch 2 passed; day rules 2 failed (issue 69).

## Pending, in order (owner chose each, 16:1x-16:4x)
1. Item 3: saved IC reopen / rename / delete / undelete / "can't delete: orders were sent" - Chrome on 8765 after hours.
2. Item 2: alert style pin - automated tests only: tests/adjustment/test_alert_gate*.py, test_alert_presets*.py (no DB)
   and tests_app/test_alert_gate_storage.py, test_background_db_gate.py (db_run_fresh, one file at a time).
3. Clean re-run of the whole flow on today's code (every row of "Done") before telling the owner it is ready.
4. After the owner says "start development": build the decisions (ADR-255..270) and the after-market issues; then
   test-data proof, then live (ADR-270), one gate, one push.
5. Later rounds: roll to a later expiry (ADR-269, issue 68) once built; real Zerodha orders (separate planned round).

## Decisions recorded this session (spec/decisions on feature/adjustments)
ADR-255 partial exits count as adjustments, Exit all not; 256 (+amendment) exit warnings, max loss/margin before->after;
257 stop on a sold leg asks to close its wing; 258 "already true" resets after each adjustment; 259 Completed Strategies;
260 one alert list + bell counts live strategies; 261 Compare approaches always; 262 IC ready-made placement is a user
preference (delta 0.20 default); 263 money after charges, labelled; 264 settings everywhere + admin lock; 265 entry at
bid/ask mid (REQ-077 AC-5 changed); 266 marking at mid + marked loss never above max loss; 267 (+amendment) level
watches and day rules exempt from the daily cap, nothing dropped silently, every record has text; 268 delta 1/0 at
intrinsic, T-01 flags when breached; 269 roll to a later expiry = close + new linked strategy; 270 T-11/T-14 live,
test data first. Ops: dev DB limit 10 kept.
