STATUS 21:35 | items 1 and 2 built (local commits), push 1 check running | item 3 (W-25 + browser walk) after the push | next push 07:30 | blocker: none (messages to the coordinator are refused: device trust; this line is the report)

# RESULTS Lane F1b, branch fix/r3-frontend-f1b-1128, base origin/fix/r3-frontend-2-1128 (d93fce449)

Successor of Lane FJ2 / F1. Paper only, no broker endpoint, money untouched (units only). Every item: failing test first (red shown by taking the fix out), fix, targeted tests, one commit.

## What is on the branch
| Item | State | Red line (first) | Green |
|---|---|---|---|
| 1 `releaseForeignDecided` (Positions) and `adoptForeignLock` (builder): a lock that VANISHES from the store released the unknown state at once. Site data cleared looks the same as another tab's decision, and a wipe also removes the request key: the next Confirm sent a second order under a NEW key | Fixed. A vanished lock alone releases nothing: the page keeps the lock it holds in memory (never written back, so two tabs cannot hand it to each other), reads again, and `decideLock` decides it (moved book = stored at once; unchanged only past the window on this page's monotonic clock). A page that DECIDES a lock now writes a marker (`ofo.lockDecided`, key + `at`) BEFORE it removes the lock; another tab releases at once only when it finds the marker for its exact lock (`lockDecidedElsewhere`) | exit-lock-wipe-f1b-1128 (Positions: 1 of 3 red: a second POST went out after a wipe), exit-lock-wipe-builder-f1b-1128 (2 of 3 red) | 3/3 and 3/3; the I-139 tests (second tab, builder wiring) green |
| 2 F-E storage refuses the write | Fixed: before a post that needs a lock, `canPersistLocks()` (probe write + read back). If it fails nothing is sent and the dialog says so (new wording below). Applies to Positions list Exit, builder Exit and Add, save bar Add | exit-lock-wipe-f1b-1128 (1 red) | 5/5; the old pin "private mode: this page's own lock still holds" (group-a-r2-lock-survives-r3-fj) moved to "nothing is sent" |
| 2 F-F failed-write page wipes another tab's newer lock | Fixed: the merged copy is built per strategy with the NEWER `at` winning (`mergeNewer`) | unknown-locks-f1b-1128 | green |
| 2 F-G one strategy's decided read wrote `{}` over an UNREADABLE store | Fixed: that strategy is freed on this page instance only (`garbageReleased`); the content is never written over, every other strategy stays locked | unknown-locks-f1b-1128 | green |
| 2 F-H save bar's add ignored exit locks | Fixed: `lockedAdd` also reads the exit lock of the strategy (the builder's rule); the bar listens to exit-lock storage events | save-bar-f1b-1128 | green |
| 2 R2-2 sent-time map keyed by wall ms | Fixed: `sentNow()` makes the wall value unique per read (+0.001 ms steps), one token per read | unknown-locks-f1b-1128 | green |
| 2 R2-5 builder half (add key kept through "not stored"; 581 keeps lock and key) | Tests added, green from the start: no defect found on the builder. A live PRICE TICK on the builder was not driven (the harness has no price source); the key rule (`keySigOf`) is pinned at unit level and on the save bar | builder-add-key-f1b-1128 | 2/2 |
| 2 R2-7 key saved by the earlier build (orders text with the entry price) | Fixed: `orderKeyFor` compares the orders text with entry prices left out on both sides (`sameSig`) | unknown-locks-f1b-1128 | green |
| 2 save bar `paperTarget` vs `target` key drop | Fixed: both `dropOrderKey` calls use `target` (the strategy the post went to) | save-bar-f1b-1128 | green |

Item 1 attacks run (reasoning plus tests): site data cleared (REAL: fixed above); a lock REPLACED by another tab (the page keeps blocking: `takeNewerGiveUp` moves the give-up time on, nothing is released); key-only storage events (the handler runs but releases only when the lock is missing AND the marker matches); the page's own drops (a storage event never reaches its own page); a reload in the middle of an open read (`out` locks are decided only by a read SENT past the window after `at`: unchanged by this lane). The marker can be forged only by a page of this browser; a wipe removes it with everything else.

## Opus review
Item 1 review (Why Opus: an early unlock allows a double order): see "Review" at the end of this file once it returns; findings that can cost money are fixed before the push, the rest go to batch 2.

## For the owner lane
- None needed from this lane's files.

## Decided for the owner
- A lock that vanished from the store is NOT a decision. The page waits for a deciding read (stricter than FJ2's "released at once"; a stored exit is still released at the next read, an unchanged book only past the window).
- A browser that will not keep the lock gets NO order from this app (fail closed). Cost: a user with blocked site data cannot place an Exit or Add until storage works. The server's block (Lane B2) stays the guarantee.
- An UNREADABLE store frees one strategy per page instance and is never rewritten by a decision (so after a reload each strategy waits one window again).

## Question for the owner
1. (FJ2 Question 1, unchanged, nothing built) Is a permanent block on unreadable or unchanged lock storage acceptable, or a release such as "I checked the Orderbook"? Real case: FJ2 / Lane W2, 28 Nov: a clock moved forward by 200 s across a reload released a lock after 46 real seconds (D-W2-1); the fix counts the window from first sight on the reloaded page, so an old lock waits up to one more window; a release by the user's own word would need an Orderbook check first. Recommendation: no release in the app; the Orderbook is the authority (ADR-016).

## New wording for the owner to read (pending owner read)
- `This browser is not letting the page keep its safety record, so nothing was sent. Allow site data for this page, then try again.` (LOCK_STORAGE_REFUSED_TEXT in unknownLocks.js; shown in the Positions Exit dialog, the builder dialog and the save bar when the browser refuses the write)

## Not done / to file as deferred issues
- Item 3 (W-25 text cut off at 1366 x 768; the browser walk) and the Opus review result: see below once run.
- Residual (deferred issue text): TITLE "A new lock written into an UNREADABLE lock store frees the strategies that were unreadable". EVIDENCE: `writeLock` starts from `entriesOf` (`{}` for an unreadable store) and writes a readable object over the garbage, so every OTHER strategy whose lock was inside it is gone after the first new lock. FILES: frontend/src/lib/unknownLocks.js (`writeLock`, `entriesOf`). A fix needs the owner's answer to Question 1 (a permanent block vs. a release).
- Residual: a wipe in one tab leaves a tab that opens AFTER the wipe with no lock (nothing to read). Only the server block (Lane B2) covers it. FILES: n/a (browser storage cannot keep what was deleted).
- Residual: a builder PRICE TICK between a "not stored" and its resend is not driven in a page test (see R2-5).

## Tasks
| task | model | minutes |
|---|---|---|
| items 1 and 2 (code and tests) | Sonnet | 60 |
| Opus review of item 1 | Opus | pending |
