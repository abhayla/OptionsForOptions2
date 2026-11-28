STATUS 10:35 | items 2-6, a-c, TF built and gated (fea45e1 pushed, TF follows); item 1 PARTIAL: round 2 re-review REVISE, 4 findings parked (see Parked), GROUP A NOT READY; item 7 browser walk, d, e not run | next push 11:15 | blocker: none

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
Second Opus read of round 2 (commit fea45e1): REVISE. See Parked.

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

## Parked (item 1 stays PARTIAL; rule B1: two rounds spent, so parked with evidence, not a third round)
Opus re-review of fea45e1 found a path where a second exit goes out with a NEW key while the first can still commit (the 27 Nov case, 2 of 4 lots twice). To file as deferred issues; the attack tests (a1, b1, c1, e1) are in the lane's scratchpad and are to be moved into frontend/tests/ with the fixes:
1. CRITICAL `decideLock` verdict `changed` (unknownLocks.js ~102-110) ends the lock and drops the key inside the 130 s window when ANY other leg moved (a stop on another leg, expiry, another device). Callers: PaperStrategies.vue ~497, StrategyBuilderPage.vue ~895-896. Runs: Positions 503 on leg 776, read shows leg 784 at 0 and 776 unchanged => lock null, second POST new key; builder 2 of 4 lots the same. Recommended (fail-closed, not built): "moved" means an EXITED leg moved; an unrelated move counts as unchanged; the key is dropped only on stored or refused; `changed` never ends the lock before a read sent more than 130 s after the give-up.
2. CRITICAL another tab decides while the first POST is still out: `adopted()` (~143-148) turns `out:true` into `out:false, at: now`; PaperStrategies.vue ~515 sets `readSeq: seq - 1` so the adopting read counts as "after the reply" though no reply exists; `out` is checked only on the unchanged branch (~113). Mutation: removing `lock.out === true ||` leaves all 23 round-2 tests green.
3. MAJOR the builder checks the lock before `await readStops` (~743) and not after (~757 checks only exitBlocked); ~769 overwrites another tab's lock, ~808 drops it on 201. Run: builder Confirm with the triggers read held, Positions exit posts meanwhile, builder then posts too. Fix: re-check `exitLockFor` in the same synchronous step as `saveExitLock`, as Positions does (~574-583).
4. MAJOR one refused storage write (`storageWorks = false`, unknownLocks.js ~19, 24, 37) makes every later read ignore storage, so another tab's lock is invisible (fail open). Fix: read storage whenever possible and merge with memory.
5. MINOR a malformed entry without `before` locks forever (liveness); an `at` in the future holds until the clock passes it; the builder's add lock is memory-only (not held across reload or a second tab, same class as F3); round-2 tests do not catch mutations M4 and M6.
F7 (server keeps the key pending up to 600 s, a same-key resend can meet 582) also stays.

## TF defect (from test lane TF): builder `?strategy=1` says the paper position "could not be read" with no failed request
Cause: `readPaperBook` threw "unreadable" when the book and the catalogue both answered but the catalogue held none of the book's contracts (D-TD-3 scenario day in the past). Fixed: that state has its own sentence and still blocks the page (fail closed); a failed or malformed read still says "could not be read". Test builder-open-unmatched-r3-fj (3 tests). Not changed: three sites that pass null to `unreadableParts` (book names a different strategy id than the URL; a re-read that is not a paper book) still say "could not be read"; they need their own wording, owner to decide.
New wording (four parts): "This strategy's paper position was read, but its contracts are not in the catalogue for today, so it is not shown." / "The numbers on this page are not shown, so none of them can be mistaken for current values." / "Nothing was changed and no order was placed." / "Trying again will not help until the catalogue lists these contracts."

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

NOT SAFE TO CLOSE: item 1 parked remainder, item 7 not run.
