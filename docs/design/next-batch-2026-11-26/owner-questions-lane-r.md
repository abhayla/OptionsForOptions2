# Owner questions, Lane R (screen findings of 26 Nov 2026)

Raised by Lane R (branch fix/screen-findings-1126, cut from feat/nb-screens-w2-1126 at a9bd41a). Each question goes to the
owner only through the coordinator. Where an option is reversible, Lane R builds the recommended one and says so.

## LR-Q1 Row 11: the "Replace the N legs?" question on a draft link (asked 26 Nov 2026)

**ANSWERED 26 Nov 2026 about 12:00 IST** (owner, question tool, via the coordinator): option 1, "Keep as is, correct the
check". Written into ADR-329 (3) and ADR-328 (2); row 11 of RESULTS.md rewritten; `draft-link.test.js` stays the test of
the in-app case.

Spec basis: ADR-328 (2) (Option Chain "Add Selected" asks "Replace the N legs?"); ADR-329 (1) (the chain trip now ADDS,
it does not replace) and ADR-329 (3) ("ADR-328 (2) stays for the case where the builder, already showing legs,
receives a draft link that replaces them (a pasted or shared link, not the chain's Add Selected)"); ADR-329 (2) and
check row 10 ("Closing or reloading the tab: no question (decided: the browser's own box cannot show the sentence)");
REQ-079 AC-5 (the wording). ADR-328.md itself was never edited, so read alone it still says "Option Chain Add Selected";
ADR-329 (3) narrowed it. The check text (RESULTS.md row 11) follows ADR-329 (3).

**The two texts.**
- Check row 11: "With legs shown, paste a different `?draft=` link into the address bar of the same tab: 'Replace the
  N legs in the builder?' Replace / Cancel; Cancel keeps the legs and puts the old link back."
- ADR-328 (2) as written: "Option Chain 'Add Selected': when the builder already holds legs, it asks 'Replace the N
  legs?' ... before replacing them". ADR-329 (3) later moved this question to a pasted or shared draft link.

**What the screen did (A11-retry, 10:57).** Empty NIFTY 1 Dec builder, 3 legs added (S 25900 CE, S 25700 PE,
B 26000 CE), then the address became `/strategy/builder?draft=test-replace-1126` by a full page load: "No draft
strategy is open. Add a leg to start one." The 3 legs vanished and no question was asked.

**What the code does (read this turn).** The question lives in a watch on the URL's `draft` value in
`frontend/src/pages/StrategyBuilderPage.vue` (line 673 on); it fires only when the `draft` value changes while the
builder page is ALREADY mounted. A link typed or pasted into the address bar and Enter loads the whole app fresh: the
unsaved legs are in page memory only, so they are gone before any code can ask (the same as row 10's decided reload
case). The only two places in the app that make a draft link (Option Chain "Add Selected", `OptionChainPage.vue:129`,
and Create Strategy > Guided, `CreateStrategyPage.vue:170`) both start on another page, so the builder is not mounted
when the link arrives; the chain trip then adds (ADR-329 (1)) and the Create Strategy trip has already asked "Leave
the builder?" on the way out. Real case: there is no path in today's app on which a user can see "Replace the N legs?"
from a draft link; only the unit test `draft-link.test.js` reaches it, by changing the route in place.

**Options.**
1. (Recommended) Keep the behaviour; correct the check and the spec text. The replace question stays as a guard for an
   in-app link that arrives while the builder is open (none exists today; any future one gets it for free). Row 11 is
   rewritten as: "Paste a different `?draft=` link into the address bar: the page loads fresh, the unsaved legs are lost
   with no question, the same as a reload (row 10)". ADR-328 (2) gets a pointer to ADR-329 (3) so it no longer reads as
   the chain's rule. Reversible, wording only; no user loses anything new. Cost: a pasted link still drops unsaved legs
   silently (true today and for a reload, already decided).
2. Keep unsaved builder legs across a page load (kept in the tab's own browser storage, cleared on Save, Discard or
   Leave), so a pasted link, and a reload, find the legs and ask "Replace the N legs in the builder?". This is new
   behaviour: it also changes row 10's decided reload case (a reload would bring the legs back), and it must not bring
   back legs for a different user on a shared PC. Larger build; Lane R would not start it without the answer.
3. Ask with the browser's own "Leave site?" box before any page load while the builder holds unsaved legs. Already not
   chosen once (row 10: the browser box cannot show the sentence or the count).

**Lane R action now:** nothing built for row 11. If option 1 is chosen, Lane R (or the coordinator) edits the check text
and adds the ADR-328 pointer; that pointer is a spec text change, so the row number stays the coordinator's.

## LR-Q2 to LR-Q6: N-14, N-08, N-12, N-11, N-15 (asked 26 Nov 2026 about 12:20 IST, through the coordinator)

**ANSWERED 26 Nov 2026 about 12:30 IST** (owner, question tool): recorded as ADR-330 (19) to (23) on fix/ic-live-test-1123.
- N-14 = ADR-330 (19): Add to Paper asks for a name prefilled with the shape name; lists and alert titles carry the number
  and expiry. Built: the name and the lists. Alert titles: Lane P's catalogue; proposed "Paper strategy - Short Iron
  Condor (#172, 1 Dec)" (`backend/ofo/errors/explanations.py` ~1962, `ofo_app/paper_monitor.py` ~246, `routes/paper.py` ~1845).
- N-08 = ADR-330 (20): ticks cleared once added. Built.
- N-12 = ADR-330 (21): Stops link scrolls to the trade and opens its Stops panel. Built.
- N-11 = ADR-330 (22): "The N pending changes will be lost." for a running trade. Built.
- N-15 = ADR-330 (23): Orderbook in lots. Blocked on a server field: issue #747.

## LR-Q7 S-02 wording (ANSWERED 26 Nov 14:25 IST, question tool: "Approve as written" = ADR-330 (26))

Spec basis: ADR-330 (8) busy-store paragraph (Lane R, 26 Nov 2026); ADR-003. Built as reversible new wording, catalogue
entry `store_busy` (STRATEGY_VALIDATION_522): "This strategy is busy with another action, so nothing was changed." /
"Wait a moment, then try again." Real case: the owner's ERR-6960F002 on a strategy delete, 25 Nov. Recommendation:
approve as built. A new decision row number for it is the coordinator's.

## LR-Q8 N-28: how a closed leg's exit price reads when it is an average of several exits (ANSWERED 26 Nov 14:25 IST, question tool: "Add '(avg of 2)'" = ADR-330 (27), built)

Spec basis: none: the spec is silent on labelling a closed exit average (searched: "average exit", "exit prices"); ADR-321 (6)
("a closed lifecycle is its own row with entry, exit and booked"); ADR-008 (the average is served, `routes/paper.py:617-624`).
Real case: paper trade 172, closed row 25850 CE shows exit 174.73, the average of two exits 153.00 and 196.45 (Orderbook).
Options: (a) a suffix "(avg of 2)" after the price (new wording); (b) each exit fill as its own line in the closed row;
(c) leave it, the Orderbook lists the fills. Recommendation: (a), small and the Orderbook already holds the detail.
Lane R builds nothing for it until answered.

## LR-Q9 C-01b: one basis for breakevens? (CLOSED 26 Nov 2026)

**CLOSED** by the coordinator, 14:20 IST: already answered by ADR-330 (17): the plan summary's breakevens stay before charges
and say so; the placed book follows ADR-263 (2). No build.

Spec basis: ADR-330 (17) (plan summary: breakevens BEFORE charges, Max Profit / Max Loss after); ADR-263 (2) (a placed paper
book: breakevens carry the same charges as Max Profit / Max Loss and booked P&L, with a line saying so). Real case: draft 174
reads "Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges."; placed 172 reads
"Breakevens include the booked P&L and about Rs 395.78 of charges and taxes." Both are as built and as decided.
Options: (a) keep both (recommended: a placed trade has real charges and booked P&L, a plan has estimates); (b) plan
breakevens after charges too; (c) placed breakevens before charges too. No build.

## LR-Q10 D-N07: what the P&L Table shows when the API is down (open, 26 Nov 2026)

Spec basis: check row 4 of docs/design/modular-doors-2026-11-25/RESULTS.md (when prices are not live the figures show "-"); the
N-07 / #744 rule (P&L Table rows and TOTAL show "-" on a failed book read); ADR-008. Real case (Part D, 14:24): API stopped
~25 s; the legs table showed "-" everywhere, the P&L Table tab was replaced by "The page could not get an answer from the
server" with no rows. Cause: with the API down the outcome request fails too, and the P&L Table's rows come from that reply.
Options: (a) keep: the error block is honest, it shows no number (recommended: no extra build, nothing misleading);
(b) build P&L Table rows from the held book net with "-" in every figure while the outcome is unreadable (a second row
source for that tab; medium build); (c) keep the last outcome rows on screen with every figure dashed. No build until answered.

## LR-Q11 N-38: two different "Settings" (open)

Spec basis: REQ-009 (the avatar menu opens Account & Settings; "Settings (the admin's app-wide Settings page, REQ-167)").
Real case: the builder has its own "Settings" button (a "Show legs as" popover) beside the search; the app's Settings is in
the avatar menu only. Options: (a) keep; (b) rename the builder's button, e.g. "View" or "Builder settings" (label only);
(c) add Settings to the top menu. Recommendation: (b). New wording, so it needs the owner.

## LR-Q12 N-40: Add to Paper while live prices are disconnected (open)

Spec basis: REQ-109 AC-1 (each confirm price defaults to the leg's builder entry price and is editable); REQ-109 AC-5 and
may_act (only paper EXITS are refused when prices are not live); ADR-015 ("Live market data disconnected. Last updated ...").
Spec silent on entries at stale prices (searched: stale, not live, entry, Add to Paper refusal). Real case (Part D, 14:46):
the banner "Live market data disconnected. Last updated: 14:46:30 IST" showed, and Add to Paper still recorded the entry at
the last captured prices. Paper only, but every later paper P&L, stop and target check starts from that entry.
Options: (a) allow as now; (b) allow, with a line in the confirm list "Prices are not live; the entry is the last captured
price, as of HH:MM" that the user confirms; (c) refuse like the exit. Recommendation: (b). New wording and a rule: needs a row.

## LR-Q13 Should a delete and its Undo show in the strategy's history? (open)

Spec basis: REQ-070 (the delete confirm reads "Delete this draft? Its history is kept, and you can Undo right after."); ADR-118.
Real case: drafts 182 and 183 reappeared and nothing on screen says when or how; `delete_draft` and `undelete_draft`
(backend/ofo_app/strategy_store.py ~359-383) set or clear `deleted_at` and write no history entry. Options: (a) keep;
(b) add "Deleted" and "Restored" events to the strategy's history (server, small). Recommendation: (b).

## LR-Q14 N-45: what "the last close" is when the feed keeps moving after 15:30 (ANSWERED = ADR-330 (36), 26 Nov 2026: "Freeze at 15:30")

Spec basis: ADR-200 (2) ("last close" is "the last price the feed or a REST read holds ... (the LTP at the close)"; the
label time "is that price's own time"); ADR-212 (the paper screens after hours show "the last close the feed holds"). Real
case (after-close check, 15:33-15:37): trade 185's 25750 PE read 99.75, then 99.60, then 100.10 under "Prices are from
15:30:00". Issue #752. Paper only, no fills after hours.
Options: (a) hold the last price received up to the calendar close (15:30) and ignore later frames for the figure
(recommended: the label and the figure then agree; it amends ADR-200 (2)'s "the last price the feed holds"); (b) keep the
latest price and label it with its own time ("as of 15:37:12"); (c) leave as is. Needs a row.

## LR-Q15 AC-R06: does one unpriced trade blank the whole Total P&L? (ANSWERED = ADR-330 (35), 26 Nov 2026: "Total of the priced trades + a count line")

Business call: which total a trader sees on Home and the Positions header when one running trade has no live price.
Spec basis: ADR-324 (1) (status proposed, pending owner read; taken unattended on 25 Nov): header figures are sums over
the strategies that can be priced; expired ones are left out and counted; "Any other reason a price is missing (prices
not live, not connected, delisted, reassigned) keeps today's behaviour: the figure is blank with its reason." SPEC CHANGE
built as ADR-324 (3b) (ADR-330 (35)): the same left-out-and-counted rule for any unpriced trade; all unpriced still
blanks. Real case (after-close check, 15:32): five of six running trades priced at the last close (rows sum +15,775.80),
#173 (SENSEX, expiring that day, awaiting settlement) paused; Home showed "Total P&L -" with "Paper P&L paused - prices not
live". New wording (pinned "pending owner read"): "1 strategy left out: its price is not live.", "{count} strategies left
out: their prices are not live.", "{count} strategies left out: their contracts have expired or their prices are not live."
Options: (a) keep the build: a total over the priced trades with the count line (recommended: one unpriced trade no
longer hides the other five); (b) revert to the blank total; (c) as (a), but a settled or settling trade counts at its
booked result instead of being left out (needs a settlement rule for the header).

## LR-Q10 to LR-Q13 (ANSWERED 26 Nov ~16:00 IST, question tool): ADR-330 (28) to (31)

LR-Q12 = (28) allow with a confirmed line (built); LR-Q10 = (29) keep the error block (closed, no build); LR-Q11 = (30)
"View" (built); LR-Q13 = (31) Deleted / Restored history entries (handed to Lane J: needs a migration).

## LR-Q1 correction (26 Nov ~17:00 IST)

The row-11 answer relayed in the morning was asked without REQ-154 in view. Asked again as a conflict, the owner decided:
REQ-154 stands (ADR-330 (34)). ADR-329 (3), ADR-328 (2) and row 11 now say the fresh-load loss is only what ships until
REQ-154 is built (issue #751, deferred, not built by Lane R).

## LR-Q16 ADR-330 (34): saying plainly that unsaved legs are not kept across a reload, until REQ-154 is built (open)

(Numbered LR-Q16: LR-Q14 is N-45.)
Spec basis: ADR-330 (34) (until REQ-154 is built the app says plainly that unsaved legs are not kept across a reload);
REQ-154 AC-1; ADR-329 (2) (the leave question for in-app navigation; the browser's own box was not chosen).
Real case: screen-check row 11 (26 Nov 10:57 IST): 3 unsaved legs, a pasted link loaded the page fresh, the legs were gone,
nothing was said.
Proposed wording: "Unsaved legs are not kept if you reload or close this page. Save to keep them."
Where it shows - options:
(a) one line under the builder's unsaved-legs bar (next to the pending/unsaved count), shown only while there are unsaved
legs (recommended: it is where the user looks when the count changes, and it disappears once saved);
(b) a one-time note the first time a leg is added in a session, dismissible;
(c) in the leave question only ("Leave the builder? The N unsaved legs will be lost.") - not enough, a reload never shows it.
Nothing is built until answered; the line is removed when REQ-154 ships.

## LR-Q17 (ANSWERED 26 Nov ~18:30 IST): "Show it with its real time, tonight; exact close later" = ADR-330 (36) (b) built, (c) deferred.

## LR-Q18 Mixed trade after the close: which time does the builder banner show? (open, 26 Nov 2026)

Spec basis: ADR-330 (36) (a) frozen at the close under "Prices are from 15:30:00", (b) a contract first priced after the
close labelled with its own time; silent on a trade with legs of both kinds. `backend/ofo_app/routes/outcome.py:241-242`
(`label_time` takes the latest leg time), shown at `StrategyBuilderPage.vue:1112`, `:1164` and the leg picker banner
(`LegPicker.vue:753`, `leg_picker.py:461`). Real case (Opus re-check run): leg A 99.75 held at 15:29:59, leg B 100.10 first
priced at 15:33:48 -> the banner reads "Prices are from 15:33:48" over a leg frozen at 15:29:59 (the label is later than
that figure); each leg row carries its own time correctly.
Options: (a) the banner shows the EARLIEST leg time ("Prices are from 15:29:59"), the leg rows keep their own; (b) the
banner names both: "Prices are from 15:30:00; 1 leg as of 15:33:48" (new wording); (c) keep the latest time (as built).
Recommendation: (b) - no figure sits under a time it does not have. Lane R builds nothing until answered; #752 stays open.
