# Test-trade plan for 26 Nov 2026 (Thu) screen checks

Basis: GC-ICLIVE final report "Screen checks for the owner's PC", ledger ic-live-test-2026-11-23-status.md, afternoon results (screen-checks-2026-11-25.md, 5d9b53ca). C-trade shapes are inferred from ledger/issue text (not stored anywhere as a spec): C1 155 = condor adjusted twice (25400 PE rolled); C2 157 = 0DTE condor held to expiry; C3 = stopped by index exit; C4 160 = stopped, closed; C5/C6 159 = adjusted, drawer 0.7293 fired; C7 161 = index exit armed above 25,720; C9 164 = 4-lot condor, 1 of 2 adjustments, two expiries (1 Dec legs priced after settlement).

## 1. Checks still blocked and what each needs

| Check | Trade state needed | Live tomorrow? | Time window IST |
|---|---|---|---|
| D-08, D-12, D-14, D-17 (0DTE half) | 0DTE condor (SENSEX 26 Nov), after 14:50 for D-08 | Yes, SENSEX expiry day | 14:50-15:30 (D-12/14/17 any time after open) |
| D-64 | Same 0DTE trade, Builder + Positions | Expiry day only | 15:30-15:45 |
| D-59 | Two-expiry paper trade (26 Nov + 3 Dec legs) with stops set, part-settles | Expiry day only | set before 15:30, read 15:45+ |
| D-71 | After expiry: History record + closed-row reason | Yes (T1) | after 15:45 |
| D-33 | 0DTE condor with short funds | Yes (T1 sized large) | on open of T1 |
| D-02, D-10, D-16, D-31, D-46, D-61 | Running condor rolled one side (short buy-back before hedge sale) | Live if an idea fires; else scenario seed | 09:30-14:00 |
| D-03 | Index exit set, then adjusted | Live | after roll |
| D-04, D-21 | Condor at 1 of 2, then 2 of 2 adjustments | Live (2 manual adjusts) | 10:00-13:00 |
| D-63 | Trade with closed rows after an adjustment (4 lots) | Live | after roll |
| D-22, D-23, D-24, D-42, D-43, D-58 rest | Closed by stop (index exit fires); armed exit shown while open | Live | D-24 while armed, rest after fire |
| D-26 | Idea lapsed + idea open | Needs scenario/seeded idea | any |
| D-36, D-38 steps | Detection on running condor, 2 testers | Only if an idea fires | market hours |
| D-37, D-05 "Not saved", D-39 positive half | Running trade, feed stopped | Yes, kill feed by PID | any |
| D-01 retest | Save index exit right after API restart | Live | 09:20 |
| D-18, D-41, D-44, D-60 | FAILED yesterday: need code fixes, retest only | Live on T3/T5 | after fix |
| D-27, D-07, D-15, D-20, D-29, D-38 | DATA rows | D-27 usable once T3 exists | any |
| D-32, D-54, D-65, D-67, D-69, D-70, D-25, D-57, D-34/35/48/51/62 | not trade-bound (phone width, own playbook, owner answers, features) | no trade needed | n/a |

## 2. Minimum trade set

All paper, 1 lot unless stated. Strikes relative to spot at open (rounded to step).

- **T1 SENSEX 26 Nov 0DTE short iron condor.** Open 09:20. Shorts about 1.2% each side, wings 500 pts. For D-33 size lots so funds are short. Do nothing to it. Unblocks D-08, D-12, D-14, D-17(0DTE), D-33, D-64, D-71.
- **T2 SENSEX two-expiry condor.** Shorts 26 Nov (as T1 strikes minus 100), long wings 3 Dec. Open 09:25. Before 15:25 set a leg stop and an index exit (far from spot). Read at 15:45+. Unblocks D-59.
- **T3 NIFTY 1 Dec condor, 4 lots.** Open 09:25. Set index exit Above (short call + 50) at once (D-03/D-24 armed text). Adjust 1 about 10:30 (roll the put side: D-02, D-10, D-16, D-46, D-61, D-63). Read D-04 at 1 of 2. Adjust 2 about 12:00, read D-04 at 2 of 2. Also D-27 (route reply), D-31 if an idea fires.
- **T4 NIFTY 1 Dec condor, to be stopped.** Open 09:30. Index exit just above spot (about +30, after D-01 guard allows) or a tight leg stop; let it fire. Unblocks D-22, D-23, D-42, D-43 (needs T3 rolled to show names), D-66 re-read.
- **T5 existing 170** keep: D-24 armed, D-41/D-18 retests, D-37, D-05, D-39 feed-stop checks.

Scenario tooling: `scripts/seed_scenario.py ADJ-<id>` (run via `scripts/orchestrator/dev_run.py <worktree> python scripts/seed_scenario.py ADJ-02`) creates ONE paper strategy "Scenario ADJ-02" from `tests/fixtures/adjust_scenarios/ADJ-01..38.json` (and PATH-xx frame 0) on database ofo_dev only, via the app's stores: rolled/adjusted history, booked P&L, adjustment times. It writes a trade, not a price feed. The app has a per-screen `scenario_mode` switch (backend/ofo_app/background.py) that reprices from the generated feed. A scenario_stack.py helper existed in `D:\Abhay\scratch\fix-batch1\` (not in repo; not checked). Unchecked: whether the seeded trade shows under the owner's live ofo_dev login and whether seeded ADJ fixtures cover 0DTE/index-exit/stopped shapes. Use it as fallback for D-02/03/04/10/16/26/31/46/61/63 if no live idea or manual roll works.

## 3. Timed run order (IST)

| Time | Action |
|---|---|
| before 09:15 | Restart API/feed; confirm main checkout on 5d9b53ca (or fixed head). Keep T5 170 |
| 09:20 | D-01 retest right after restart (index exit save); open T1 |
| 09:25 | Open T2, T3, then T4; set T3 index exit; set T2 stops |
| 09:30-10:30 | Live A checks on T3/T5: D-06, D-16 baseline, D-17, D-33, D-12, D-14 on T1 |
| 10:30 | T3 adjust 1 (roll put side): D-02, D-10, D-03, D-16, D-46, D-61, D-63, D-04 (1 of 2), D-27 |
| 11:00-11:30 | T4 stop fires: D-22, D-23, D-42; D-24 on T3 |
| 12:00 | T3 adjust 2: D-04 (2 of 2), D-21 |
| 13:00-14:00 | Feed-stop block on T5: D-05, D-37, D-39, D-41 retest; D-36/D-38 if idea open |
| 14:50 | D-08 on T1 |
| 15:25 | Confirm T2 stops saved |
| 15:30-15:45 | D-64 on T1 (Builder + Positions); screenshot every minute |
| 15:45-16:00 | D-59 on T2 after part settlement; D-71 on T1 |

## 4. Do-not-delete rule line

Paper trades T1-T5 (and strategy 170) are test data: do NOT delete, clear, rename-and-save or "clean out" any paper strategy until every check in section 1 has a recorded result in screen-checks-2026-11-26.md; record the trade ids in this file the moment each is opened.
