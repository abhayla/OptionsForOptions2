> SUPERSEDED (owner 6 Nov ~23:2x IST, question tool): "Test data only" - no live-market day; the Monday 9 Nov live run is
> DROPPED. Remaining work: show in Chrome (visible) only what was not yet shown on screen; keep tonight's results.
> Alerts raised by the background, stops firing and Pause do not work on test data: logged as gaps, no code change
> (development stays on hold).

# Clean re-run of the iron condor flow, Monday 9 Nov 2026 (paper only)

Code: 514113f1 (API 8765 restarted 15:22 on 6 Nov; background restarted 17:15 on 6 Nov, issue 75). Frontend vite 5173
from the settings tree (same code). Nothing may change code before or during the run (development on hold).
Monday is the NIFTY 9 Nov weekly expiry: the expiry-day rules get live coverage for the first time.

Already on 514113f1 and counted (not re-run, identical code): test-data PATH-50 / 15 / 12 / 13 / 14 / 16 and the
automated suites of 6 Nov 16:07-16:37 and 17:0x-17:1x (see ISSUES.md). Known reds there: issues 69, 74 (tests).

## Before 09:15
- [ ] Owner: Kite login (daily token). The only owner step.
- [ ] Check every role is alive by recorded PID: Redis 1608, liveprices 20852, background 6116 (launcher 7712), API 4580,
      vite 5173 / 26768. Background log shows "strategies monitored".
- [ ] Expiry lists load for NIFTY and SENSEX (issue 1 guard: if refused again, use the audited override, log it).

## 09:15-11:00 Builder and entry (live)
- [ ] Ready-made Short Iron Condor NIFTY weekly (17 Nov) + monthly (29 Dec) + SENSEX weekly (as 19 Nov on 6 Nov): legs, strikes, charges.
- [ ] Edits: strike -/+ (4 quick clicks land 4 steps), Shift / Width / Hedge, Multiplier 2 doubles credit, margin, charges.
- [ ] Payoff chart, payoff table, greeks, P&L table, At Expiry / Estimated Now.
- [ ] Save, reopen, rename (item 3 today: PASS except issues 71, 72, 73).
- [ ] Add to Paper: entry prefilled at the live price (issue 6 fix), plan dialog, "Use playbook as is" stores the plan.
## 11:00-13:30 Adjustments (live)
- [ ] Manual roll in Drafts Mode, review, confirm; second adjustment; history rows and booked P&L reconcile.
- [ ] Compare approaches: A-01 picks an OTM strike or refuses (issue 31), A-02, A-06 prepare opens Drafts Mode (issue 34),
      Exit whole prepare opens the exit dialog (issue 24), compare answers inside 30 s (issue 29).
- [ ] Pause until / Clear; level watch armed.
## 13:30-15:30 Alerts and exits (live, background on 514113f1)
- [ ] Weekly 5-min candle alert (13:45 or first crossing), monthly 15-min alert, SENSEX alert, level watch alert.
- [ ] Act on an alert -> completed; dismiss with a reason.
- [ ] Exits: 1 leg, part of a leg (1 of 2 lots), 2 legs, all, via Compare, leg stop, conditional exit.
- [ ] Expiry day (9 Nov condor): stage "Last day", T-09, A-27 cheap shorts, 14:30 time exit A-35 / T-10b live.
## Pass rule
Every row behaves as it did on 6 Nov or better, on 514113f1, with no NEW defect of severity critical (wrong order side,
wrong strike, duplicate order, wrong money). Known open issues are listed, not re-counted as failures.
