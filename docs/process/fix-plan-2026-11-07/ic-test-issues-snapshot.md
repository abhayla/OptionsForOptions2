# Iron condor UI test, 2026-11-06 (paper only, live NIFTY ~24,690)

Scope (owner, question tool 12:1x-12:2x): paper only; 7 areas + charts + exit one leg / several legs / whole;
all IC strategies soft-deleted incl. 82 (29 rows, 79 -> 50; backups backup-<id>.json; undelete = /strategies/{id}/undelete).
App: 8765 moved to 42924b7b at 12:3x (migrations 0043, 0044 on ofo_dev), frontend vite dev :5173 from the settings tree.

| # | Area | Issue | Needs market? | State |
|---|---|---|---|---|
| 1 | Data / builder | Expiry lists EMPTY for NIFTY and SENSEX: today's Zerodha list refused by the 10% delist guard ("would drop 2065 of 4118 live NIFTY contracts, 50.1%"). Real cause: exchange narrowed the strike range at the wings (NIFTY 9 Nov now 20050-26750 contiguous, 135 strikes; 17000-20000 and 26800-29200 gone); file complete (120,828 rows). Guard misreads a wing narrowing as truncation; the refusal reason is also silenced in the app log. | yes (today's list) | WORKAROUND 12:5x: forced load via the guard's own audited override (reason+actor+audit): added 206, delisted 2237. CLASS FIX after market: guard must tell wing narrowing from truncation; log the refusal code reason. |
| 2 | Option chain (leg picker) | Put OI column mixes formats: "97,045", "14,170", "57,330" next to "1.3L", "8.2L". | no | after market |
| 3 | Builder strike -/+ | Each leg-edit takes 4.1-4.8 s; a click during it cancels the previous relative step (newest-wins), so 5 quick clicks = 1 step, 12 clicks 2 s apart = 0 steps, page stuck "Updating the numbers...", once a red "could not get an answer" banner. | yes (latency on live data) | builder dispatched (fix/leg-step-coalesce) |

| 4 | Builder payoff table / paper panel | Max Profit/Loss are net of charges (+5,272 / -7,728) but the Payoff Table (+5,570.50) and "Profit left / Loss left" (+5,625.75 = gross 5,570.50 + 55.25) are gross; nothing labels which. | no | after market |
| 5 | Builder P&L table | Total P&L % uses max loss as base (-97.50 -> -1.3% = /7,429.50) while each leg's % uses its premium; unlabelled mixed bases. | no | after market |
| 6 | Add to Paper | Paper entry price defaults to the planned price captured ~15 min earlier (24300 PE 126.00 while LTP ~129), not the live price; exits DO use the live LTP. Flatters paper P&L. | yes (live prices) | open |
| 7 | Plan dialog after Add to Paper | Shows an EMPTY modal for 5-14 s with no loading text, then the plan; first time had no "Alert style" field, second time had it. | no | after market |
| 8 | Paper panel | Contract dates as "2026-11-17" while every other screen says "17 Nov". | no | after market |
| 9 | Playbooks page | Version dates "11/1/2026, 2:53:56 PM" (US format) vs IST format elsewhere. | no | after market |
| 10 | Plan dialog | "Use playbook as is" on strategy 86 left plan = null (no POST in the server log); "Save plan" on 87 stored it. My click may have missed: RE-TEST. | no | to re-test |
| 11 | Opportunities + bell | Alerts of DELETED strategies stay Open with "Compare approaches" (82 "Owner IC Dec", L4 ICs); bell count includes them. | no | after market |
| 12 | Opportunities wording | "Spot crosses a breakeven: -123.5000 (rule 0.0000)", "Trending day: 0.1507 (rule 0.1500)": raw 4-decimal numbers, no units. | no | after market |
| 13 | Opportunities (old rows) | 4 Nov rows "Spot within ... 0.0034 % (rule 0.0220 %)" while the playbook says 0.75 %; today's check gives 0.3365 vs 0.75 (right). Probably old code; verify no new row repeats it. | no | verify |
| 14 | Background checks | The background role (python -m ofo_app.background) was NOT running (nor liveprices/bus): no adjustment alert was raised for anyone since 4 Nov 14:25. Started 12:50 IST in bus mode (Redis5 6380, liveprices, API FEED_MODE=bus, background). The start procedure for this PC must start all roles. | yes | ops fixed live 12:50; runbook/launcher fix after market |
| 15 | Exit one leg | Exiting the bought 25300 CE wing alone: no warning that the 25100 CE becomes a naked short (unlimited loss, margin 70k -> 1.66 lakh). | no (design) | owner/product call |
| 16 | Exit dialog | DB pool exhausted (API pool 2, role limit 5, all 5 used; tunnel to VPS): the exit order WAS stored (order 224) but the dialog said "could not get an answer" and re-enabled Confirm -> a second click would sell again (duplicate exit = new naked short). Same root cause as #3's 503s: sqlalchemy QueuePool timeout 30 s. | yes | fix: idempotent submit / show stored order; latency class with builder |
| 17 | Builder after exit (bus mode) | "NIFTY 17 Nov 24300 PE: no live quote" + "Estimated Now unavailable: no IV" while the paper table shows LTP 135.40 for the same leg. | yes | investigating |
| 18 | DB tunnel | SSH tunnel to the VPS DB dropped once (~12:5x), API unhealthy until it came back (new ssh PID 9144). | yes | observed |

| 19 | (withdrawn) | Tracking panel missing for paper strategies: wrong, the 404 was before Add to Paper; panel shows on 86/87. | - | withdrawn |
| 20 | Monitoring after a shape change | After exiting one wing, condor A (3 legs) has type null -> playbook "none", NO results, NO message; REQ-161 AC-4 says an unmapped shape gets the generic triggers and the sheet says so. Generic triggers are not built (route doc: "type None -> source none and no results"). After the 2nd exit the strangle WAS typed (strangle playbook, T-03 + T-18 flagged). | no | after market; needs the generic-trigger set (design) |
| 21 | Review drawer leg list | Closed legs "65 units 17 Nov 24100 PE" next to open legs "1 x 17 Nov 24300 PE". | no | after market |
| 22 | Compare: Exit whole | Max loss after = -1,754.91 vs P&L -1,459.25 minus cost 102.41 = -1,561.66: ~Rs 193 unexplained (entry charges?). | no | verify after market |
| 23 | Adjustment counting | Every paper exit (wing exit, exit all) counts as an "adjustment" (history rows adjustment 1..3; T-18 flags 2/2; compare then offers ONLY "Exit whole", shown as "3 of 2"). | no | OWNER QUESTION: do exits count as adjustments? |
| 24 | Compare -> Prepare "Exit the whole strategy" | No request is sent; shows "The page could not get an answer from the server." Cause: AdjustCompare.openInBuilder builds legs from after_legs, which is empty for a full exit -> null -> NEUTRAL_PARTS. A full-exit approach can never be prepared, and the message blames the server. | no | fix (frontend) |
| 25 | Completed Strategies | Never shows anything: COMPLETED_STATUSES = [] in MyStrategiesPage.vue; a fully exited paper strategy stays status "draft". | no | not built; owner/product |
| 26 | History | Fill column header "Zerodha" for paper rows (cells say "Paper - not sent to Zerodha"). | no | cosmetic |
| 27 | Console | Vue warn flood: AdjustDrawer prop "client" expected Object, got Function (TrackingPanel), every poll. | no | after market |
| 28 | Polling | Page polls /paper/alerts + /adjustment-opportunities every ~3 s and /strategies/{id}/tracking every ~3 s: with pool 2 this starves the API. | no | after market (poll interval / single combined read) |

| 29 | Compare page | POST adjustment-approaches took 9.5 s (strategy 88); browser client timeout is 10 s -> page shows "could not get an answer". | yes | builder dispatched (fix/a01-delta-side, item 2) |
| 30 | A-11 convert to iron fly | Correct end shape (24550/24750/24750/24950) but sends two separate BUY 24950 CE orders instead of one 2-lot order (extra brokerage). | no | after market |
| 31 | A-01 roll untested spread toward spot | CRITICAL: on 88 (spot 24,738, call side tested) picked SELL 25,600 PE (~860 pts ITM) as the new short put "at delta 0.30"; only blocked because that strike had no price. | yes | builder dispatched (fix/a01-delta-side) |
| 32 | A-26 refusal wording | "has fallen from Rs 175 to Rs 175.82" (it rose); "holds 1 lots". | no | after market |
| 33 | Background alerts | RCA (read-only Opus, 13:4x): 86's flags (13:24-13:27) never met the Weekly rule "holds at a 5-min candle close" before the 13:27:35 exit (first full candle closed 13:30) = by design. Real defect found: background.py:798 publishes the monitor list before :809 loads gate rows; a check in that gap pauses silently (:1136-1140, no log) and alert_gate.py:310-311 takes no sample for that candle -> a new strategy's first alert slips one candle. Also no per-strategy gate/pause log. 51/59 open records block new ones by ADR-237 (5) (by design). | no (timing) | after market: publish after _load_gates; log first pause per reason; gate counts in minute line |

| 34 | Compare -> prepare a NON-exit approach (A-11 iron fly on 88) | Opens an UNLINKED "New Strategy" (/strategy/builder, no id; Save / Add to Paper) instead of strategy 88's Drafts Mode with pending changes (ADR-207 (2)). Add to Paper would open a 2nd position and leave 88 open. | no (logic) | builder dispatched (fix/prepare-into-drafts) |
| 35 | Drafts Mode notice | "Your price for leg 3 was replaced by the captured price of 25000.00 CE." names the strike where the price should be. | no | after market |
| 36 | Already-true after adjusting | T-03 on 88 stays "already true when tracking started" after the tested call was rolled 24950 -> 25000 (delta still 0.38): a rolled leg never flags. | no | owner/spec (F-71) |

| 37 | Payoff Table "Add Booked P&L" | On 88 (booked -357.50) the At Expiry value at 24,800 is Rs 7,998.25 with the box ON and OFF; with booked it should be 7,640.75 (= history totals credit). | no | after market |

| 38 | Alerts screen vs bell | Alerts > Active lists paper stop/conditional exits only (incl. deleted strategies, "exited 1 legs"); adjustment alerts live on Positions > Adjustment opportunities. Two places, no cross-link. | no | owner/product |
| 39 | History "why" | A basket prepared from Compare (A-06 on 89) is recorded "Your own change"; the approach name is lost. | no | after market |
| 40 | Paper list | "UT IC 17Nov D - 6 legs" counts closed legs (4 open). | no | after market |
| 41 | Current positions > Paper summary | Total P&L "-" "Paper P&L paused - prices not live" during live market: one old position without a price (old test strategies, booked -3,06,788) blanks the whole account summary. | yes | after market |
| 42 | Alert -> Compare | Opens with pick=A-36 ("Only the ones picked") so the prepare list is EMPTY; the user must switch to "All that apply" to act. | no | after market |
| 43 | Leg stop on a short leg | Stop on S 24950 CE fired (BUY 232.35 at level 232.00) and left its wing B 25050 CE open alone. | no | owner/product |
| 10 | (withdrawn) | "Use playbook as is" DOES save the plan (89: plan stored). Earlier miss was my click. | - | withdrawn |

| 44 | Conditional exit orders | Orders from a conditional (index-level) exit are labelled kind "stop" in the order book. | no | after market |
| 45 | Paper P&L on thin SENSEX strikes | Legs marked at last traded price: in ~10 min SENSEX +42 pts but 80300 PE -50 pts (delta ~0.5 predicts ~21), per-leg P&L -1,311 / +1,005 / -895 / +1,132 while the net was -69. Stale LTPs on thin BFO strikes make per-leg P&L and stops misleading. Mark at bid/ask mid when the LTP is older than the quote? | yes (needs live quotes to measure) | to measure: compare LTP time vs quote time on BFO legs; then decide (owner: marking basis) |
| 46 | Paper panel first paint | For a few seconds the Net Positions panel shows LTP = entry price and Total P&L 0.00 before live prices arrive (SENSEX 90). Should show "loading", not 0.00. | no | after market |

| 47 | Builder planned entries (far-month) | CRITICAL for trust: NIFTY 29 Dec condor 24650/24750 PE + 24950/25050 CE captured LTPs gave credit 104.60 (14:30) and 102.95 (14:33) on 100-pt wings -> max loss = charges only (Rs -516), an impossible no-risk trade. Chain at 14:32: 84.85. Stale LTPs (25050 CE 500.50 unchanged across minutes; 24750 PE LTP = entry 383.70). | yes | DECIDED ADR-265 (capture at bid/ask mid, LTP only without a quote; setting; "credit more than wing width" warning) - build when development starts |
| 48 | Builder draft restore | An unsaved 2-lot draft was lost after going to Market > Option Chain and back; REQ-154 AC-1 says the builder restores the unsaved strategy after a reload. | no | after market |

| 49 | False loss alert from stale prices | Live T-06 alert 153 at 14:25 on SENSEX condor 90: "Loss reaches 240.7767 % of max loss" - impossible for a defined-risk condor (max loss Rs 309 before charges); marked loss came from stale last trades (issue 45). | yes | DECIDED ADR-266 (mark stale legs at mid; marked loss never above max loss -> "not checked"); build when development starts |
| 50 | Playbooks page, phone width | Page 429 px wide on a 400 px screen: fixed "Reason for this change" box (w-96, 384 px) and the step buttons push it sideways. | no | after market |
| 51 | Builder, phone width | Fits (no sideways scroll) but cramped: expiry cut to "9 Nov (3 da", shape name "Short Iron Co...", top menu scrolls sideways. | no | after market (minor) |
| 52 | Exit dialog: max loss jump | Exiting 1 of 2 lots of the sold 24950 CE on 91 raised max loss from ~Rs 795 to Rs 36,856.72 (hand-checked correct) with no sign in the dialog. | no | DECIDED ADR-256 amendment (every exit shows max loss and margin before -> after; warning when max loss more than doubles) |
| 53 | Opportunities, phone width | Fits, but Outcome / Compare approaches / Dismiss are off-screen to the right in a sideways-scrolling table. | no | after market |
| 54 | Positions > Paper, phone width | Page 637 px wide on a 400 px screen (action column w-36 shrink-0: Open in Builder / Add orders / Stops). | no | after market |

| 55 | Live price bus | One "feed bus unreachable: TimeoutError" in the API at ~14:48 (recovered by itself). Redis tick stream capped at 20,000 messages but each is ~10 KB, so ~215 MB RAM held on this PC. | yes | after market: trim tick payload / lower cap; log reconnects |
| 56 | Monthly T-02 alert | On 91 T-02 ("spot crosses a breakeven") turned true after the 14:37 partial exit (value -23,036 vs rule 0) but no alert at the 14:45 monthly candle close. | yes | CLOSED (by design): alerts 154 T-02 and 155 S-02 "Trending day 0.2708 (rule 0.15)" raised at the 15:00 monthly 15-min close, the first full candle after the 14:37 crossing. Monthly alert path proven live. |

| 57 | Level watch vs daily cap | 91's user watch "Above 24,870" was HELD "daily_limit" at 15:00 because two automatic alerts (154 T-02, 155 S-02) used the monthly cap of 2. | no | DECIDED ADR-267 (user watches never held by the cap) |
| 58 | Friday 15:00 day rule | Works live: carry-check alerts 158 (92), 156 (51), 157 (59) at the 15:05 weekly close. | yes | VERIFIED |
| 59 | Day-rule alert text | Record 158 (carry check) has condition = None and summary = None: the alert row shows an empty "What happened". | no | DECIDED ADR-267 amendment (every record carries its text); after market |
| 60 | Day rule dropped silently | 91's weekend carry check flagged at 15:00 but was neither recorded nor held (monthly cap of 2 used by 154/155); no trace anywhere. | yes | DECIDED ADR-267 amendment (day rules exempt from the cap; nothing dropped without a held row) |

| 61 | Scenario tool: index display | In scenario mode the index / chain / strategy sockets keep frame 0's spot (23,750, 5 Nov 11:59) while P&L and checks follow the stored frame (documented "known bypass"). Confusing on screen. | no | after market (test tooling) |
| 62 | Scenario tool: background checker | The scenario-mode background worker logs no recompute after frame moves (stuck at the frame-0 minute line; frame row stored 15:36:59) -> no alerts from test data in the running app. Cause not found (clock is scn.clock, before_cycle syncs the frame). | no | RCA when development starts; background paths covered by automated tests meanwhile |
| 63 | Expiry close, intrinsic-only options | PATH-50 frame 7 (expiry 15:25, sold 23500 CE = intrinsic 100): T-03 "delta of a short leg not available", T-14 and S-02 not checked - delta rules silent exactly when the short is in the money. | no | DECIDED ADR-268 (delta 1/0 at intrinsic) |
| 64 | T-01 when breached | Same frame: spot 100 pts beyond the sold call (0.42 %) leaves T-01 clear (last-day limit 0.3 %): no "near the short" warning once the short is breached. | no | DECIDED ADR-268 (T-01 also flags at or beyond the strike) |

| 65 | Crossed rules relabelled "already true" | A rule that crossed AFTER entry is shown on later checks as "Already true when tracking started" and loses its flag (and the Review entry): PATH-12 T-07 / T-09 flagged at expiry 09:30, "already true" at 12:00; PATH-14 T-11 / T-07 flagged frames 4-5, "already true" from frame 6. False text, and the warning vanishes while the condition still holds. | no | after market (logic defect; check memory treats "true at last check" as the entry baseline) |
| 66 | Scenario copy API pool | The scenario API with the default pool 2 timed out (QueuePool 30 s) on one paper entry (PATH-13): same class as issue 3/16 - the default pool 2 is too small for one user. | no | evidence for the pool / round-trip fix |
| 67 | INCIDENT (my tooling) | My scenario restart script matched processes by command-line text ("*scenario_stack.py*") and also stopped the host process that parented Redis, the live-price process and the live background; Redis stopped at ~15:5x (market already closed). Restored: Redis restarted (pid 1608), live price and background rebuilt their keys; 8765 never stopped. Script now stops only the launcher PID it recorded. | - | fixed (tool); lesson: never select processes by command-line text |

| 68 | Roll to a later expiry | Today A-04 / A-05 (and manual roll-outs) are adjustments inside the same strategy; owner decided they close the strategy and open a new linked one (ADR-269). Untested end to end (refused live on the roll-cost limit; no after-numbers on PATH-50 frame 2). | no | DECIDED ADR-269; test after it is built (test data + one live repeat) |

| 69 | Carry-check content (automated proof) | tests_app/test_day_rules_worker.py: 2 failed / 3 passed on 514113f1 AND on 42924b7b (pre-merge) - the carry-check record has gap_pct None, next_open None, gap_reason adjust_trigger_carry_gap_unknown, gap_setting_reason setting_user_unreadable. Old defect, not from today's merges; same as live record 158 with no text (issues 59/60). Last night's gate TOTAL PASS did not catch it. | no | after market (fix with ADR-267 amendment); detection: why the gate missed this suite |

## Verified on test data (PATH-15 gap, PATH-12 time sweep, PATH-13 IV up, PATH-14 IV crush, PATH-16 expiry close; strategies 94-100, scenario-marked)
- Setup on these paths via the same API calls the builder makes (POST /strategies, POST /paper/.../orders at the scenario LTP, plan "as is"); the builder / picker / Add to Paper screens themselves were proven on PATH-50 and live.
- PATH-15: next-day 09:20 gap 23,100 -> 23,300 (0.8658 %) -> T-13 gap flag (0.75), with T-01, T-03, S-02.
- PATH-12: stage Early (6 days) -> Middle (3 days) -> Last day (expiry); T-07 rises with decay 54.9 -> 57.6 -> 58.1 -> 100 %; Friday 15:00 carry check; last day T-09, A-27; 14:30 T-10b + A-35. Issue 65.
- PATH-13: IV 10 -> 14 %: P&L -702 / -1,430 / -2,158 / -2,873; T-11 flags at +4.0 pts (limit 3).
- PATH-14: IV 10 -> 6 %: P&L +955 ... +3,796; T-07 at 53.7 % then 70.5 %; T-11 flags at -3.9 pts. Issue 65 again.
- PATH-16: expiry 14:20: T-01 0.0855 % (0.3), T-14 gamma 3.10 % >= 2 (T-14 logic proven on test data), T-09, S-02; 14:30: T-10b, day.expiry.1430 rule, A-35 offered. Entry used 0.05 where the scenario has no quote for far strikes.
- Automated suites on throwaway databases (16:07-16:37, code 514113f1): test_ic_paper_loop_core 1 passed; test_ic_exits_paper 9 passed; test_ic_settlement_paper 1 passed; test_ic_rules_worker_paths 9 passed; test_level_watch_worker 2 passed; test_day_rules_worker 2 failed / 3 passed (issue 69, also fails on 42924b7b).

## Verified on test data (PATH-50, scenario copy on 8766 / ofo_dev, strategy 93 marked PATH-50, 15:3x-15:5x)
- Built via the leg picker (Add leg, strikes window 20, B/S per row, lots 2), saved, Add to Paper, plan "as is"; "Scenario - test data, not the market" banner shown; live strategies 86-92 not scenario-marked (isolation).
- Frame 0: T-02 / T-03 / T-11 already true at entry (T-11 IV 6.0 pts vs 3: IV rule logic works on test data).
- Frame 1 (Fri 14:00, 23,330): T-07 profit 75.2 % >= 50 flag; P&L +14,683.50.
- Frame 2 (Fri 15:00, 23,200): T-01 0.2155 % (Middle 0.5), T-03 0.3846 (0.35), T-07 65.7 %, Friday 15:00 carry check, S-02; P&L +12,831 reconciles leg by leg; A-01 rolls the call spread to 23350/23550 (OTM), A-29 halves 2 lots, A-28 closes the put spread, A-11 fly.
- Frame 3 (Mon expiry 14:20): stage "Last day"; T-07 100 % >= 80; T-09 0.05 <= 2; A-27 buy back cheap shorts offered; A-35 time exit refused ("from 14:30").
- Frame 4 (14:29): A-35 still refused. Frame 5 (14:31): A-35 offered, T-10b clock rule flags.
- Frame 6 (15:00): day-before-holiday carry check flags.
- Frame 7 (15:25, 23,600): sold 23500 CE = 100; P&L +6,532.50 reconciles; issues 63, 64.

## Verified live (not-done list, 14:35-15:00)
- Exit part of a leg (1 of 2 lots): DONE (see below).
- Dismiss an alert with a reason: 149 -> "dismissed, Not relevant"; open 17 -> 16.
- SENSEX alert live: 153 T-06 at 14:25:00 (candle close) on 90, lapsed "The strategy closed" after the 14:29 exit (alert path right; value wrong, issue 49).
- Middle stage (3 days, 9 Nov condor 92): stage "Middle", limits 0.5 % / delta 0.35 applied.
- Monthly style on 91: confirm candle 15 min, cooldown 120, cap 2; level watch Above 24,870 armed 14:40 (result below).
- Phone width (400 px): builder OK (cramped), compare OK (table scrolls in its box), opportunities OK but actions off-screen, alerts OK, Playbooks 429 px and Positions > Paper 637 px overflow.

## Verified live (monthly + multi-lot, 14:30-14:45)
- NIFTY 29 Dec condor with Multiplier 2: credit 6,799 -> 13,598, margin 63,929 -> 1,27,826 (double), charges 516 -> 795 (brokerage per order: right).
- Monthly style applied: alert style "Automatic (now Monthly)"; T-01 limit 1.5 % (weekly 0.75), T-03 limit 0.25 (weekly 0.30).
- Partial leg exit: 1 of 2 lots of S 24950 CE -> BUY 65 @571.20 (exit), net -65, booked 0.00; total +2,054.00 = +1,118 + 0 + 591.50 + 344.50.

## Owner decisions this session (recorded in spec, development ON HOLD until the owner says start)
- ADR-255 partial exits count as adjustments, Exit all doesn't (issue 23)
- ADR-256 factual warning on an exit that leaves a sold leg unprotected (issue 15)
- ADR-257 stop on a sold leg asks to close its wing, ticked by default (issue 43)
- ADR-258 "already true" resets after each adjustment (issue 36)
- ADR-259 Completed Strategies lists closed strategies with final totals (issue 25)
- ADR-260 one alert list in Alerts > Active, bell counts live strategies only (issues 11, 38)
- ADR-261 Compare approaches always available (no-alert case, strategy 87)
- ADR-262 ready-made iron condor placement is a per-user preference, default delta 0.20 (observation)
- ADR-263 every headline money figure after charges, labelled (issue 4)
- ADR-264 behaviours and numbers are settings: admin default, user override, admin lock; standing rule for new work (configuration plan approved; owner asked to see screens first, then put ALL development on hold 14:2x: "Only update the requirements and issues ... Do not start development")
- ADR-265 SPEC CHANGE REQ-077 AC-5: planned entry captured at bid/ask mid by default (setting), warning when a credit is more than the wing width (issues 45, 47)
- Ops: keep ofo_dev role limit 10 / DB_POOL_SIZE 6.
- Owner 14:4x: "Why are you asking me? You should go with your recommendation." -> strategy/behaviour questions are decided by me with a decision row and reported as information (memory strategy-questions-go-with-recommendation, 2nd miss).
- Kept earlier answers for ADR-255 / ADR-257 after the "go with your recommendations" message (question tool).

## Verified live (SENSEX, 14:16-14:30)
- Ready-made SENSEX condor 19 Nov: lot 20, 100-pt strikes, charges reconcile (~Rs 398 est., Rs 401.35 actual round trip); paper entry prefilled live; Exit all of 4 legs at live prices; closed gross -69.00.

## Verified live (alerts and exits, 13:45-13:58)
- Background alerts: 13:45:01 (5-min candle close) record 151 T-18 (2/2 adjustments) and 152 level watch above 24760 (24775.60) on 88; nothing held.
- Acting on an alert: Opportunities -> Compare (switch to All) -> Exit the whole strategy -> exit dialog (acted=151,152&basket=4) -> Confirm -> 151 and 152 outcome "completed".
- Paper leg stop: armed 13:56:37 Above 232.00 on S 24950 CE (89), fired 13:57:41, BUY 232.35 (stop).
- Conditional exit: Above 24,815.00 armed on 89 at 13:59 (result below).
- A-01 fix live on 89: refuses "No strike in the chain brings Leg 2 (SELL 24,700 PE) to the target delta" (no ITM pick). A-02 picks 25,250 = nearest |delta| <= 0.30 (25,200 = 0.3026, 25,250 = 0.2788): correct.
- #34 fix live: A-06 prepared on 89 -> /strategy/builder?strategy=89 Drafts Mode, 4 pending changes, review B Exit 24900 CE 252.25 / S Exit 25000 CE 207.60 / S Add 24950 CE 230.20 / B Add 25050 CE 188.00, confirmed as adjustment 1 (booked -97.50).

## Verified live (areas 5-6, manual path)
- Manual roll in Drafts Mode on 88: "+" on S 24950 CE -> 2 pending changes -> Review: B Exit 24950 CE 199.20 / S Add 25000 CE 176.90 -> confirmed; booked -422.50 = (192.70-199.20)x65; net premium 108.20 = (175-120.45)+(176.90-123.25).
- Second adjustment on the same strategy: S 24500 PE -> 24550: B Exit 174.00 / S Add 189.85; booked +65.00; history rows entry / adjustment 1 / adjustment 2, totals booked -357.50, charges 345.75; T-18 flags 2/2 (crossed 13:41:19).

## Verified live fixes (merged 46811400 into feature/adjustments, served on 8765 since 13:15)
- #3 strike step: 4 quick "+" -> "24850 +4" shown, landed 25050 with fresh price 152.20; no error banner.
- #6 entry prefill: Add to Paper on 88 prefilled LTP (120.45 vs planned 121.75; 175.00 vs 179.10; 192.70 vs 191.55; 123.25 vs 125.20).
- #24 compare -> "Exit the whole strategy" -> prepare: exit dialog with 4 legs, right sides, live prices, 1 lot each; confirmed; 87 fully closed (booked -1,036.75 / +1,309.75 / -2,073.50 / +1,800.50, charges 365.97). b973d36e merged b60682a9.
- Pause (A-38): pause until 14:00 stored ("paused": true, until 1400), Clear stored (paused false); texts right.
- Level watch (A-37): "Above 24760" stored on 88 at 13:3x; alert pending a crossing.
- Pool: role limit 5 -> 10 (owner OK 13:1x, revert after market unless kept), DB_POOL_SIZE=6: /health 5.4 s -> 0.29 s; 0 QueuePool errors since restart.

## Fixes in progress
- #3: commit e34bd754 (branch fix/leg-step-coalesce): clicks accumulate (steps 1-20, server moves one listed strike at a time); guard test fails 5/7 on old code. Found: templates file re-read every leg-edit (~115 ms, twice for Shift/Width/Hedge).

## Observations (trader view, not defects)
- Ready-made "Short Iron Condor" sells only +-100 from spot with 100-wide wings (24500/24600/24800/24900 at spot 24,693): near an iron butterfly; a typical condor sells ~1 SD out. Owner call whether to widen the default.

## Item 3: saved IC reopen / rename / delete / undelete (Chrome 5173 -> 8765, code 514113f1, 16:55-17:1x, market closed)
| 70 | Builder after market close (bus mode) | REGRESSION of ADR-197 / ADR-200: reopening 91 (29 Dec) and 92 (9 Nov) at 16:55 shows "Outcome cannot be shown: reference price for <expiry>: a reference price for this expiry could not be worked out from option prices", index "NIFTY -", banner "Market closed." with no "Prices are from <time>" (ADR-177). ADR-200 was built 27 Oct for the direct feed; today runs FEED_MODE=bus (FeedRelay has no FeedState, feed_health.market_closed_for falls back to the calendar) - suspect the held close never reaches the API in bus mode. | after-close state (every evening) | after market: RCA when development starts; blocks after-hours review of positions |
| 71 | Reopen a fully closed strategy | 86 (all 4 legs closed, P&L -1,277.25) opens with "No legs yet / Add leg / Pick from Option Chain" and "No draft strategy is open" beside a paper panel of 4 closed legs: reads as an empty new draft, not a finished trade. | no | after market: show "All legs closed" + final result; link to Completed Strategies (ADR-259) |
| 72 | Delete -> Undo placement | Undo works (97 deleted, Undo, row back), but the toast renders below the whole list: appeared 2.2 s after confirm at 2,605 px on a 639 px screen (64 rows); window 10 s (reuses other.undo_clear_all_seconds). A user does not see it. | no | DECIDED ADR-271 (5): fixed toast, window counted from when it appears |
| 73 | Delete of a paper strategy | can_delete true for 86-92 (all with paper fills); 86 deleted from its row with no refusal, confirm called it a "draft"; restored by undelete (200). Cause: _CAN_DELETE_SQL checks execution_plans + strategy_versions only. Real-order rows 9/11/17: "Orders were already sent for this strategy, so it cannot be deleted." in the row; DELETE on 9 = 409 STRATEGY_VALIDATION_432 (server guard holds). | no | DECIDED ADR-271 (1)-(4); build when development starts |
| obs | Rename | Inline, 20-char cap holds (21st char refused), empty name refused "The strategy has no name.", persists after reload; list column cuts 20-char names ("IC Rename Test..."); rename does not move "last saved" nor the revision (97 still rev 1). | no | cosmetic, after market |
| obs | Undelete | No screen (ADR-184: no restore); API POST /strategies/{id}/undelete?expected_revision=N (query param, not body; first try with a body gave 422). 95, 97, 86 restored, all listed again. | - | as designed |

## Item 2: alert style pin, automated (17:0x-17:1x, code 514113f1; DB files via main-checkout db_run_fresh on the live tree, one at a time)
- tests/adjustment/test_alert_gate.py 41 passed; test_alert_gate_lapse_restore.py 20 passed; test_alert_presets.py 28 passed (no DB).
- tests_app/test_background_db_gate.py 15 passed.
- tests_app/test_alert_gate_storage.py 26 passed / 1 failed (issue 74).
| 74 | Stale DB test (detection gap, same class as 69) | test_the_downgrade_restores_the_0031_guard_and_the_0035_allowlist_chain replays 0036's downgrade alone on a database at head 0044: "app role allowlist refused for ofo_app (post): function public.strategy_adjustment_plans_guard body differs from its pinned body". 0041 re-pinned that guard after 0036, so a mid-chain downgrade on head cannot pass; a real downgrade runs 0044..0037 first. Test defect since 0041, not a product defect; the alert-gate behaviour tests all pass. Not caught by last night's "TOTAL PASS" gate, like 69. | no | after market: test downgrades from 0036's own head (or the whole chain); RCA why the gate does not run these tests_app DB files |
| ops | Runner | db_run.py reads .env beside its own script: settings and live trees have none, so DB tests run as `python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py <tree> python -m pytest ...`. | - | note for the runbook |

## Clean re-run prerequisite found 17:1x
| 75 | Stale code in the background role | Background (pid 1996) started 12:50 on 42924b7b and never restarted, while the API restarted 15:22 on 514113f1. Python does not reload, so every live background alert today (13:45, 14:25 SENSEX, 15:00 monthly, 15:05 Friday carry, level watches) ran the PRE-FIX approaches.py (A-01 in-the-money pick, issue 31) through playbook_eval. Today's live alert rows are evidence for 42924b7b, not for today's code. | - | ops fixed 17:15: 1996 stopped by PID, background restarted on 514113f1 (launcher 7712, role 6116, FEED_MODE=bus, LIVE_MARKET=1, REDIS_URL 6380; log background-1106-evening.log). Launcher fix (issue 14) must restart every role on a code move. |

## Phone width re-check after hours (6 Nov 18:45-18:53 IST, code 514113f1, 400 px same-origin iframe, 49 pages)
Method: every static route loaded in a 400 px iframe (window resize did not take; the first sweep measured 1,521 px and was discarded).
- 46 of 49 pages fit: no sideways page scroll. The section tab strip (UL w-max, 629 px) scrolls inside its own bar: acceptable.
- Issue 50 STILL OPEN: Strategies > Adjustments > Playbooks 429 px on 382 px visible; "Reason for this change" box `field w-96` = 384 px.
- Issue 54 STILL OPEN: Positions > Paper tab 535 px on 382 px; three 144 px action columns. (Not seen by a default-tab sweep: tabs must be opened.)
- Issue 53 unchanged: Opportunities table min-w-[640px] scrolls inside its box; page itself fits.

| # | Where | What | Blocks IC test? | Status |
|---|---|---|---|---|
| 76 | Settings > App settings, phone width | Page 457 px on 382 px: every section's 7-column table (Setting/Value in force/Unit/Default/Since/Set by/What it changes) spills 6-72 px past the screen. Not on the IC path. | no | after market (minor) |

Not re-checkable tonight: builder and compare at phone width with real legs (issue 70: builder blank after close) -> stays on the Monday list.

## Test-data re-run of the live rows (6 Nov evening, code 514113f1, scenario copy 8766 on ofo_dev, scenario-marked)
Owner standing rule (30 Oct): market-state rows are proven on the scenario library + one real-chain anchor. This replaces
the live rows where the library has a path; Monday keeps only the real-chain anchor (SENSEX / monthly chains, live feed).
- PATH-01 (strategy 101, 19:0x): T-01 flags first at frame 6 (0.4703 % vs 0.5 %), nothing at frame 5 -- matches the path.
  A-01 (issue 31) PASS: at spot 23,392 rolls the untested put spread up (BUY 23150 PE 18.45, SELL 22950 PE 4.60, SELL
  23250 PE 35.15, BUY 23050 PE 9.30); new short 23250 is 142 pts OTM; credit (35.15+4.60-9.30-18.45) x 130 = Rs 1,560 =
  screen. A-02 / A-06 refused with the cost reason (Rs 1,820 / 1,313 > Rs 566.30 limit). Profit left / loss left move
  exactly with P&L (e.g. P&L -812.50 -> profit left 5,921.50+812.50 = 6,734.00).
- PATH-31 (strategy 102, 19:55-19:59): expiry day 14:40-15:20, stage "Last day" on every frame; T-09 cheap shorts true
  (0.05 < 2); T-10b true; A-27 = buy back both shorts (23150 PE, 23500 CE) PASS; A-35 time exit = close all four PASS;
  15:00 day.beforeHoliday flag PASS (10 Nov is Diwali-Balipratipada in market_calendar.json).
- Batch stopped at PATH-17 by Claude Code's low-memory reaper (20:00, 2.0 GB free of 15.7 GB). PATH-17/18/40/10/11 NOT run.
- Re-run after the reaper (OK from the owner), 20:06-20:54, SETTLE 35 s per frame, each path on a fresh scenario copy:
  - PATH-17 (strategy 104, stale prices): every rule "not checked: prices stale or missing", state PAUSED, P&L blank.
    PASS for the check. Compare still prices approaches on the 10-minute-old option prices with no warning: issue 79.
  - PATH-18 (strategy 105): T-03 first at frame 2 (0.3655 vs 0.35), as the path expects. PASS.
  - PATH-40 (strategy 106): T-01 first at frame 6 (0.4703 vs 0.5), T-03 + S-02 at frame 8. PASS. A-01 new short stays
    OTM on every frame (spot 23,350 -> 23200 PE; 23,508 -> 23400 PE). The second adjustment and T-18 were NOT placed by
    this runner; they stay on test_ic_second_adjustment (DB test).
  - PATH-10 (strategy 107, up sweep): S-02 f6, T-01 + T-09 f8, T-03 f9, 2x-credit stop f11, T-02 f13, T-06 f17. A-01
    rolls the put spread up, short always OTM (spot 23,300 -> 23150 PE). PASS. The frames differ from the worker test
    (T-02 14, T-06 18, stop 18) only because the test seeds the fixture entry (3 Nov, credit 5,421, 2x = 10,842) and
    this run entered at frame-0 prices (credit 2,437.50, 2x = 4,875; f11 loss 5,505.50 > 4,875). Checked, not a defect.
  - PATH-11 (strategy 108, down sweep): T-09 f6 and S-02 f7 exactly as the path expects; T-01 f8, T-03 f10, stop f13,
    T-06 f18. A-01 rolls the call spread down, short always OTM (spot 22,900 -> 23050 CE). PASS.
  - DB tests with the scenario copy stopped (21:2x-21:47, db_run_fresh on the live tree): test_ic_outcomes_paper 10 passed
    (act on / completed / partly / lapsed; replaces the VOID run); test_adjustment_opportunities 15 passed (dismiss with a
    reason); test_ic_second_adjustment 1 passed + 1 xfailed (second adjustment placed; T-18 one record and only exit /
    reduce offered at 2 of 2 are proven; the xfail is issue 81).
  - Strategy names come back as quoted text ("SCN PATH-11 IC"): by design (stored_form.shown_name, ADR-003). Not a defect.
- test_ic_outcomes_paper (act on / completed / partly / lapsed): 6 failed, 4 passed in 8 s -- all 6 are
  TooManyConnectionsError for role ofo_app (live roles + scenario copy pool 3 + test on one role limit). Environment, not
  the product: the result is VOID, re-run with the scenario copy stopped. test_adjustment_opportunities: not run (reaped).

| # | Where | What | Blocks IC test? | Status |
|---|---|---|---|---|
| 77 | Compare approaches: spot lag | After the price moves, POST adjustment-approaches keeps the previous spot for 6-30 s while the check and paper P&L update at once (measured: frame 9 -> 3, approaches still 23,392 @ 11:46 at +6 s, 23,335 @ 11:34 at +32 s). Spot time is shown, so not silent. Live: compare can price off a spot up to ~30 s old. | no | after market (spot cache TTL; say "prices from hh:mm:ss" next to the cost) |
| 78 | T-07 / S-12 reason text at zero max profit | A condor entered at 0.05 per leg (max profit 0) shows "Max profit not finite (unlimited or multi-expiry)" -- false: it is finite and zero. Edge case (test entry at expiry-day prices). | no | after market (wording: "Max profit is zero, so % of max profit cannot be computed") |
| 79 | Compare approaches on stale prices (breaks ADR-015; decided ADR-272) | PATH-17 frame 0 (strategy 109): chain says "stale since 11:35 IST" at 11:45 and the check withholds every rule, yet POST adjustment-approaches prices A-01 etc. from those option prices with warnings [] on every approach; only the spot block says "feed: its last price is too old" (spot re-read by a one-time request). A user can compare and prepare a roll on 10-minute-old premiums with no stale label on the cost. | no (paper) / yes before real orders | after market (each approach carries a stale-price warning, or compare refuses like the check) |
| 80 | A-01 trades the same contract twice (DECIDED owner 7 Nov 00:5x: one combined order, ADR-274) | PATH-40 frame 12: A-01 lists BUY 23150 PE (close the short) and BUY 23150 PE (new long) as two trades. Outcome is right; two orders of one contract cost a second brokerage (Rs 20) and a second fill risk. Not checked whether Prepare merges them. | no | after market (net the same contract into one trade) |
| 81 | T-19 missing at the adjustment limit | test_ic_second_adjustment (xfail strict, parked r4-run3): at 2 of 2 adjustments, stage Middle, the check reply lists T-01, T-13, T-03, T-16, T-10b, T-18 and NO T-19 row at all (not even "not checked"), with rates seeded. A rule that silently disappears breaks "every ON rule shows a result". Cause not measured. | no | after market (needs development) |
| 82 | Builder ready-made panel after a failed load | Scenario 5174, 21:5x: the panel's GET catalogue/NIFTY/expiries answered 500 (TooManyConnectionsError, role ofo_app shared by live roles + scenario copy: environment). Result on screen: expiry box empty, all 15 cards greyed, and the error text sits at y 1,445 px, below every card (screen 614 px); no Retry, only a page reload. Same class as the Undo-far-below fix of ADR-271 (5). | no | after market (message next to the expiry box + a Retry button) |

Owner 6 Nov ~22:5x: test as a PC web page only, not mobile. Phone-width issues 50, 53, 54, 76 are PARKED (mobile out of scope), not open defects; no more phone checks.

## Desktop UI pass on test data (6 Nov 22:2x-23:1x, Chrome 5174 -> scenario PATH-40, strategies 106 + 110, paper)
PASS: ready-made Short Iron Condor (46.60 x 65 = Rs 3,029); Multiplier 2 = Rs 6,058; Shift / Width / Hedge each step and
reverse; 4 quick strike clicks = 4 steps (old issue fixed); breakevens 23,153 / 23,447, max loss / profit and payoff
table hand-checked; greeks signs right; Add to Paper prefilled (issue 6 fix); "Use playbook as is" stores playbook 3;
manual roll in the builder (booked -1,017.25, cash -1,010.75, both hand-checked); Compare in 2.0 s (issue 29);
A-01 prepare opens the pending basket, new short 23350 PE OTM (issues 31, 34); second adjustment (booked +913.25);
at 2 of 2 T-18 flags and only no change / close part / exit offered; partial exit 1 of 2 lots (-3,311.75); 2-leg exit
(+2,541.50); Exit whole from Compare opens the exit dialog (issue 24), total -1,040 reconciles; leg stop and
conditional exit arm and cancel (firing needs the live market: paper_monitor runs only when the market is live).
NOT proven here: alerts raised by the scenario background (checks=0 after frame steps, issue 62), level watch and
stops firing, Pause (the route reads the real clock, so after 15:30 no time is accepted): live anchor / DB tests.

| # | Where | What | Blocks IC test? | Status |
|---|---|---|---|---|
| 83 | Ready-made IC vs default playbook | The builder's ready-made Short Iron Condor puts the shorts 90-110 pts from spot (23,290: 23200 PE / 23400 CE = 0.47 %), inside the default playbook's T-01 line (0.5 %). T-01 is "already true" from entry, so the first early warning never alerts for the default setup. | no | ALREADY DECIDED: ADR-262 (placement a per-user preference, default delta 0.20); not built yet (development on hold) |
| 84 | Adjustment history after Compare (as REQ-163 AC-1 says today; decided ADR-273, SPEC CHANGE AC-1) | An A-01 roll prepared from Compare is recorded as "Your own change" with no approach name. | no | after market (record the approach id) |
| 85 | Builder message after a strike step | "Your price for leg 3 was replaced by the captured price of 23450.00 CE" quotes the strike, not the price (66.35). | no | after market (wording) |
| 86 | Plan dialog after Add to Paper | An empty dialog box shows for 5-9 s before the plan appears; no loading text. | no | after market |

## Owner answers 6 Nov ~23:2x (question tool)
- Test data only: no live-market day; Monday 9 Nov live run dropped (replaces the 30 Oct "one real-chain anchor").
- Keep tonight's results; show in Chrome only what was not yet shown on screen.
- Background alerts on test data, paper stops firing, Pause after hours: log as gaps "not testable on test data yet",
  no code change (development on hold).
- Correction 23:2x: tonight Exit all on 110 was recorded as "adjustment 3" (3 of 2). ADR-255 (decided today) says Exit all
  does NOT count as an adjustment, partial exits do: the decision is not built yet (development on hold), not an open question.

## Desktop Chrome, test data, rule screens not shown before (6 Nov 23:3x-, owner "only what wasn't shown yet")
- PATH-17 stale prices (strategy 111), builder tracking panel: "Paper P&L paused - prices not live, as of 11:35", LTP "-",
  P&L blank, footer "stale since 11:35 IST": no false numbers. PASS for P&L.
| 87 | Stale prices: rule status not shown (breaks ADR-015; decided ADR-272) | Same screen: no line says the adjustment checks are off, although the server withholds every rule (USER_INPUT_149); TrackingPanel.vue never reads `withheld`. Compare (?adjust=111) says "Adjustment checks are running" in the Pause box, shows no stale word anywhere, and ranks credits from 10-min-old prices (e.g. "Most credit Rs 13,000"). A user believes the rules are watching when they are not. Extends issue 79. | no (paper) / yes before real orders | after market |
- PATH-13 IV up (strategy 112), builder panel: frame 0 P&L 0.00, vega -5.32 (short vega: right); frame 1 (IV 11 %) P&L
  -702.00 = +201.50 -526.50 -539.50 +162.50 (hand-checked); frame 3 (IV 13 %) -2,158.00; same as the script run. PASS.
| 88 | T-11 at exactly its limit (hidden passing rules break ADR-019 Q203 "every trigger shows rule, threshold, actual values") | T-11 is "IV changed >= 3 pts since entry" (cmp ge, inclusive). Frame 3: the chain shows ATM IV 13.00 on CE and PE, entry was 10.00, yet T-11 is not flagged (first flag at frame 4, +4). Cause not measured: the stored entry IV / the IV the check reads are not shown anywhere, because a rule that passes is not listed (only flags, already-true and not-checked appear). A user cannot see how close a rule is to firing. | no | after market: measure entry_atm_iv; show passing rules with value / limit |
- PATH-13 on screen, fresh condor 113: frame 4 shows "Your rule was triggered: Options' IV changed this many points since
  entry: 3.9994 pts (rule 3.0000 pts)" + "Review adjustment". PASS (display of an IV flag).
  Issue 88 cause measured: the IV the check reads sits 0.0006 pt below the chain's shown IV (3.9994 at a 4.00 move), so an
  exact-limit move (13.00 vs 10.00) reads 2.9994 and does not fire.
  Test-setup notes (not product defects): (a) a restart keeps the last frame index, so the background's first check of
  condor 112 ran at the path's last frame and recorded T-11 "already true when tracking started" (false for the user);
  (b) the chain served the previous frame's prices for >40 s after a frame change (issue 77 class, also on the chain),
  so condor 113 entered at IV-14 % prices. Both fixed in my setup scripts.
- PATH-14 IV crush day 1 (strategy 114, on screen): frame 0 credit 41.40 x 130 = Rs 5,382, P&L 0.00; frame 3 P&L
  +2,892.50 (-1,300 +2,561 +2,808 -1,176.50), T-07 53.74 % >= 50 and S-12 "Big win early" 53.74 % >= 40 flagged with
  "Review adjustment"; frame 4 P&L +3,796.00 (70.53 %), T-11 3.9088 pts >= 3 flagged. Same as the script run. PASS.
  Prices are stamped one second before each frame's clock (11:13:59 for frame 4): no lag here (my earlier "frame 2"
  reading was wrong).
| obs | T-11 is two-sided | T-11 flags an IV FALL as "Your rule was triggered" (abs change). For a short condor a fall is profit, not risk; here T-07 already flags take-profit. Trader view; no change proposed now. | no | observation |
| obs | Expiry label in test mode | Builder shows "9 Nov (2 days)" on a 3 Nov test frame: days counted from the real date, not the test clock. Test copy only. | no | observation |
- PATH-15 gap (strategy 115, on screen): frame 0 Thu 09:20 23,100 P&L 0.00, nothing true; frame 1 Fri 09:20 23,300
  (+0.87 %) P&L -1,943.50 (-708.50 +2,093 -4,361.50 +1,033.50, hand-checked), S-02 "Trending day" 0.2188 flagged.
| 89 | = ISSUE 65 again (gap day): rules shown "already true when tracking started" | Same frame: T-13 gap 0.8658 % (0.75), T-01 0.4292 % (0.5), T-03 0.3517 (0.35) are grey "Already true when tracking started", although none held at the Thursday entry (23,100). Measured: the background never checked 115 (not in scn-PATH-15-bg.log), so no rule memory exists; the screen check writes no memory (ADR-237 (6)) and in test mode takes the entry state from the fixture (3 Nov 10:00, 6 days left) instead of the paper entry. Why each rule evaluates as held on that entry state: not measured. The real background raises T-13 at this frame (test_ic_rules_worker_paths PATH-15 passed on 514113f1), so live alerts are not affected; the screen is wrong until the background's first check. | no (test mode) | after market: measure held_at_entry for 115; screen should say "not checked yet" before the first background check |
- Correction 00:2x: condor 112's false "already true" (T-11, frame 4) was blamed on my setup; the stronger explanation is
  issue 65 (same class as 89). Issue 65 has now recurred on PATH-12, PATH-14 (6 Nov 15:xx), PATH-13 (112) and PATH-15
  (115); condor 113, checked by the background at frame 0 first, flagged correctly. Class: the "already true" baseline
  comes from the first STORED check (or the fixture entry in test mode), not from the real paper entry. Most serious open
  defect for a trader: a real warning turns into a grey line. 2nd+ occurrence: an independent root-cause review comes
  before any fix round (development on hold).
- PATH-12 time sweep (strategy 116, on screen): frame 0 Tue 10:30 stage Early, credit 41.60 x 130 = Rs 5,408, P&L 0.00;
  frame 3 Fri 15:00 stage Middle, P&L +3,139.50 from decay at a flat spot (-1,469 +2,749.50 +3,139.50 -1,280.50), T-07
  58.05 % >= 50 flagged, weekend-carry rule flagged. PASS on logic and money.
| 90 | Weekend-carry flag wording | The Friday 15:00 carry flag shows the raw rule id "day.beforeWeekend.1500.0" as its only text (no words, no value). Same likely for day.expiry.1430 and day.beforeHoliday rules. | no | after market (catalogue wording for day.* rules) |
- PATH-12 cont.: frame 4 Mon 09:30 expiry, stage "Last day", P&L +5,408.00 = full credit (every leg 0.05), T-07 100 % >= 80
  and T-09 0.05 <= 2 flagged on screen; frame 8 14:30 T-10b flags (check). Background raised alerts 186 T-07 and 187
  weekend carry for 116 (written at the Mon 09:30 frame: the frozen test clock passed no candle close on Friday; live the
  clock runs). Correction: background alerts DO work on test data once the test clock passes a candle close (gap 1 was
  wrong for PATH-12; PATH-40's minute frames passed none).
| obs | Compare clock on unchanged prices | Frame 8 (14:30): every price equals the 09:30 one, so the chain keeps last_price_at 09:29:59 and Compare dates itself 09:30 and refuses the time exit "from 14:30" while the check flags T-10b at 14:30. Test data only (live prices tick); A-35 was shown working at 14:31 on PATH-50. | no | observation |
| obs | A-26 max profit Rs 29,43,139 | "Close the untested side for profit" buys back only the short 22800 PE and keeps the long 22600 PE: its max profit at NIFTY 0 is 22,600 x 130 = Rs 29,38,000 + the call spread credit. Correct, but reads like an error to a user: say "if NIFTY falls to 0" or cap the shown range. | no | observation (wording) |
| obs | Expiry-day test data | PATH-12 frames 4-8 price every leg 0.05 from 09:30 with spot 300 pts from each short: real premiums would not be 0.05 with 6 h left. Fixture limit (same as the T-19 parked note). | no | observation |

## Issue handling per the owner's directions (re-checked 7 Nov 00:2x against the handover "Standing owner instructions")
Development on hold: requirements + issues only; fix only what needs live market data (none tonight: all on test data);
behaviour calls decided with a decision row. Tonight: ADR-272 (79, 87), ADR-273 (84, SPEC CHANGE REQ-163 AC-1) written;
88 and 90 / 85 are breaches of existing rows (ADR-019 Q203, ADR-003 wording), no new row; 80 is an owner call (orders);
65 / 89 class (2nd+ occurrence): independent root-cause review dispatched 7 Nov 00:1x (read-only), result to follow.
- PATH-16 expiry close (strategy 117, on screen): 14:20, spot 23,380 (20 pts from the 23400 CE short), stage "Last day":
  T-14 gamma "Loss from a 1% move (gamma) at least this % of margin: 3.1016 % (rule 2.0000 %)" flagged; S-02 flagged;
  T-01 0.0855 % and T-09 0.05 "already true" (correct here: the condor was entered at this frame). 14:30: the check
  flags T-10b and day.expiry.1430.5. PASS for the rules.
| 91 | Compare dates itself by the last price, not the clock | 2nd time tonight (PATH-12 frame 8, PATH-16 frame 1): the check reads 14:30 and flags the 14:30 rules, but Compare shows "Spot ... 14:20:00 IST" (spot and prices unchanged since) and refuses the time exit "offered on expiry day from 14:30". Live risk: low while the index ticks, real if the feed pauses at 14:30 on expiry day (the exit is refused when it is due). A-35 was offered on PATH-50 at 14:31 when prices changed. | no | after market: time-gated approaches read the market clock |

## Issue 65 class: independent review result (7 Nov 00:3x), verified by me
Root cause (confirmed): the "already true" baseline is chosen at the FIRST check, not stored at entry. The background
write (background.py:1207, record_check without the scenario -> adjustment_check.py:535-536 "entry = state") and the
background's own check (background.py:1187) take the current state as the entry; held_at_entry can never change
afterwards (playbook_store.py:250-252, migration 0031 trigger). Verified: stored rows for 115 = T-01, T-03, T-13
held_at_entry true, exactly the three rules shown grey at the gap frame. Reaches LIVE strategies: e.g. a condor filled
at 15:27, first checked 09:16 next day after a 0.9 % gap -> the gap warning never fires. Not a test-data effect.
Severity: highest open (a real warning is silently lost). Finding: knowledge/findings/rule-entry-baseline-taken-at-first-check.json.
Fix waits for "start development" (not a live-data-only fix). Proposed fix: store the baseline once at tracking start,
one function for all callers, repair rows written after a crossing, three new tests (detection was blind: F-71 tests pass a fixed entry; the worker test uses a fake recorder).
Reviewer point 4 (a strategy with no stored baseline): follow the existing module docstring ("counts as not held"), no new decision.

## 7 Nov 00:3x
- Owner asked "start development now, and with what first?": answered "[No preference]". The hold stays (the owner's rule
  needs the words "start development"). Ready first round when it starts: issue 65 class (store the rule baseline at
  entry + 3 tests) and ADR-272 (stale prices on Compare / tracking panel), then a test-data re-run of PATH-12/13/15/17.
- Full pre-push gate started 00:31 (PID 17456, log prepush-full-1107.log) on feature/adjustments b94c2484; push follows only on PASS.
