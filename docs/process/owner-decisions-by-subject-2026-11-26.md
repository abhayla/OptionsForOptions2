# Owner decisions 25-26 Nov 2026, by subject

Sources compared: ADR-326, ADR-327, ADR-328, ADR-329, ADR-330 (read-only). Ids are written ADR-point, e.g. 330-3 = ADR-330 point (3); "330-3+closed" = a dated addition inside point (3). Each id has one home subject; cross-references are in brackets. 16 subjects.

---------------------------------------------------------------------
## A. Decisions by subject
---------------------------------------------------------------------

### 1. Alerts and the bell
- 330-3 (25 Nov night): alerts are of two kinds; ACTIONABLE ones (plan loss stop crossed, profit target reached, adjustment rule fired) stay in Active until the user acknowledges and answers "exit" or "continue"; INFORMATIONAL ones are a short pop-up kept only in History.
- 330-3+closed (26 Nov morning): an actionable alert still waiting when its trade closes completely leaves Active and the bell and goes to History as "Closed by system: the trade closed at HH:MM".
- 330-3+plan-removed (26 Nov morning): an actionable alert still waiting when the user removes the plan leaves Active and the bell and goes to History marked closed by system because the plan was removed.
- 330-4 (25 Nov night): the bell counts the actionable alerts the user has not answered, and equals the rows in Active; informational messages never count.
- 330-4+Stops-fired (26 Nov morning): a fired Stops-panel exit whose paper exit is already done is INFORMATIONAL (pop-up, History, not on the bell).
- 326-5 (25 Nov): an adjustment pop-up for a rule already true at entry is not raised in the first 5 minutes after entry; after 5 minutes, if still true, it is raised; a rule that becomes true after entry is raised at once.
- 326-5+refined (25 Nov, same day): "already true at entry" means first found true within 5 minutes of entry and never seen false since; the pop-up waits until entry + 5 minutes; a rule seen false then true is raised at once.
- 330-5b (25 Nov night): a rupee level, like every plan level, raises an actionable alert and nothing exits by itself. [see subject 2]

### 2. Plan stops and targets
- 326-1 (25 Nov, Q2): "Take profit" is refused ("Not in profit after charges: {after}") when the whole trade closed at the planned prices is a loss after charges as well as before; Exit stays offered.
- 330-1 (25 Nov night): the rupee amounts of "% of max loss" and "2x the credit received" stops are worked out once from the trade as entered and change only when the user edits the plan.
- 330-1+adjustment (26 Nov morning): an adjustment (e.g. a roll) does not move the stop amounts either; the plan shows a line that the trade was adjusted since entry.
- 330-5a (25 Nov night): profit target and loss stop can be typed in rupees or percent; the plan shows both.
- 330-5+basis (26 Nov morning, "go with your recommendation of option A"): a rupee level is for the whole trade and before charges, with the per-lot figure shown beside it.
- 330-5+rupee-stop (26 Nov): a rupee loss stop replaces only the "% of max loss" part; the "2x the credit received" line stays, whichever comes first.
- 330-25 (26 Nov noon): a rupee stop above max loss is saved with a warning line; it never blocks.
- 330-17 (26 Nov morning): breakevens in the plan summary stay before charges with the line "Breakevens are before charges"; Max Profit and Max Loss stay after charges.

### 3. Time exit
- 330-7 (25 Nov night): a plan's time exit can be set for any trading day and time, raises an actionable alert, nothing exits by itself.
- 330-7+one-date (26 Nov morning): one trading day and one time, alert raised once; a blank date means expiry day.

### 4. Playbooks, plans, Reset and "no plan"
- 330-9 (25 Nov night): a playbook is one complete adjustment method for a strategy type; one type can have several; a plan belongs to one strategy, is picked from a playbook, may change all or some conditions, and a strategy has exactly one active plan. SPEC CHANGE to REQ-158 (several standard playbooks per type).
- 330-9+who-makes (same night): the product team writes the standard playbooks; a user can make his own by editing one and saving it under his name.
- 330-9+two-levels (same night): only playbooks and the plan; "Save this plan with a name" makes it one of the user's own playbooks; no separate list of saved plans.
- 330-9+what-may-change (same night): per condition the user may change values or switch it off for this trade; he cannot add a condition the playbook lacks.
- 330-9+reset (same night): "Reset to playbook" after one confirmation sends every condition back to the playbook's values and marks changed or switched-off conditions.
- 330-9+which-offered (same night): a strategy is offered only the playbooks written for its own type.
- 330-11 (25 Nov 11:46 and 11:50 IST, chat): only a strategy's own plan applies; with no plan there are no suggestions and no target or stop alerts and it shows "No plan: nothing is watched for this strategy". SPEC CHANGE to REQ-158 and REQ-161.
- 330-11+no-limit (26 Nov morning): with no plan the adjustment-count limit does not apply either.
- 330-13 (25 Nov about 12:50 IST): a live "Plan watch" box (fires at / now / distance / state) shown only when the strategy has a plan.
- 330-32 (26 Nov evening): "Reset to playbook" puts back the conditions only (and switches switched-off ones on); typed levels (profit target, rupee target, rupee stop, time exit, adjustment limit) and plan settings stay.

### 5. A side of the trade closing
- 330-2 (25 Nov night): after one side closes, the plan stays the one set at entry; rules for the closed side read "Not applicable: the <call or put> side is closed"; the user is told and asked whether to add legs on the closed side, or confirm the new shape (e.g. bull put spread); asked again if he does not confirm.
- 330-33 (26 Nov evening): every time a side closes, also a second time on the same side after new legs, the user is told and asked again.

### 6. Stops panel and armed exits
- 327-1..4 (25 Nov ~16:10 IST): in market hours a paper trigger whose level cannot be checked against a live price (waited up to 3 s) is refused and nothing stored, with "Not saved: the live price could not be read, so this level cannot be checked. Try again in a moment."; market closed unchanged; a level already crossed still refused. SPEC CHANGE to ADR-317 (2).
- 328-4 (25 Nov evening): while the builder shows that the trade changed elsewhere, Exit all and every per-leg Exit are disabled with "This trade changed elsewhere. Reload to see the current legs." until reload.
- 328-5 (25 Nov evening): the unreadable-price refusal wording of ADR-327 (2) is approved as built.
- 330-6 (25 Nov night): when a leg stop is set, the Stops panel shows before saving "If this stop fires, max loss becomes Rs X (now Rs Y)"; also in the alert when it fires; never blocks.
- 330-41 (26 Nov night): the max-loss figure in a fired leg stop's alert uses the price the leg actually exited at.
- 330-21 (26 Nov noon): the "Stops" link on a Live Strategies card opens Positions, scrolls to that trade and opens its Stops panel.
- 330-44 (26 Nov night): an armed paper exit whose level is hit but cannot run for lack of a live price (or too-old index) alerts once per exit per day, stays set, runs at the next check.

### 7. Prices not live, stale, after the close
- 326-2 (25 Nov, Q3): header figures over the strategies that can be priced; expired ones left out with the count line; the Live card's expiry sentence (ADR-324 (1) to (3) accepted as built).
- 330-28 (26 Nov after the close): "Add to Paper" while prices are disconnected is allowed, and the confirm list carries "Prices are not live; the entry is the last captured price, as of 14:46."
- 330-35 (26 Nov evening): the header Total P&L is the sum over the trades that can be priced with a count line for the rest ("1 strategy left out: its price is not live."); blank with reason only when none can be priced. SPEC CHANGE to ADR-324 (1).
- 330-36 (26 Nov evening): the after-close figure is the last price received up to the calendar close (15:30:00); later prices are ignored for it.
- 330-36+no-pre-close-price (26 Nov evening): a contract first priced after 15:30 shows the price it has labelled with its own time ("as of 15:37:12"); follow-up to freeze each 15:30 close at start-up.
- 330-36+banner (26 Nov evening): one builder banner: "Prices are from 15:30:00; 1 leg as of 15:33:48".
- 330-39 (26 Nov night): during market hours an index value older than 60 seconds (a setting) is shown as not live with its own time and treated as unavailable by index-level exits, trigger checks and the Stops panel.

### 8. Unsaved legs, reload and leaving the builder
- 328-2 (25 Nov evening): Option Chain "Add Selected" asks "Replace the N legs?" before replacing held legs. [premise replaced by 329]
- 329-1 (25 Nov ~22:35 IST): going to the Option Chain keeps the builder's unsaved legs; Add Selected ADDS the ticked contracts.
- 329-2 (25 Nov ~22:35 IST): leaving the builder for any other page with unsaved legs asks "Leave the builder? The N unsaved legs will be lost." with "Stay" and "Leave". (Answer first "2", then changed to "1", which stands.)
- 329-3 (25 Nov ~22:35 IST, with later notes): "Replace the N legs?" stays only for a draft link that arrives inside the app; until REQ-154 is built a pasted link or reload loads fresh with no question.
- 330-18 (26 Nov, after screen-check row 11, 10:57 IST): a pasted link while unsaved legs are held stays as is: loads fresh, legs lost, nothing asked.
- 330-22 (26 Nov noon): for a running trade with staged changes the leave question reads "Leave the builder? The N pending changes will be lost."; new unsaved strategy keeps "The N unsaved legs will be lost."
- 330-34 (26 Nov evening): REQ-154 AC-1 stands over point (18): unsaved legs are kept on the server per signed-in user and restored, built with the sign-in step; until then one line under the unsaved-legs bar: "Unsaved legs are not kept if you reload or close this page. Save to keep them."

### 9. Option Chain picking
- 326-7 (25 Nov, Q8): the lots box appears after the first click on a strike.
- 330-16 (26 Nov morning): Add Selected with contracts on another index than the builder's held legs adds nothing and says "These contracts are on SENSEX; the legs in the builder are on NIFTY. Nothing was added."
- 330-20 (26 Nov noon): after Add Selected the ticks are cleared.
- 330-40 (26 Nov night): pressing Buy (or Sell) twice on the same ticked contract removes the leg and unticks it; a contract is one row.

### 10. Changing expiry and moving legs
- 328-1 (25 Nov evening): a strike step or move (step, Shift, Width, Hedge) that lands on a contract held on the OPPOSITE side asks "Keep both" / "Cancel"; a deliberate add from the strike picker stays silent. SPEC CHANGE to ADR-319 (4) and REQ-109 AC-9.
- 330-42 (26 Nov night): a separate "Change expiry" action moves all legs or one leg to a picked expiry keeping strikes, sides and lots; if any strike is missing nothing moves and the missing strike is named. SPEC CHANGE to REQ-078 AC-7.

### 11. Positions list and totals
- 326-6 (25 Nov, Q7): "Today" is the whole result after charges of the real trades opened or closed on the current trading day.
- 328-3 (25 Nov evening): the Paper P&L panel shows per leg the leg's TOTAL result (booked plus open), the same as the legs table.
- 330-10 (25 Nov about 10:20 IST, wording confirmed night): real and paper in ONE Positions list with a "PAPER" tag, two totals "Real P&L" and "Paper P&L" never added together, filter All / Real / Paper default All, exit confirmations name Paper or Real. SPEC CHANGE to ADR-201 (2).
- 330-14 (26 Nov morning): a Completed strategy shows "Open in Builder" only, no "Add orders".
- 330-15 (26 Nov morning): Paper P&L total stays the whole paper result, open and closed together, with a line such as "Includes N closed strategies".
- 330-24 (26 Nov noon): "Real P&L" is the sum of the rows shown with a line "Excludes contracts not in a strategy here and contracts closed today."
- 330-27 (26 Nov noon): a closed leg whose exit is an average shows "174.73 (avg of 2)"; the Orderbook keeps each fill.

### 12. Deleting, Undo and a busy strategy
- 330-8 (25 Nov night): My Strategies gets tick boxes, "Select all" and "Delete selected"; one confirmation names the count; rows a single delete refuses are skipped and named.
- 330-8+running (26 Nov morning): a RUNNING paper strategy is deleted in a bulk delete exactly as a single delete allows; the confirmation says how many are running.
- 330-26 (26 Nov afternoon): a save, delete or exit meeting a busy strategy is refused with "This strategy is busy with another action, so nothing was changed." / "Wait a moment, then try again."
- 330-31 (26 Nov after the close): a delete and its Undo are recorded in the strategy's history as "Deleted" and "Restored" with times.

### 13. Names and labels
- 326-4 (25 Nov, Q5): 24-hour IST time everywhere, the disconnect sentence included ("Last updated: 10:42:17 IST"); no AM or PM.
- 330-19 (26 Nov noon): "Add to Paper" asks for a name prefilled with the shape; alert titles and lists carry number and expiry, "Short Iron Condor (#172, 1 Dec)".
- 330-23 (26 Nov noon): the Orderbook shows quantity in LOTS.
- 330-30 (26 Nov after the close): the builder's "Settings" button is renamed "View".

### 14. Wording approvals and error messages
- 326-3 (25 Nov, Q4): ADR-324 point (4) accepted as built (timeout words; a failed pick keeps typed fields).
- 330-29 (26 Nov after the close): the builder's "P&L Table" tab, when its data cannot be read, keeps the error block "The page could not get an answer from the server" and shows no number.
- 330-37 (26 Nov evening): a link to a strategy that no longer exists says "This strategy was not found. It may have been deleted." with a button "Open My Strategies".
  [other approvals: 328-5, 330-26, 330-34 wording, 330-28 line are filed under subjects 6, 12, 8, 7]

### 15. Charts
- 330-38 (26 Nov night): the payoff chart's hover reading stays under the mouse through a live refresh and updates in place.
- 330-43 (26 Nov night): the builder's Strategy Chart is switched on (ADR-203) and draws the strategy's ACTUAL open legs through one route for paper now and real later.

### 16. Scope and process
- 326 header (25 Nov): Q2-Q6 by the question tool in the GC-ICLIVE session, Q7 and Q8 and the D-67 refinement in the Part F session; this 7-point text replaces the 5-point one.
- 328 scope (25 Nov evening): all of phases 3 to 8 of the modular-doors plan stay in the plan.
- 330-12 (25 Nov 11:02 IST, chat): one exit function ("exit this strategy: these legs, this reason") and stand-alone condition checks; the exit function is Phase 4 of the modular-doors plan.
- 330 standing instruction (25 Nov night): every actionable alert goes through ONE shared module; the same one-module rule for every capability.
- 330 scope note (26 Nov night, "no preference"): D-48 and D-51 built now; D-35 planned next; D-62 waits for standard playbook content.
- 330 afternoon line (26 Nov afternoon): "the tests for every link, button and function of the paragraph below are started, screen by screen."
- 330 "Not in this record": OD-4 "waits for the owner's word to start."

Id check: 326-1..7 (+refinement of 5), 327, 328-1..5, 329-1..3, 330-1..44 are all placed (330-3,4,5 split across subjects 1 and 2; 330-9 and 330-11 in 4; 330-36 in 7; others singly).

---------------------------------------------------------------------
## B. Same subject asked more than once
---------------------------------------------------------------------

Verdict totals: 26 subjects/threads; CONSISTENT 19, SUPERSEDED 7, CONFLICT 0.

B1. Add Selected: replace or add (ids 328-2, 329-1, 329-3) - SUPERSEDED
- 328-2: "when the builder already holds legs, it asks "Replace the N legs?" ... before replacing them". "Not chosen: add the ticked legs to the existing ones; keep replacing silently."
- 328-2 later note: "In force since 25 Nov 2026: ADR-329 (1) and (3) replace this point's premise: Add Selected ADDS the ticked contracts to the builder's legs".
- 329 decision: "The question corrected the premise of ADR-328 (2)".

B2. Leave-the-builder question (329-2, within 329, same evening) - SUPERSEDED
- 329: "he first answered "2" (always ask before leaving) and then changed the answer to "1", which stands."
- 329 provenance: "it replaced his answer "2" given a few minutes earlier."

B3. Reload or pasted link with unsaved legs (329-3, 330-18, 330-34) - SUPERSEDED
- 330-18: "this stays as it is. A pasted link, like a reload, loads the page fresh; the unsaved legs are lost and nothing is asked." "Not chosen: keep unsaved legs across a page load so a paste or reload asks".
- 330-34: "REQ-154 stands over point (18)"; "unsaved legs are kept on the server and restored when the builder loads, on any browser, until the user saves or clears." "they describe only what ships UNTIL REQ-154 is built".
- 329-3: "REQ-154 AC-1 ... STANDS, ADR-330 (34) (owner, 26 Nov 2026, asked as a conflict)".

B4. Leave-the-builder wording (329-2, 330-22) - CONSISTENT
- 329-2: "a new unsaved strategy keeps "The N unsaved legs will be lost." (ADR-330 (22), owner 26 Nov 2026, question tool...)".
- 330-22: "for a new unsaved strategy it stays "The N unsaved legs will be lost."" Later answer adds the running-trade case only.

B5. Opposite-side contract (328-1, 329-1) - CONSISTENT
- 328-1: "A deliberate add of an opposite-side leg from the strike picker stays silent."
- 329-1: "the opposite-side case follows ADR-328 (1) for moves only, so a ticked opposite-side contract is a deliberate add and is not asked".

B6. Option Chain picking (326-7, 330-16, 330-20, 330-40, with 328-2/329-1) - CONSISTENT
- 326-7 "the lots box appears after the first click on a strike"; 330-40 "more lots are set in the lots box"; 330-16 "Add Selected adds nothing; the held legs stay" applies only to another index; 330-20 "they persist until they are added" matches 330-16 (nothing added, so not cleared by text). No sentence in one changes another.

B7. How long an actionable alert lives (330-3, 330-3+closed, 330-3+plan-removed) - SUPERSEDED (in those two cases)
- 330-3: "Such an alert does not close, lapse or leave the Active list until the user himself acknowledges it".
- 330-3+closed: "leaves the Active list and the bell and is kept in History marked "Closed by system: the trade closed at HH:MM"; there is no position left to decide about." "Not chosen: keep it until acknowledged."
- 330-3+plan-removed: "asked because this point and point (11) disagree" ... "leaves the Active list and the bell ... point (11) then holds (no plan, nothing watched)." "Not chosen: keep it until answered".

B8. Which messages are actionable / count on the bell (330-3, 330-4, 330-4+Stops-fired, 330-5b, 330-7, 330-44) - CONSISTENT
- 330-3: "(b) INFORMATIONAL: nothing for the user to do (paper orders placed, settled at expiry, stop saved)". 330-4+Stops-fired: "the message is INFORMATIONAL ... it does not count on the bell". 330-5b: "it raises an actionable alert of point (3) and nothing exits by itself ... The exits a user arms himself on the Stops panel ... are a different thing". 330-44 states only "the user gets an alert, once per exit per day" and says nothing about the bell (silent, not contradictory).

B9. Adjustment pop-up quiet period (326-5, 326-5+refined; vs 330-3 adjustment alert) - CONSISTENT
- 326-5: "is not raised in the first 5 minutes after entry"; refinement: ""already true at entry" means first found true within 5 minutes of entry and never seen false since". 330-3 lists "an adjustment rule fired" as actionable and does not mention the 5 minutes. No sentence says the pop-up of 326-5 and the alert of 330-3 are the same or different (see C, close calls).

B10. Plan stop amounts after trade changes (330-1, 330-1+adjustment, 330-2a, 330-5) - CONSISTENT
- 330-1: "Closing a side or a leg does not move them."; +adjustment: "an adjustment of the trade ... does not move the stop amounts either; only the user editing the plan does."; 330-2a: "The plan stays the one set at entry"; 330-5: the typed rupee stop "replaces only the "% of max loss" part".

B11. Rupee levels (330-5a, 330-5b, 330-5+basis, 330-5+rupee-stop, 330-25) - CONSISTENT
- Each later answer adds a case: basis ("for the WHOLE trade and BEFORE charges"), 2x credit stays, above-max-loss warning. None replaces an earlier sentence.

B12. Charges basis (326-1, 330-5+basis, 330-17) - CONSISTENT on the text (see C close call)
- 326-1: "a loss AFTER charges"; 330-5: "BEFORE charges, the same basis as the percent levels (ADR-247)"; 330-17: "Max Profit and Max Loss stay after charges (ADR-321 (3))". Each names a different thing.

B13. Fired leg stop max-loss line (330-6, 330-41) - CONSISTENT
- 330-6: "The same line is in the alert when the stop fires." 330-41: "the alert's line uses the price the leg actually exited at ... not the Rs 12,005.50 worked out at the stop level." Adds the gap case; see D9.

B14. A side closes (330-2, 330-33) - CONSISTENT
- 330-2: "If he does not confirm, he is asked again"; 330-33: "every time a side of the trade closes the user is told and asked again ... also when the same side closes a second time". Not chosen in 330-33 "ask once per side for the life of the trade" was never in 330-2.

B15. Time exit (330-7, 330-7+one-date) - CONSISTENT
- 330-7 "any trading day and time"; addition "the user picks one trading day and one time ... A blank date means expiry day, as today."

B16. Playbooks, plans, Reset (330-9 and its same-night sub-answers, 330-11, 330-13, 330-32) - CONSISTENT
- 330-9: "after one confirmation every condition goes back to the playbook's values"; 330-32: "the CONDITIONS only ... the levels the user typed ... stay as he set them". 330-9: "A plan can be saved with a name and used again on other strategies" and "there is no separate list of saved plans" (via own playbooks). 330-9 "plan then applies only to that open position" matches 330-11 "A playbook is only a source to copy from".

B17. No plan (330-11, 330-11+no-limit, 330-13) - CONSISTENT
- 330-13: "Shown only when the strategy has a plan; otherwise the line of point (11)."

B18. Bulk delete of running strategies (330-8, 330-8+running) - SUPERSEDED (reading of the example)
- 330-8: "a strategy that cannot be deleted today (for example one with open positions) is skipped and named in the result, as in "12 deleted, 2 kept: they have open positions"". +running: "asked because the example above and ADR-293 (1) disagree" ... "The example "one with open positions" above therefore means a strategy a single delete refuses today (held at the broker, ADR-292), never a running paper one." "Not chosen: skip running paper strategies and name them in the result."

B19. Delete, busy, Undo (330-8, 330-26, 330-31) - CONSISTENT
- Different events (many rows; busy strategy; trace of a delete). 330-26 "a save, delete or exit that meets a strategy busy" refused; 330-8 has no busy case.

B20. Header total when some trades cannot be priced (326-2, 330-35) - SUPERSEDED
- 326-2: "header figures over the strategies that can be priced; expired ones left out with the count line". 330-35: "SPEC CHANGE to ADR-324 (1), which he had accepted in ADR-326 (2) and which kept the figure blank for any missing price other than expiry". See D5.

B21. Totals on the Positions list (330-10, 330-15, 330-24, 330-35; 326-6) - CONSISTENT on the text (see C close calls)
- 330-10 "two totals ... never added together"; 330-15 "the Paper P&L total stays the whole paper result, open and closed trades together"; 330-24 "Real P&L ... Excludes ... contracts closed today"; 330-35 "The total on Home and the Positions header is the sum over the trades that can be priced".

B22. After-close price (330-36 and its two later answers) - CONSISTENT
- 330-36: "later prices are ignored for it"; +no-pre-close: "For that contract only, the price it has is shown labelled with its own time"; +banner: "Prices are from 15:30:00; 1 leg as of 15:33:48". Each states its own scope.

B23. A price that cannot be read (327-2, 328-5, 330-28, 330-39, 330-44) - CONSISTENT
- 327-2: "Market open and still no live price after that wait (no feed, a stale or failed read): the save is refused"; 330-44: "the exit stays set and runs at the next check when prices are back" (at hit, not at save); 330-39: "treats it as unavailable, exactly as when the whole feed is down"; 330-28 covers entering a trade, not a trigger. 328-5 approves the wording of 327-2.

B24. "Could not get an answer" messages (330-29, 330-37, 326-3) - CONSISTENT
- 330-29: "the error block "The page could not get an answer from the server" stays" (data unreadable). 330-37: "in place of "The page could not get an answer from the server.", which blamed the connection although the server had answered" (deleted strategy). Different cases; 326-3 text of ADR-324 (4) not in the five records.

B25. OD-4 tests (330 "Not in this record" vs afternoon line) - SUPERSEDED
- "Not in this record: OD-4 ... is recorded in the 25 Nov screen notes and waits for the owner's word to start." vs "Also 26 Nov afternoon (owner, question tool): the tests for every link, button and function of the paragraph below are started, screen by screen."

B26. One-module rule (330-12, 330 standing instruction) - CONSISTENT
- 330-12: "one exit function ... that any trigger calls"; standing: "every "actionable alert" above is raised through ONE shared module ... The same one-module rule holds for every capability in the product".

---------------------------------------------------------------------
## C. Conflicts to settle
---------------------------------------------------------------------

None found.

Checked: all 26 threads of B, comparing each later sentence with the earlier one it touches, looking for (a) a "Not chosen" option that a later point chose, (b) a later point that changes an earlier sentence without saying so, (c) two figures or messages for one event. Every earlier-vs-later change in the five records either names itself ("replace this point's premise", "stands over point (18)", "SPEC CHANGE to ADR-324 (1)", "point (11) then holds", "therefore means") or adds a sub-case. The owner did give two different answers once to one question ("2" then "1" in ADR-329) and the record says "1" stands.

Close calls (NOT conflicts; the texts do not overlap enough to prove a clash, but you may want a one-line answer):
1. 330-15 vs 330-35, closed or settled trades in the paper total. 330-15: "the Paper P&L total stays the whole paper result, open and closed trades together, ... "Includes N closed strategies"". 330-35, Not chosen: "also count a settled or settling trade at its booked result". Case: a trade that settled at expiry today. Whether it counts is not written.
2. 330-10 vs 330-35 / 326-2, what "Total P&L" adds. 330-10: "two totals, "Real P&L" and "Paper P&L", never added together". 330-35: "The total on Home and the Positions header is the sum over the trades that can be priced" and "Home showed "Total P&L -" with "Paper P&L paused"". Case: a day with one real and two paper trades: the text does not say what the single "Total P&L" header sums.
3. 330-5+basis vs 330-17, base of "% of max loss". 330-5: "a rupee level is for the WHOLE trade and BEFORE charges, the same basis as the percent levels (ADR-247)". 330-17: "Max Profit and Max Loss stay after charges (ADR-321 (3))". Case: a stop of "15.4 % of max loss": text does not say whether the max loss in that percent is the after-charges figure shown in the summary.
4. 326-1 vs 330-5, a profit level hit before charges but a loss after charges. 326-1: ""Take profit" ... is refused ... when the whole trade closed at the planned prices is a loss AFTER charges". 330-5: "a rupee level ... BEFORE charges ... it raises an actionable alert". Case: plan target reached with a small gross profit that charges turn into a loss: alert raised (330-5) but "Take profit" refused (326-1).
5. 326-5 vs 330-3, adjustment pop-up vs adjustment alert. 326-5: "an adjustment pop-up for a rule that was already true when the trade was entered is not raised in the first 5 minutes". 330-3: "an adjustment rule fired" is ACTIONABLE and stays until answered. The text never says whether the pop-up of 326-5 is the actionable alert of 330-3 (and so whether the 5-minute wait also delays the alert).
6. 330-24 vs 326-6, closed today. 330-24: "Real P&L" "Excludes ... contracts closed today". 326-6: "Today" is the result "of the real trades opened or closed on the current trading day". Two different figures with two labels; no text says they must agree.

---------------------------------------------------------------------
## D. Stale text
---------------------------------------------------------------------

D1. ADR-328 (2), "Not chosen" and header lines. Quote: "Not chosen: add the ticked legs to the existing ones; keep replacing silently." (ADR-329 (1) chose exactly "ADDS the ticked contracts".) The point carries a note ("In force since 25 Nov 2026: ADR-329 (1) and (3) replace this point's premise"), but the "Not chosen" sentence, the `changes` line ("makes ADR-319 (1) true for Option Chain Add Selected") and the `consequences` line ("who clicks Add Selected with an unsaved draft, is asked before anything is replaced or doubled") are not marked.

D2. ADR-330 (18). Quote: "this stays as it is. A pasted link, like a reload, loads the page fresh; the unsaved legs are lost and nothing is asked." and "Not chosen: keep unsaved legs across a page load so a paste or reload asks". ADR-330 (34) says "REQ-154 stands over point (18)" and "Not chosen: withdraw REQ-154", but point (18) itself carries no mark.

D3. ADR-330 (8), the example. Quote: "a strategy that cannot be deleted today (for example one with open positions) is skipped and named in the result, as in "12 deleted, 2 kept: they have open positions"". The later paragraph of the same point says the example "means a strategy a single delete refuses today (held at the broker, ADR-292), never a running paper one"; the example sentence itself is unchanged.

D4. ADR-326 (2). Quote: "ADR-324 points (1) to (3) are accepted as built (header figures over the strategies that can be priced; expired ones left out with the count line; the Live card's expiry sentence)." ADR-330 (35) says this was "SPEC CHANGE to ADR-324 (1), which he had accepted in ADR-326 (2)". ADR-326 carries no mark. (Literal note: ADR-326's own parenthesis already says "strategies that can be priced"; ADR-330 (35) says the accepted rule "kept the figure blank for any missing price other than expiry". The two descriptions of ADR-324 (1) differ and ADR-324 was not among the five records.)

D5. ADR-330, "Not in this record" paragraph. Quote: "Not in this record: OD-4 (tests for every link, button and function, asserting the outcome) is recorded in the 25 Nov screen notes and waits for the owner's word to start." The line above it says: "Also 26 Nov afternoon (owner, question tool): the tests for every link, button and function of the paragraph below are started, screen by screen."

D6. ADR-330, opening lines and `changes`. Quote: "Nothing here is built yet; each point names the finding it settles." and "To be built after the modular-doors refactor (it touches the same stop and plan code)." Later in the same record: (16) "built on refactor/modular-doors with the S-08 work" and the scope note "D-48 ... and D-51 ... are built now".

D7. ADR-330 (34). Quote: "until then the app says plainly that unsaved legs are not kept across a reload (wording to be proposed to the owner)." The next paragraph ("Wording and place (owner 26 Nov evening, question tool)") gives the wording, so "to be proposed" is done.

D8. ADR-330 (6). Quote: "The same line is in the alert when the stop fires." ADR-330 (41): the alert "uses the price the leg actually exited at ... not the Rs 12,005.50 worked out at the stop level". The alert no longer carries "the same line" (same figure) when the leg gaps through the stop.

D9. ADR-330 (3), first paragraph. Quote: "Such an alert does not close, lapse or leave the Active list until the user himself acknowledges it and takes his call". Two later paragraphs of the same point (trade closes first; plan removed first) say it does leave the Active list in those cases. The base sentence is not qualified; the changes follow directly beneath it.

D10. ADR-330 front matter. `date: '2026-11-25'`, title "Owner decisions of 25 Nov 2026 night", `provenance`: only "Owner answer, 25 Nov 2026 night ... ("Go with your recommendation")" and `source` only S-21, while the body holds answers dated "26 Nov morning", "26 Nov noon", "26 Nov after the close", "26 Nov evening", "26 Nov night".

D11. ADR-327 (2) vs ADR-328 (5), literal wording. 327: ""Not saved: the live price could not be read, so this level cannot be checked. Try again in a moment."" 328-5: "approved as built: "the live price could not be read, so this level cannot be checked. Try again in a moment." / "No stop was set; nothing was exited." / "Setting this paper stop." / "Press Save again once the live prices are showing."" The "Not saved:" opening is in 327 only; 328 may be listing the template's fragments, but the text does not say.
