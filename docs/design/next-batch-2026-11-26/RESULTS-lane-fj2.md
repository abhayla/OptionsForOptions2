STATUS 20:20 | Lane F1 batch 1: head b0349e9b7+RESULTS, merged with integration/weekend-r3-1129, frontend 407 files / 4302 tests green; now ruff, repo_scan, prepush jobs 4, push | on origin: 68a46dd62 (items 1-2), 4297f7065 (F2/F3 hand-off branch) | blocker: none

# RESULTS Lane F1 (was FJ2), branch fix/r3-frontend-2-1128, base origin/fix/r3-frontend-joins-1128 (ddd656805)

The owner's 18:55 IST decision withdrew ADR-330 (64) (a real position gets the same Exit, Stops, Add as paper, nothing sent to Zerodha); the coordinator's replan gave the plan screens, Positions / Home sentences, list Retry and My Strategies to Lanes F2 / F3. This file lists only Lane F1's items.

## What is on the branch
| Commit | Content |
|---|---|
| 68a46dd62 (pushed) | item 1 paused sentence once with as-of (NOT_CONNECTED counted: 19 prints -> 1; Home and totals strip carry the time); item 2 server `not_applicable_text` |
| c72497cdf | I-206 / D-TG-2 leg-expiry Review dialog; item 6; O-P-01; F5 text A; ask() comment; clock +200 s pin |
| 0d9379634 + 3ce63ee4f + 3e47603c9 | Opus review round 1 fixes: F-A, F-B, F-D, F-C (the builder Add-to-Paper gate was built then reverted: owner decision) |

| Item | State | Red line (first) | Green |
|---|---|---|---|
| I-206 / D-TG-2 leg-expiry Review dialog | Fixed, not tested in a browser | leg-move-stop-line-fj2-1128: no `armed-exits` request for an exit row + an Add row with no usable price (the TG symptom), and the dialog sat on "Checking..." | 2/2 |
| 6 "No price for 4 of 4 legs; the server prices the exit when you confirm." with a stored close | Fixed: a contradiction of (60) (the dialog shows the legs and ONE market-closed line) and (63) | exit-closed-no-price-line-fj2-1128 (1 of 2 red) | 2/2 |
| O-P-01 one blocked exit, two reasons | Fixed on the one place found (blocked dialog also said the server prices it at confirm) | exit-one-reason-fj2-1128 (1 of 2 red) | 2/2 |
| 12 comment at ask() | Fixed (the gate on this page is blocked only by busy or checking) | | |
| 12 stale and missing legs, closed market | Proof added, no defect | exit-closed-stale-missing-fj2-1128 (4, green from the start) | 4/4 |
| F5 text A (I-132) | Built: hedged sentence after an unknown move when an armed leg stop was read before the post; cleared by the first decided stops read; no offer before. 774 test narrowed as the coordinator chose | paper-move-stop-offer-774 narrowed + 2 new cases (red before) | 9/9 |
| 7 / I-188 clock | Already fixed by FJ (87b3de2fb monotonic stamp); pinned for the exact case (+200 s right after the 503) | green on FJ's code (cannot show red here) | 2/2 |
| F-A Opus review: a 581 (same key, other body) dropped lock and key | Fixed: 581 is unknown, like 582 | lock-review-fj2-1128 (red), 2 older tests that pinned "581 refused" moved | green |
| F-B an add's key changed with every price tick | Fixed: `keySigOf` leaves an entry row's price out of the key's text | lock-review-fj2-1128 and save-bar-key-tick-fj2-1128 (red without the fix, shown by swapping the old line back) | green |
| F-C wall clock stepped back while a read is out | Fixed: `sentNow()` records the monotonic time of the send; decideLock uses it | lock-review-fj2-1128 (red) | green |
| F-D stored `at` of 0 / -1 / seconds read as long past | Fixed: below epoch-ms 1e12 counts from first sight | lock-review-fj2-1128 (4 red) | green |
| 8 builder add lock decided by decideLock | Nothing to change found: `addVerdict`, `recheckUnknownAdd` and `decideUnknownExit` all call `decideLock`; the reviewer attacked it and could not break it. (No local net-key compare of an add lock exists on this head; the net-key compares left in the builder are `restoreStaged`, which puts staged edits back and decides no lock.) | | |

## Opus review of group A (8d49a1d4d): REVISE
Answer to the question "which single code path guarantees no second order?": NONE. The server's request key de-duplicates only the SAME key with the SAME body, for up to 600 s, and its record is in Redis (lost on a restart or eviction). The browser lock is the only guard against a DIFFERENT second order while the first is still being placed, and it ends on a guess (130 s) at the server's commit window, which has no deadline. Decision (coordinator): the guarantee moves to the server (Lane B2: a durable per-strategy block while an order's outcome is unknown); the browser lock stays as the second line. What the browser lock may fail at without a double order: an early release followed by a resend of the same exit (stable text, price '0'): the server answers 582 or the first result.
Open (one line each, not fixed here):
- F-E If storage refuses the write, a reload loses both the lock and the key (unknownLocks.js memory fallback). Test idea: setItem throws, reload, Confirm must send nothing or the page must say storage is refused.
- F-F A page whose write once failed can wipe another tab's newer lock (unknownLocks.js merged copy written back).
- F-G One strategy's read past the window releases an UNREADABLE whole store for every strategy (writes `{}`).
- F-H The save bar's add ignores exit locks (SaveDraftBar.vue ~449 checks only the add lock).
- F-I Locks written by builds before the localStorage move (sessionStorage) are lost on upgrade; minor.
- F7 same-key resend can meet 582 for up to 600 s (a wait, no double order); N4 a sign flip reads "changed" not "placed" (wording).

LiveStrategyCard: the card itself is correct and pinned (Exit and Stops only when `position_kind === 'paper'`; tests position-kind-adr330-64, live-card-links-s14). With ADR-330 (64) withdrawn that pin must be reversed by the lane that builds "same Exit for real, nothing sent": it is not touched here.

## For the owner lane
- Backend (Lane B2): the durable per-strategy block; the request-key store is Redis (`backend/ofo_app/request_key.py`): a restart loses the pending claim. `request_key.begin` checks the body fingerprint BEFORE the pending check (a same-key resend with another body gets 581 although the first request is still being placed): the browser now treats 581 as unknown.
- Backend (Lane RA2): from the review, paper "open" rows on a strategy the server calls real are not refused (`paper.py` ~1480 refuses only exit rows); moot if ADR-330 (64) is withdrawn.

## Decided for the owner
- Exit dialog with the market closed: Confirm greyed (ADR-330 (60); the coordinator settled it 28 Nov 12:14 UTC). "No price for N of N legs; the server prices the exit when you confirm." is not printed then, nor while the exit is blocked (it promised a confirm that cannot happen).
- A 581 is "unknown": lock and key stay until a read decides.
- An add's request key does not depend on the entry price.
- A stored lock time that is not epoch milliseconds counts from first sight.
- NOT_CONNECTED strategies count with PAUSED ones for the one-sentence rule (pushed 68a46dd62).

## Question for the owner
2. I-14 wording: the unknown-result line is two sentences ("We could not confirm the order. Check Orderbook before trying again."); the coordinator asked for "one sentence". Recommendation: keep, it says the one thing (unknown) and what to do. I-101: after Exit all is Cancelled, should the exits stay staged? As built they do not.
1. Is a permanent block on unreadable lock storage acceptable, or a release such as "I checked the Orderbook"? Recommendation: no release in the app; the Orderbook is the authority (ADR-016).

## New wording for the owner to read
- `The stop on the old leg may have been cancelled, and the new leg has no stop until you set one.` (F5 text A, shown after an unknown move when a stop was armed)
- (pushed earlier) `Paper P&L paused - prices not live, as of <time> IST` on Home and the totals strip.

## I-139, I-14, I-101 (coordinator's definitions, 19:45 IST)
- I-139 page wiring (GitHub 870, 873): ALREADY BUILT on both pages (lock kept in localStorage, `locked` prop, decideLock); pinned with new tests: exit-lock-builder-wiring-fj2-1128 (Cancel does not release; failing reads plus 10 minutes of timers do not release; a second tab is locked) and exit-lock-positions-wiring-fj2-1128 (the same, on the Positions list). Green on first run: no defect found. Mutation note: removing the doExit lock check AND the dialog's `locked` term together leaves the tests green because further layers (ask(), the not-live gate, the 5 s hold) also stop the post; the tests pin the outcome (no second POST), not one line.
- I-14 unknown-result sentence: pinned on both dialogs: the dialog says `We could not confirm the order. Check Orderbook before trying again.` (one message, the shared constant PAPER_UNKNOWN_TEXT) with only the "Open Orderbook" button beside it (a re-read, not a retry), no "placed" / "failed" text, Confirm off; the stored case never says "could not confirm". The text is the owner's earlier wording: not changed. If "exactly one sentence" means a single sentence with one full stop, that is a wording change for the owner (Question 2).
- I-101 Exit all with a change staged (decision (59)): ALREADY BUILT in StrategyBuilderPage (DISCARD_WARNING, DISCARDED_TEXT, KEPT_UNTIL_KNOWN_TEXT, BACK_UNCHANGED_TEXT); 7 tests in exit-all-staged-adr330-59 pass, Lane TE recorded PASS. Not changed. The "nothing staged: does Cancel leave the exits staged?" half is the open owner question: as built, Cancel leaves NO exit staged (the staged change comes back exactly); not decided here.

## Not done
- W-25 (Exit all text cut off at 1366 by 768) and the browser walk (item 13): not run; the layout needs a browser.
- Worktree ../wt-f23 (purpose: the F2/F3 hand-off branch and its own check, created 28 Nov 19:25 IST) removed with plain `git worktree remove` at 20:15 IST; tracked files in the main tree 5401 before, 5401 after.
- Moved to F2 / F3 (pushed as fix/r3-frontend-f23-handoff-1128 = 4297f7065, prepush TOTAL PASS; a local backup branch `fj2-f23-handoff` at 218dbc3ab also exists): D-TG-3 Positions raw 409 JSON, D-TG-4 stale Stop box, plan card Target/Stop (O-R-09), My Strategies empty state (T2-17), Retry on the Positions Paper list (T3-10).
- Not reproduced: T3-09 (a dismissed row's reason word): the Opportunities row prints the server's `detail`; a dismissal with no reason carries none by the server's design (adjustment_opportunities.py:158).

## Tasks
| task | model | minutes |
|---|---|---|
| items 1-2, 3-6, 9, 11, 12 | Sonnet | 150 |
| Opus review of group A + LiveStrategyCard | Opus | 14 |
| review round 1 fixes | Sonnet | 40 |
