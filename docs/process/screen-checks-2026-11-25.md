# Screen checks and issues: live market test 2026-11-25

Branch `fix/ic-live-test-1123` at a3f2b9e9, on the owner's PC, live market, paper trades only. Uncommitted notes file.
Standing rule for this session (owner, 09:47 IST): every step is done on screen as a user would; nothing from the
backend without the owner's explicit OK; issues are noted here, not fixed; fixes start after the market closes.

Ids: S-01 onwards (new findings today). Screen checks of ledger rows cite the D-id.

## Issues and requests

#### S-01 [MISSING FEATURE] No way to select several strategies and delete them at once
- Trader sees: My Strategies has one Delete per row; clearing 30 test strategies takes 30 separate Delete + confirm
  rounds, and Completed strategies are on a different list from Drafts and Running ones.
- Asked for (owner, 09:47 IST): a select-all (and select-several) option that deletes the chosen strategies in one go.
- Where: My Strategies (and the Completed list)
- Seen: 25 Nov 09:44, while clearing the test strategies
- Class: 5

#### S-02 [DEFECT] Deleting a Running paper strategy failed once with a raw server error, then worked on retry
- Trader sees: Delete on "T1123-C9 pm 4lot" (Running, paper) gave "An unexpected server error stopped this request
  (reference ERR-6960F002)."; the second Delete on the same row worked ("Strategy deleted. Undo").
- Where: My Strategies > Delete
- Seen: 25 Nov ~09:50, once (helper's report; screenshot not kept)
- Unverified: cause unknown (server log for ERR-6960F002 not read: backend read needs owner OK)
- Class: 4

#### S-03 [UNCONFIRMED] "Held IC k10" cannot be deleted though other paper strategies with orders can
- Trader sees: "Orders were already sent for this strategy, so it cannot be deleted." on Held IC k10 (Completed),
  while 29 other paper strategies that also had orders were deletable.
- Where: Completed Strategies > Delete
- Seen: 25 Nov ~09:51
- Unverified: whether Held IC k10 had a real (Zerodha) order, which would make the refusal correct
- Class: 5
- Resolved 11:06 (code + run log, no app call): Held IC k10 (id 137) was typed in on 12 Nov 15:14 during the GC-TRACK1
  item k10 test of "Held at my broker" (entry 12 Nov 15:00, broker Zerodha; docs/process/gc-track1-run-log.md line
  71). A held condor is a REAL position stored as practice orders, and ADR-292 makes it never deletable
  (strategy_store.py `_DELETABLE_SQL`). The refusal is right; its WORDS are wrong: no order was sent by the app. Better:
  "This strategy is marked as held at your broker, so it cannot be deleted." Class stays 5 (wording).
- Owner saw it (11:0x) on Home > Overview after the clear-out, so "everything blank" was not reachable: a held
  strategy can never be removed, and the screen gives no way to tell a trader that or to hide it. Its closed result
  also feeds the Paper header total (S-15).

#### S-04 [DEFECT] Clicking Delete moves "Rename" under the mouse; the confirming Delete jumps elsewhere
- Trader sees: on Completed Strategies, clicking a row's Delete (far right) turns the row into a tall confirm box: the
  "Rename" link now sits exactly where Delete was, and the confirming "Delete" / "Cancel" move to the left, two lines
  lower ("Practice orders were placed for this strategy. Delete it? Its practice record leaves the lists, and you can
  Undo right after."). A second click at the same spot opens Rename instead of confirming.
- Where: Completed Strategies (and My Strategies, same control) > Delete
- Seen: 25 Nov 09:54, every row; the cause of the helpers' Rename clicks
- Class: 5

#### S-05 [DEFECT] My Strategies shows a bare "Loading..." for several seconds even when the list is empty
- Trader sees: "Loading..." alone for over 1.5 s (gone by 4.5 s), then "You have no saved strategies yet."
- Where: Strategies > My Strategies
- Seen: 25 Nov ~09:58, once, list empty
- Class: 4

#### S-06 [BASIS-LABEL] Builder shows max profit/loss after charges but breakevens before charges, with no basis line
- Trader sees (iron condor S 25550 PE / B 25450 PE / S 26050 CE / B 26150 CE, 1 Dec, 1 lot, Get 3,877 = 59.65 x 65):
  Max Profit +3,619 and Max Loss -2,881 (both = before-charges figure minus ~258 charges), but Breakeven
  "25,490 (-1.0%), 26,110 (+1.4%)" = 25550 - 59.65 and 26050 + 59.65, i.e. before charges (after charges they
  would be ~25,494 / ~26,106). No line says which basis each uses.
- Where: Strategy Builder summary (a plan, before Add to Paper)
- Seen: 25 Nov 10:03
- Class: 2 (same class as D-16, which fixed it for paper trades only)

#### S-07 [DEFECT] The "Strategies" word in the top menu does nothing; only the small arrow opens the menu
- Trader sees: clicking "Strategies" twice did not open the menu (and did not navigate); clicking the arrow beside it
  did. The Strategy Builder then took over 3 s to appear after its menu item was clicked.
- Where: top navigation
- Seen: 25 Nov ~10:01
- Class: 5

#### S-08 [DEFECT] An unsaved strategy in the builder is lost on leaving the page, with no warning
- Trader sees: a fully built 4-leg iron condor (not yet saved) was gone after the owner opened other pages and came
  back; no "you have unsaved changes" prompt, no draft kept.
- Where: Strategy Builder, leaving the page by the top menu
- Seen: 25 Nov ~10:08 (owner)
- Class: 3

#### S-09 [DEFECT] Pick from Option Chain shows dashes for every price for 4-8 seconds after opening
- Trader sees: all LTP, IV, OI and delta cells read "-" for over 4 s on the second opening (first opening: "Reading
  strikes..." then prices within ~4 s). B/S buttons are already clickable on the dash rows.
- Where: Strategy Builder > Pick from Option Chain
- Seen: 25 Nov 10:11
- Class: 4

#### S-10 [MISSING FEATURE] No rupee profit or loss exit; the plan takes only % of max, and only alerts
- Owner asked (10:29): exit when profit is more than Rs 1,000 per lot, and when loss is more than Rs 400 per lot.
- Trader sees: the plan's Target and Stop accept only "% of max profit / max loss" (before charges, which the dialog
  does not say; only the Plan block after saving says "before charges"). Reaching them raises a suggestion, not an
  exit. The only automatic exits are index-level conditional exits and leg price stops. Set as Target 25.7 % (Rs ~1,002
  of 3,900) and Stop 15.4 % (Rs 400.40 of 2,600). Related parked row D-34.
- Class: 3
- TO DO (owner 10:40): discuss after market close today, then build. Owner's point: the plan already turns a % into
  Rs (Stop shows "Rs 400.40"), so a Rs input is the easy half. The missing half is the ACTION: today reaching Target or
  Stop only alerts; the ask is an automatic (paper) exit at a Rs profit or loss, like the index conditional exit.
  To settle in the discussion: before or after charges; per lot or whole trade; paper only or also real orders.
- Code read 10:45 (backend/ofo_app/paper_monitor.py `_fire`): ONE exit block already serves both index conditional
  exits and leg stops (claim the trigger once, price the open legs at live prices, record exit orders buys first,
  store the reason, raise the alert). It sits inside the monitor's `_fire`, fed only by "one quote crossed a level".
  The plan's Target/Stop are already checked by the background checker (it raises the alert today).
  Recommendation for the discussion: pull that block out as one "exit this paper strategy (these legs, this reason)"
  function; let the plan's Target/Stop call it when the user ticks "exit automatically"; P&L from the one engine
  (ADR-008), on the basis the user chose. Real orders: separate decision (real-order code frozen, ADR-281).

#### S-11 [DEFECT] "Customise triggers" in the plan dialog leaves the page and drops the unsaved plan
- Trader sees: in "When tracking starts: this strategy's plan", Customise triggers opened Strategies > Adjustments
  (Playbooks, "Rules for this trade only") with no warning; the plan was not saved and the dialog was gone on return.
- Seen: 25 Nov 10:30
- Class: 3

#### S-12 [DEFECT] Plan dialog hints do not follow the typed values and show no rupee amount
- Trader sees: after typing Target 25.7 and Stop 15.4, the hints still read "50 % of max profit" and "50 % of max
  loss or 2x the credit received"; no Rs figure for either. After saving, the Plan block shows Rs 400.40 for the stop
  but no Rs figure for the target.
- Seen: 25 Nov 10:32
- Class: 5

#### S-13 [DEFECT] The plan offers a "Time exit" only on expiry day; no same-day time exit for an intraday trade
- Trader sees: "Time exit (on expiry day) 14:30"; for a 1 Dec trade opened 25 Nov there is no way to say "exit at
  15:15 today".
- Seen: 25 Nov 10:29
- Class: 3

#### S-14 [DEFECT] Live Strategies card cannot be opened: no way from it to the strategy, its stops or its exit
- Trader sees: the "IC 1125 intraday, NIFTY Running" card shows figures only; clicking the name does nothing; no
  Open / Stops / Exit control. The card also calls paper fills "Planned entry". Took ~7 s to load ("Loading this
  strategy...").
- Seen: 25 Nov 10:34
- Class: 5

#### S-15 [DEFECT] Positions > Paper header total includes a closed trade that the list hides
- Trader sees: the header "Total P&L (after charges)" and "Booked" figures differ from the only listed trade, IC 1125
  intraday (-272.10). The gap is exactly the closed Held IC k10's net result; "Show closed positions" is off.
  (Header figures left out: Held IC k10 is a held-at-broker entry, and the repo is public.)
- Seen: 25 Nov 10:35
- Class: 2

#### S-16 [DEFECT] The plan's loss stop alert fired, then lapsed after 3 minutes
- Trader sees: "Loss reaches this % of max loss: 15.5750 % (rule 15.4000 %) - Lapsed at 11:05:01 IST, fired 11:02:20
  IST". A trader away for 3 minutes never sees the stop he set; the loss later grew (25400 PE leg -1,040 at 11:12).
- Seen: 25 Nov 11:12
- Unverified: whether "lapsed" means the loss fell back under 15.4 % (rule no longer true) or a time-out
- Class: 3

#### S-17 [FINDING + MISSING FEATURE] Playbook levels: most of the owner's model exists; three gaps
- Owner's model (11:31): several standard playbooks for all users; a user copies one, edits it, saves own versions;
  picks standard or own when creating a strategy; the chosen one applies per strategy and can be customised for one
  strategy without touching others or the source.
- Today (spec REQ-158, ADR-214 (4b); tables in alembic 0031: adjustment_playbooks [user_ref NULL = system],
  adjustment_playbook_active [one per user and type], strategy_adjustment_plans [strategy_id PK, own body COPY,
  playbook_id pointer]):
  - Copy a standard one, edit, save as own, many allowed: WORKS ("Save as new playbook", duplicate, rename, delete).
  - Per-strategy copy, edited without touching other strategies or the playbook: WORKS (the strategy's plan is a
    copy; "Rules for this trade only" writes only that trade's plan).
  - Pick standard or own when starting a strategy: WORKS, but only among playbooks of that strategy's TYPE.
  - Several STANDARD playbooks per type: NOT BUILT (REQ-158: "one read-only system playbook per strategy type").
- Gaps: (1) several standard playbooks per type (e.g. "IC conservative", "IC intraday"); (2) a playbook is tied to one
  strategy type, so it cannot be offered for another type; (3) no "reset this strategy to its playbook" found
  (not fully checked). Also: the screens say "playbook" and "plan" for two levels without explaining the difference.
- Owner will explain how to build the standard versions. Discuss after close. Class: 3

#### S-18 [DEFECT] Home > Overview "Open in Strategy Builder" never opens the strategy: the link carries no id
- Trader sees (owner 12:02, reproduced 12:03): clicking "Open in Strategy Builder" on IC 1125 intraday opens an empty
  builder ("No draft strategy is open. Add a leg to start one."), still empty after 10 s; URL /strategy/builder.
- Cause (read, not changed): frontend/src/pages/HomeOverviewPage.vue:85 is
  `<router-link to="/strategy/builder" ...>` for every row, with no `?strategy=<id>`; both rows link to the same
  empty builder (browser shows href="/strategy/builder" on both). The network log shows no request for strategy 168
  at all. At 11:12 the same click appeared to work only because the builder still held strategy 168 from earlier in
  the same browser session, not because the link named it. Working links elsewhere use /strategy/builder?strategy=168.
- Related slowness: when the builder does load a saved strategy it takes ~5-6 s before the legs and figures show.
- Class: 3

### Stop scenarios on IC 1125 intraday (owner asked 12:50; run 12:51-12:58)

Sequence: D-01 crossed-level test; call side closed by two leg stops (26000 CE below 142.30 fired 12:53:00 at 140.70;
26100 CE below 110.00 fired 12:54:05 at 105.10); put side closed by an index conditional exit (Above 25,750 /
Below 25,720 set ~12:56; fired 12:57:44, "NIFTY was at 25,719.75"; 25500 PE out at 135.00, 25400 PE at 104.30).
Final: Completed, result -670.42 after charges (booked before charges +1,004.25 - 1,014.00 - 2,197.00 + 1,797.25 =
-409.50; charges 260.92).

#### S-19 [DEFECT] The Stops panel asks for a NIFTY level but never shows NIFTY's current value
- To type a sensible level the trader must leave the page (Overview showed 25,735.00 at 12:57:26). Class: 5

#### S-20 [DEFECT] A leg stop's reason says the index value "was not available" while NIFTY was live
- Closed rows, Orderbook and Alerts: "Stop-loss: NIFTY 1 Dec 26000 CE crossed below 142.30; the index value at that
  moment was not available"; same for 26100 CE. NIFTY was live all along (builder 25,744.90 at 12:54:41); the index
  conditional exit DID record "NIFTY was at 25,719.75". D-22's fix covers index exits only. Class: 3

#### S-21 [DEFECT] After a leg exits, the plan's % stop silently re-bases: Rs 400 became Rs 757
- Plan block at 10:32: "Stop: loss of 15.4 % of max loss (Rs 400.40)"; at 12:55, after the call side closed:
  "Stop: loss of 15.4 % of max loss (Rs 756.76)" and "2 x credit (Rs 3,172.00)" (was Rs 7,800). The owner's stop
  (exit at Rs 400 loss) nearly doubled with no message. The plan also still reads "Iron condor: system default" on
  what the builder now calls a "Bull Put Spread". Strengthens S-10 (Rs stops). Class: 2

#### S-22 [MISSING FEATURE] Exiting one short leg raises the max loss four-fold with no warning
- After the 26000 CE short stopped out, Max Loss went from -2,860 to -12,005.51 (a naked long 26100 CE plus the put
  spread) and Max Profit to "No fixed maximum". Nothing warned when the leg stop was set or when it fired. A trader
  setting a stop on a short leg should see "if this fires, max loss becomes Rs X". Class: 1

#### S-23 [DEFECT] "Stops on this strategy" keeps showing a fired stop as "armed" until the page reloads
- The 26000 CE stop read "armed" for several seconds after its row had closed; the 26100 CE stop likewise; both read
  "fired" only after reopening the page. Class: 5

#### S-24 [UNCONFIRMED] Leg stops were accepted with the price already past the level
- 26000 CE "below 142.30" saved while the row showed 141.35; 26100 CE "below 110.00" saved while it showed 105.95.
  Both fired within ~10 s. Prices were falling fast, so the price at save time is not proven. D-01 says a leg stop
  is judged on its own live price. Next: set a leg stop clearly past the live price on a quiet leg. Class: 1

#### S-25 [DEFECT] Orderbook Qty and Price columns run together
- "65101.20" for 65 units at 101.20; "65 76.65" spaced only where the price has 2 digits. Class: 5

#### S-26 [DEFECT] The Stops panel moves while you type: a live refresh shifted it 16 px mid-entry
- Typed values landed in the wrong box / Save missed on the first try; the same layout shift class as S-04. Class: 5

#### S-27 [FINDING] After one side exits, the adjustment plan is not re-thought for what is left
- After the call side closed, no new adjustment suggestion appeared; every rule line read "Lapsed" (the 11:20 "spot
  within 0.2388 % of a short strike" lapsed at 12:05). The plan kept its iron-condor rules and name ("Iron condor:
  system default") on what is now a Bull Put Spread. Owner asked (12:50) whether adjustments happen properly when one
  side exits: today nothing changes. To settle after close: should a side exit re-type the strategy and offer the
  rules of the new shape, or keep the original plan? Related: S-21, S-22, OD-3. Class: 3

#### S-28 [DEFECT] A Completed paper strategy still offers "Add orders"
- Positions > Paper with closed shown: IC 1125 intraday, Completed, still has "Add orders". Class: 5

#### Also seen
- Held IC k10's block shows the broker in quote marks: "Zerodha" (open ledger row D-58 class).

### Not yet checked today (carry into the next test window)
- D-22: Alerts > History tab. D-24: tracking panel on screen. D-60, D-09 (exit dialog) and the other
  "Fixed, not tested" ledger rows.
- S-24 retest: a leg stop set clearly past the live price on a quiet leg (should be refused, like D-01).
- S-02: server log for ERR-6960F002 (needs the owner's OK for a backend read).
- S-16: whether "Lapsed" means the rule stopped being true or a time-out.

### Lessons from today's testing (process, not product)
- **Presence-only tests hid S-18 (owner 12:17: "This is not acceptable").** The Overview link test checks the link
  exists, never where it goes; no test clicks from one page to the next. My 11:12 screen pass was luck: the builder
  still held strategy 168 from earlier. Practice adopted: after every navigation, read the address and the strategy
  name from a fresh page load. Fix of the test gap is OD-4 (waits for the owner's word).
- **Backend reads during a screen test (owner 09:5x: "don't delete from the backend").** Read-only server lists were
  read as backend work. Practice: every action and check by mouse; any server read is announced first.
- **Helper clicked Rename instead of Delete.** Cause was S-04 (the control moves under the mouse), and a brief that
  assumed one page of 30 rows. Practice: re-read the screen after every click that changes layout.
- **I misread the plan basis** (assumed after charges; it is before charges, max loss 2,600 / max profit 3,900). The
  dialog never says which (S-10, S-12).
- **A % stop has a moving base (S-21).** Question to ask of any stop: "if part of the trade closes, does it still mean
  the same rupees?"

### Count (25 Nov, 14:22 IST)
28 issues (S-01 to S-28): 20 defects, 3 missing features (S-01, S-10, S-22), 1 basis-label (S-06), 2 findings
(S-17, which also holds missing features, and S-27), 2 unconfirmed (S-03, resolved as wrong wording; S-24). 5 owner decisions (OD-1 to OD-5), all
waiting to be written into spec/ after close. 10 ledger rows screen-checked: 9 pass, 1 partial (D-22).

## Owner decisions taken during the test (write into spec/ after market close)

- **OD-5 (25 Nov 12:5x IST, question tool): live "Plan watch" box beside the live P&L.** Answer: "Box beside live
  P&L (Recommended)" over a separate Plan tab or both. Owner's idea (12:46): every value a plan can trigger on is shown
  live on screen. Content: one line per trigger (profit target, loss stop, each adjustment rule, Stops-panel index
  exits and leg stops): fires at / now / distance / state (watching, fired, lapsed), in Rs and %, live, from the one
  engine (ADR-008). Shown only when the strategy has a plan; else "No plan: nothing is watched" (OD-3). Where: next to
  the live P&L on the builder and on the Positions row. Today only fired rules show a value, in %, at the bottom of
  the builder page (tracking panel), and the Stops-panel exits are not in it. Spec basis: none (new). Discuss and
  build after close.
- **OD-4 (25 Nov 12:17 IST, owner in chat): test coverage must cover every link, button and function, and what
  each one DOES.** Owner, on S-18: "no test ever clicks through from one page to the next. This is a big gap. ... all
  links and all buttons and all functionalities should be tested by the test, so the coverage should be proper." And:
  "the test checks that the link exists, not where it goes. This is also a gap and it should be fixed in all the
  tests." Meaning: (a) every link, button and function has a test; (b) a test asserts the OUTCOME (where a link
  goes and that the target page shows the right strategy; what a button changes), never only that the element
  exists; (c) click-through tests for the journeys between pages (e.g. Overview / My Strategies / Positions / Live
  -> builder showing that exact strategy); (d) existing tests that only check presence are found and fixed, all of
  them. Evidence of the gap: frontend/tests/home.test.js checks `recent-open-N` exists, never its target. Owner:
  "do not do anything. I will let you know when to do it." Status: recorded only.
- **OD-3 (25 Nov 11:46 IST, owner in chat): only a strategy's own plan applies; no fallback to any playbook.**
  Owner: "the main playbook should not be applicable to any open strategies. If ... there is no plan created, then
  that means the user does not want anything to happen with that strategy. ... if a plan is associated with a
  strategy, only then it is applicable. Otherwise, no default referring to the playbook." A playbook is only a source
  to COPY from when a plan is created. Today (adjustment_check.py `resolve`): saved plan first, else the user's ACTIVE
  playbook for the type, live, else the system default. SPEC CHANGE to REQ-158 (strategy plan > chosen playbook >
  system default) and REQ-161 ("No plan saved yet: default rules apply"). Consequence to confirm in the discussion: a
  strategy with no plan then gets no adjustment suggestions and no target/stop alerts; its index conditional exits
  and leg stops (Stops panel) are separate and keep working.
  CONFIRMED by the owner 11:50 IST: "a strategy with no plan would get no adjustment suggestions and no target or
  stop alerts." Suggested screen line for the discussion: "No plan: nothing is watched for this strategy".
- **OD-2 (25 Nov 11:02 IST, owner in chat): exits and their checks are stand-alone functions.** Owner, verbatim:
  "exit should be a stand-alone function ... P&L check and other similar checks should also be stand-alone
  functions". Meaning: (a) ONE exit function ("exit this strategy: these legs, this reason") that any trigger calls;
  (b) each condition is its own stand-alone check (index level, leg price, P&L amount, P&L %, time of day, ...) that
  only answers "met / not met" and then calls the exit function. Today the exit block sits inside
  paper_monitor.py `_fire` and is reached only from a price crossing; the plan's Target/Stop check lives in the
  background checker and only alerts. Discuss after close with S-10 and S-13; then into spec/.
- **OD-1 (25 Nov 10:2x IST, question tool): Positions shows real and paper trades in ONE list.** Answer: "One list +
  safeguards (Recommended)". SPEC CHANGE to ADR-201 (2), which chose a separate Paper tab (28 Oct). Safeguards: a clear
  PAPER tag on every paper row (not just a small "P"); separate "Real P&L" and "Paper P&L" totals at the top, never
  added together (ADR-201's rule stays); All / Real / Paper filter buttons, default All; every exit confirm names
  "Paper" or "Real (Zerodha order)" in its title. Real rows still come from Zerodha first (ADR-016); grouping real
  contracts by strategy is part of the work. Build after market close. Not written to spec/ now: the owner's session
  rule forbids spec edits today; it becomes a new ADR (next free id at write time; a cloud session may be adding ADRs).

Noted for open ledger row D-52: the empty builder still says "start from a ready-made shape below" and no shapes panel
is shown (25 Nov 10:01).

## Screen checks of ledger rows (D-ids)

| D-id | Result | What the screen showed (25 Nov) |
|---|---|---|
| D-17 | Pass | Builder summary: "Time value at live prices, as of 10:03:32  -3,848"; the credit beside it reads "Get 3,877 ... At plan prices". Live 6-day condor, not 0DTE. |
| D-01 | Pass | Conditional exit "Above 25700" with NIFTY ~25,765: "Not saved: the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit." (POST 422, nothing stored). Leg-stop side: see S-24. |
| D-02 | Pass (exits) | Index exit recorded the buy-back of the short 25500 PE before the sale of the 25400 PE hedge ("exited 2 legs at 25500 PE at 135.00, 25400 PE at 104.30"). Entry orders are recorded as sent (sell first), as designed. |
| D-10 | Pass | Builder "Closed: booked P&L" rows: 26000 CE 156.15 -> 140.70 +1,004.25; 26100 CE 120.70 -> 105.10 -1,014.00; open rows separate. |
| D-22 | Partial | Reasons show on the closed rows and in Alerts without a click; index exit stores "NIFTY was at 25,719.75"; leg stops store "index value ... not available" (S-20). Alerts > History tab not opened. |
| D-23 | Pass | Orderbook Kind "Stop" on both leg-stop exits (12:53:00, 12:54:05); entries read "Open". |
| D-28 | Pass | Running while legs open; "Completed" on Positions > Paper after the last exit. |
| D-06 | Pass | Live card Max Profit +3,640.71 / Max Loss -2,859.29 / breakevens 25,444 / 26,056 = builder at the same minute (10:33). |
| D-33 | Pass | Funds & Margins: "Not enough funds. Paper trade: this practice order is still allowed; a real order of this size would be refused." Add to Paper stays enabled. |
