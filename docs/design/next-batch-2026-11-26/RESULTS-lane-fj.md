STATUS 13:50 | pushed 99db7820f, gate TOTAL PASS (--jobs 2), suite 391 files / 4230 tests | built: items 1-6, a-c, TF, R1-R4 (five Opus reviews; round 5 fix for the last finding not re-reviewed, so NOT claimed ready), not_applicable stops, PC items A C D, shared slow-read rule, not_read re-ask | not done: item 7 browser walk, d (UX-AF2/UX-B03), W-15, F5 | budget reached | blocker: none

# RESULTS Lane FJ (frontend joins), branch fix/r3-frontend-joins-1128

Base: origin/integration/weekend-r2-1128 plus merges of fix/r2-builder-2, r2-exit-stops-2, r2-pages, r2-plan-screens, r2-backend-2 (two add/add test conflicts: took the lane that fixed the bug). The merged base had 16 red tests (old tests overtaken by FA2's market gate and FC2's list-failure sentence): tests moved, src untouched.

| Item | State | Red line (first) | Green |
|---|---|---|---|
| 1 lock + one key on every page | Fixed, not tested in a browser | paper-strategies-exit-lock-r3-fj: `expected [ { method: 'POST', ... } ] to have a length of 1 but got 2` (5 of 6 red) | 12/12, then round 2 `unknown-locks-class-r3-fj-round2` 20 of 23 red -> 23/23 |
| 2 cancelled-stop lines (page half) | Fixed, not tested in a browser | builder-cancelled-stops-r3-fj: 3 of 5 red | 5/5 |
| 3 plan screens and fields | Fixed, not tested in a browser | 6/9, 5/7, 4/6 red | green |
| 4 chart after unmount | Fixed (coordinator 09:28: Lane FK owns PayoffChart from here; this change is already in) | new guard removed: 1 of 4 red | 4/4; drafts test 5 of 5 runs green |
| 5 no price names the contract | Fixed | 10 red | 12/12 |
| 6 F6 parts, PriceNotice one rule | Fixed | 2/3 and 1/2 red | green |
| 6 F5 stop sentence after unknown move | NOT built, see Question | | |
| a entries_sentence | Fixed | 3/7 red | green |
| b book "Prices as of" / "Checked at" | Fixed | 3/5 red | green |
| c FB2 minors (refusals, 511 tick, Save As, shape read) | Fixed | 4/7 and [2,2,3,3,4,4] vs [2,3,4] | green |

Opus review (items 1-2, commit 10cc777): REVISE, F1/F2 critical (builder and Positions locks read each other as "placed" or "moved"), F3 add lock written after the POST, F4-F7 minors. Round 2 fixed F1-F6 at class level: one writer and one decision (`decideLock`) in lib/unknownLocks.js. F7 not built (server key stays pending up to 600 s, so a same-key resend can meet 582 for up to 10 minutes: no double order, possible wait).
Five Opus reads, see Lock rounds and reviews.

## For the owner lane
- `StrategyOut` (`GET /strategies/{id}`) carries no `position_kind`; with it the builder could tell a real trade directly. Today: status_word "Running" + no paper book for that id.

## Decided for the owner
- Lock and key live in localStorage (storage event for a second tab), in-memory fallback.
- A Confirm sends nothing while any lock is undecided, in any tab or page instance; same key resent only after "not stored".
- Lock ends only by a good re-read: book moved toward the expected book, or unchanged only for a read sent more than 130 s after the client gave up. `out` locks (written before the POST) are never decided by an unchanged book.
- Only STRATEGY_VALIDATION_582 means "still being placed" (lock and key kept); 580/581/583 and every other 409 are refusals.
- Unreadable stored lock content locks every strategy until site data is cleared (fail closed, no escape button). See Question 2.
- Real trade in the builder = status_word Running + no paper book + saved id equals open id; anything else reads as paper.
- A settled trade's Plan watch box now shows the closed sentence (old test "no box on a closed trade" rewritten).
- Save As is blocked while the strategy's add lock stands.
- Refusal parts joined in order: what happened, impact, what is blocked, next action.
- Cancelled-stop entry without a name prints "a leg".

## New wording for the owner to read
1. `The plan watch has not been read for this trade.`
2. `No broker is connected, so no real positions are shown.` (only when the server sends no reason; otherwise the server's `real_pnl.reason`)
3. `No price for <contract>` / `No price for <contract>, <contract>` (e.g. `No price for NIFTY 9 Nov 23500 CE`), as the Exit reason line and the dialog line.
4. `The market is closed.` (entry dialog when `entries_sentence` is absent; otherwise the server's `entries_sentence`)
5. `Prices as of <time>` and `Checked at <time>` (book panel, one as-of formatter).
6. `The stop on a leg was removed with the move; set a new one on the new leg.` (and the `(level 120.00)` form), for a nameless entry.
7. Refusals print every part of the server's reply.

## Question for the owner
1. F5, stop sentence after a move of unknown outcome. Text A (decision 48): "The stop on the old leg may have been cancelled, and the new leg has no stop until you set one." Text B: pinned test paper-move-stop-offer-774 ("the answer is unknown: nothing is claimed; the stop state comes from a re-read"). Recommendation: adopt A (hedged, shown only when an armed stop was read before the post, cleared by the first decided read) and narrow the 774 test to "no claim of cancellation, no offer before the re-read". Built and held back in the scratchpad, not in the branch.
2. Is a permanent block on unreadable lock storage acceptable, or should there be a release such as "I checked the Orderbook"?
3. TD O-4: should the table total follow the "Add booked P&L" switch (tiles move with it, the table total does not; OFF shows whole rupees, ON paise)?
4. Execute page (real basket): does it need the same lock after an unknown outcome, and what should a repeat press do there? Not built.

## Lock rounds and reviews (item 1 / GROUP A: R1 R2 R3 R4)
Five Opus reviews of the lock and key code; each closed what the last found, each found one more in the add/exit lock interplay.
| Review of | Verdict | Open then |
|---|---|---|
| 10cc777 | REVISE | F1/F2 builder and Positions locks read each other as placed/moved; F3 add lock after the POST |
| fea45e1 | REVISE | changed verdict ended the lock in the window; foreign out lock decided; builder checks lock before the stops read; storage fail-open |
| 4c6bc6b | REVISE | add lock ended by unrelated leg move; add lock skipped by a post with an exit row; deciding tab dropped another tab's lock; one key slot |
| 287c2dfa5 | REVISE | N1 (MAJOR, added by round 4): the save bar timer decided the builder add lock, then a second add with a new key could go out (E1, E2); N2 null-at lock never dropped; N3 unreadable legs lock for ever; N5 null-key drop |
| round 5 (on top of 287c2dfa5) | not re-reviewed | N1, N2, N3, N5 closed with tests (group-a-r5-*); N4 left (sign flip or partial fill reads "changed" not "stored") |
Closed, with a test file per finding: R1 no resend inside the window (group-a-r1, group-a-r4-*), R2 lock survives reload and a second tab (group-a-r2, group-a-r4-lock-owner), R3 one key per action incl. Execute page (group-a-r3, group-a-r4-key-slots), R4 cancelled stops read (group-a-r4). Attack tests of the reviews are folded into those files.
Still open (minor, no double order): F7 the server keeps a key pending up to 600 s so a same-key resend can meet 582 for up to 10 minutes; N4; an unparseable whole store blocks every strategy for 130 s after first sight.
The coordinator's build lane runs one more independent review on the merged build.

## TF defect (from test lane TF): builder `?strategy=1` says the paper position "could not be read" with no failed request
Cause: `readPaperBook` threw "unreadable" when the book and the catalogue both answered but the catalogue held none of the book's contracts (D-TD-3 scenario day in the past). Fixed: that state has its own sentence and still blocks the page (fail closed); a failed or malformed read still says "could not be read". Test builder-open-unmatched-r3-fj (3 tests). Not changed: three sites that pass null to `unreadableParts` (book names a different strategy id than the URL; a re-read that is not a paper book) still say "could not be read"; they need their own wording, owner to decide.
New wording (four parts): "This strategy's paper position was read, but its contracts are not in the catalogue for today, so it is not shown." / "The numbers on this page are not shown, so none of them can be mistaken for current values." / "Nothing was changed and no order was placed." / "Trying again will not help until the catalogue lists these contracts."

## Group B (after the group A push)
| Item | State | Test (red first) |
|---|---|---|
| `state:"not_applicable"` stops (coordinator, ADR-330 (64)) | Fixed, not tested in a browser. PaperStops row, PlanEntry line, legStopsGone: never live, no badge, no Cancel, no move-stop offer; row reads "Not applicable: real position." | stops-not-applicable-real-r3-fj (5; 4 red) |
| PC O-A-12 greyed Exit opened the dialog | Fixed: ask() and the `exit=` link no longer open it when the exit gate is blocked or a leg has no price; the link writes a note instead. This reverses Lane U's hotfix (link opened a blocked dialog): owner to know | exit-greyed-no-dialog-r3-fj (5; 4 red); exit-not-live-good-read moved (4 tests) |
| One slow-read rule (W-13, W-17, W-03; coordinator) | Fixed: services/api.js `SLOW_READ_BUDGETS_MS` + interceptor: a listed GET gets twice its route budget (min 30 s), a caller's own timeout wins, unlisted 10 s; Alerts Active/History show a second line after 4 s | slow-read-budget-r3-fj (8; 4 red), still-loading-r3-fj (1) |
| W-03 plan-watch `not_read` rows re-asked | Fixed: up to 3 re-asks through the queue, "Updating the numbers..." not "not available" | plan-watch-not-read-r3-fj (2) |
| O-C-05 "Checked at Time not available" | Fixed: each Checked-at line only when the time is known (builder, live card) | checked-at (8; 2 red) |
| O-A-08 /settings landing | Fixed: /settings redirects to /settings/app-settings | settings-landing-r3-fj (3) |
| W-20 / O-A-07 one stop, three decision (55) lines, no second wording | Confirmed green on this head, no fix | paper-stops-one-wording-r3-fj |
| W-01 reset sentence | Confirmed green (plan-reset-p8); "Use playbook as is" shows nothing of its own beyond the normal save result | |
| W-15 side toggle | OPEN: LegList.vue has no side toggle (B/S badge is a plain span); adding one is a product decision | |
| W-17 / W-02 / W-31 Positions plan-watch batch cancelled before the server answers | Not reproduced in code: the batch already passes its own 20 s above the 15 s budget and `cancelPlanWatchRead` only drops queued jobs | |
New wording (pending owner read): "Still loading. The server is taking longer than usual to answer." (Alerts Active/History after 4 s); "Not applicable: real position."; "Updating the numbers..." (existing, now also for a `not_read` row).
For the owner lane: confirm the server's real budgets for /alerts/active, /alerts/answered, /paper/alerts/records and the catalogue expiries route (12 s is an estimate from the PC notes; edit point `SLOW_READ_BUDGETS_MS` in frontend/src/services/api.js). Opus review of the stop/exit/order items in this group (O-A-12, not_applicable) was NOT run.

## Not done
- Item 7 browser walk (unknown exit on builder and Positions with second tab, moved leg with stop, Add to Paper after close, Live card Plan door, list Retry) and the UX-AF2 / UX-B03 re-check: not run.
- F5 as above; F7; builder's in-memory add lock still compares its local net key (never stored).
- Real-mode `GET /real/strategies/{id}/triggers` is read as the brief says; not checked against a live server.

## PC steps
Market closed: open a paper strategy, Exit with the server stopped mid-reply, confirm a second Confirm (same tab, new tab) sends nothing; reopen builder and Positions: the lock holds; the Orderbook link re-reads.
Live: repeat with a real unknown reply; check "Prices as of" / "Checked at" on the book panel.

## Tasks
| task | model | minutes |
|---|---|---|
| merged-base red + items 1-2 | Sonnet | 14 |
| item 4 | Sonnet | 4 |
| items 3, 5, 6, a-c | Sonnet | 32 |
| Opus review items 1-2 | Opus | 11 |
| round 2 fixes | Sonnet | 15 |

SAFE TO CLOSE (head 99db7820f, left: item 7 browser walk, d, W-15, F5, Opus review of the group B stop/exit items, round 5 re-review)

## Not done: coordinator's second PC list (arrived after the budget ended; a fresh lane starts on head 99db7820f)
1. T1-20 Home: the paused line lacks its as-of part ("Paper P&L paused ... as of <date>, <time> IST" as on Positions).
2. T3-10: Positions and Adjustment opportunities show no Retry after a failed load: the one failed-load rule must cover these two pages (my slow-read rule covers the time limit only, not Retry on these pages).
3. T3-09: a dismissed alert row shows no reason word.
4. T2-17: My Strategies lists no Completed rows: check the spec (Completed under My Strategies or only /strategies/completed-strategies); if by design, say so with the spec line and make the empty state say where they are.
5. O-R-09 / W-01: the Plan block of a running trade prints no stop or target figure: show them with units, or the reason none is set.
6. O-C-05 (Checked at): DONE in 99db7820f (checked-at.test.js, 8 tests).
7. O-P-01: one blocked exit shows two different reasons: one reason, the server's.
8. W-25: the Exit all text is cut off inside the dialog at 1366 by 768.
9. O-A-12 CONFLICT: the coordinator's later message says "pick the second" (Exit not greyed, the dialog opens and says why Confirm is off, ADR-330 (60) shape, both pages agree). What 99db7820f does is the first (a greyed Exit and the exit= link open nothing; the link writes a note). Reconcile with the owner or follow the coordinator's later text; the tests are exit-greyed-no-dialog-r3-fj and exit-not-live-good-read.
Items 1-5, 7, 8 are not started; nothing of them is on the branch.
