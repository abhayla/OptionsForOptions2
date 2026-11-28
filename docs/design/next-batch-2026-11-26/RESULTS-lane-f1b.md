STATUS 01:00 | review round 2 done, its money finding fixed (builder add vanish without event), full vitest 4337/4337, final check running | hand-over below | blocker: none

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

## Opus review of item 1 (reviewer agent, Opus): REVISE, round 1 fixed
Attack: can the release paths let a second order be SENT while an outcome is unknown? No regression found (nothing releases earlier than before the lane). What it found and what was done (every one tested first, red without the fix):
| Finding | Severity | Done |
|---|---|---|
| 1 the builder's ADD lock (and the save bar's) was still released when it vanished (a wipe), a second add went out under a new key | can cost money | FIXED structurally: every page keeps the raw lock records it wrote or read (`held`); on a storage event a held lock missing from the store WITHOUT a decided marker is written back with its request key (`restoreVanished`), with a marker the hold ends. One rule for Positions, builder (exit and add) and save bar. Tests: builder-add-key-f1b-1128, save-bar-f1b-1128 (red without) |
| 2 `canPersistLocks` said yes while the real lock write failed (a nearly full store) | can cost money | FIXED: `lockPersisted(kind, id, key)` reads the store back after the writes and before the post (lock AND key); on failure the lock and key are dropped, nothing is sent, the sentence below shows. The probe stays as the early check. Test: exit-lock-wipe-f1b-1128 (red without) |
| 3 F-G: the NEXT lock save over an unreadable store writes over the garbage | minor | NOT FIXED (a fix needs Question 1): listed under residuals |
| 4 each storage event started another re-read loop on the builder | minor, not money | FIXED: one loop per unknown record (`recheckingExit`) |
| 5 the marker names a lock by (key, at); a clamped `at` or a reused key could match | minor | FIXED: every lock write has a nonce, copied into the marker and matched first |
| 6 `mergeNewer` can bring back a lock another tab decided | minor, fails closed | not changed (blocks again until a read decides) |
| 7 `sentNow` tokens unique only among the last 64 | minor | not changed |
Reviewer's "not covered": the server block; real browser quota or "clear site data" events (simulated with dispatched events); a reload in the middle of an open read at component level; a possible older gap: PaperStrategies has no stale-screen gate like the builder's `paperStale` after a marker release (until `refreshNow` answers it may offer Exit on old rows under a new key; the server block covers it). Round 2 of the review has NOT been run (the second round is for the batch-2 diff).

## Opus review round 2 (reviewer agent, Opus): REVISE, money finding fixed, rest listed (two rounds used)
| Finding | Severity | Done |
|---|---|---|
| F1 the builder's ADD path (`addEndedElsewhere`) released a vanished lock with no marker check; with `localStorage.clear()` and NO storage event a second add went out under another key (run by the reviewer: 2 posts) | can cost money, open since before the lane | FIXED: the held add keeps its lock in memory (`addUnknown.lock`); a vanished lock with no decided marker is written back with its key and the recheck loop goes on. Test first (red): builder-add-key-f1b-1128 "a same-tab wipe without an event". The old pin "a lock another tab removes" now passes the lock it decided (a real decider writes the marker) |
| F5 a restored key never matched again (sig text) | not money | FIXED: the restored key slot uses `keySigOf` text |
| F2 the NEXT lock save over an unreadable store overwrites it (F-G second half) | minor | NOT FIXED (needs Question 1); hand-over |
| F3 (a) marker write refused while the removal goes through: the other tab restores the lock every cycle; (b) one marker per strategy and kind: a frozen tab restores an older lock | minor, not permanent (at most one window) | NOT FIXED; hand-over |
| F4 the real-write cleanup drops a request key kept on purpose after "not stored" | minor, not money | NOT FIXED; hand-over |
| F6 an old marker without a nonce matches a lock with no `at` and the same key | minor, narrow | NOT FIXED; hand-over |
| F7 Positions has no stale-screen gate after a marker release (a Confirm before the list read returns is built from old rows under a new key) | not money in practice behind Lane B2's server block, older than the lane | NOT FIXED; hand-over |
Held up: two tabs with a marker (no bounce), wipe with an event (lock and key restored), exit paths with a same-tab wipe and no event, save bar same-tab wipe, `canConfirm` includes `locked` (the window line is text only), `sameSig` only for 'add', held-map growth, no permanent block in normal flows. Not covered by the reviewer: whether a real browser's "Clear site data" fires storage events; whether Lane B2's block refuses a second ADD (if it does, F1 was browser-only); builder Retry; the `tracking.js` text; mutation runs.

## For the owner lane
- OUTSIDE MY EDIT LIST, done because the guard's own message demands it (screen-inventory-guard failed the full check on the new Retry button): one row BUILD-192 added to docs/design/next-batch-2026-11-26/screen-inventory.md and screen-inventory.json regenerated with `node frontend/e2e/support/inventory-extract.mjs` (the JSON diff is large only because line numbers shifted; no other control changed). Another lane that edits the same file will meet a textual conflict: take both rows and regenerate the JSON.

## Decided for the owner
- A lock that vanished from the store is NOT a decision. The page waits for a deciding read (stricter than FJ2's "released at once"; a stored exit is still released at the next read, an unchanged book only past the window).
- A browser that will not keep the lock gets NO order from this app (fail closed). Cost: a user with blocked site data cannot place an Exit or Add until storage works. The server's block (Lane B2) stays the guarantee.
- An UNREADABLE store frees one strategy per page instance and is never rewritten by a decision (so after a reload each strategy waits one window again).

## Question for the owner
1. (FJ2 Question 1, unchanged, nothing built) Is a permanent block on unreadable or unchanged lock storage acceptable, or a release such as "I checked the Orderbook"? Real case: FJ2 / Lane W2, 28 Nov: a clock moved forward by 200 s across a reload released a lock after 46 real seconds (D-W2-1); the fix counts the window from first sight on the reloaded page, so an old lock waits up to one more window; a release by the user's own word would need an Orderbook check first. Recommendation: no release in the app; the Orderbook is the authority (ADR-016).

## New wording for the owner to read (pending owner read)
- `We could not confirm the order. Check the Orderbook; no second order is sent until the answer is known.` (PAPER_UNKNOWN_TEXT; replaces `... Check Orderbook before trying again.`)
- `This browser is not letting the page keep its safety record, so nothing was sent. Allow site data for this page, then try again.` (LOCK_STORAGE_REFUSED_TEXT in unknownLocks.js; shown in the Positions Exit dialog, the builder dialog and the save bar when the browser refuses the write)

## Coordinator items done in batch 1 (messages 15:50 and 16:03 UTC)
- Unknown-outcome sentence (no retry invited): was `We could not confirm the order. Check Orderbook before trying again.` now `We could not confirm the order. Check the Orderbook; no second order is sent until the answer is known.` Test dialog-unknown-f1b-1128 (red first); the pin in paper-add moved.
- "Two minutes have passed ..." followed the wall clock on a dialog opened while a lock stood: now counted on the lock's own monotonic stamp (`monoAgeOfAt`), else the dialog's first sight; never the wall age. Test dialog-unknown-f1b-1128 (red first); exit-lock-window-r2-fa2 "dialog opened later" now stamps the lock like a page does.
- W-25 (found in a real browser: Chromium, 1366 x 768, the real PaperConfirmDialog with four exit rows): the Exit all discard note sat below the four rows inside a body that scrolls (608 px of content in 512 px), out of sight while Confirm was in view. Now the note comes first. Test dialog-note-first-f1b-1128 (red first); screenshot after: the note is the first thing in the dialog.
- Builder Retry (I-86): done (builder-open-retry-f1b-1128, red first: a failed open showed the sentence and no Retry; Retry reads the URL's strategy again; not-found keeps its own door and shows no Retry). Merged into this push (non-money).
- Lane W2 defects: D-W2-1 (clock +200 s across a reload) and D-W2-2 (second tab stayed locked after a stored exit) are in this lane's files and were fixed in 335e9d1bf and 3a7986145 (inside 4201d3af2); this lane tightened D-W2-2's release (marker or deciding read). D-W2-3 (Plan block stop/target) is Lane F2's.

## Not done / to file as deferred issues
- The rest of item 3 (the FJ2 browser walk: unknown exit on the builder and Positions with a second tab, moved leg with a stop, Add to Paper after close, Live card Plan door, list Retry; UX-AF2, UX-B03): not run yet (needs the app with its backend and a market state; only the dialog was rendered in a real browser). Batch 2.
- Residual (deferred issue text): TITLE "A new lock written into an UNREADABLE lock store frees the strategies that were unreadable". EVIDENCE: `writeLock` starts from `entriesOf` (`{}` for an unreadable store) and writes a readable object over the garbage, so every OTHER strategy whose lock was inside it is gone after the first new lock. FILES: frontend/src/lib/unknownLocks.js (`writeLock`, `entriesOf`). A fix needs the owner's answer to Question 1 (a permanent block vs. a release).
- Residual: a wipe in one tab leaves a tab that opens AFTER the wipe with no lock (nothing to read). Only the server block (Lane B2) covers it. FILES: n/a (browser storage cannot keep what was deleted).
- Residual: a builder PRICE TICK between a "not stored" and its resend is not driven in a page test (see R2-5).

## Tasks
| task | model | minutes |
|---|---|---|
| items 1 and 2 (code and tests) | Sonnet | 60 |
| Opus review of item 1 | Opus | 12 |
| W-25 browser render | Sonnet | 10 |

Scratch worktree ../wt-next (purpose: build W-25 while the check ran on the main tree, rule 4; created 28 Nov 21:36 IST) merged back and removed with plain `git worktree remove` at 21:48 IST; tracked files 5411 before, 5411 after plus the new test files (merged).

## Friction (rule I1; docs/process is outside this lane's files, so here)
- The box lacked ruff, fastapi and sqlalchemy: the gate would not start until `pip install -r requirements-dev.txt -r requirements-app.txt` and `ruff==0.15.12` (same as FJ2's note).
- Three full checks (about 22 min each) each failed on ONE frontend test the targeted runs missed (an old pin of changed behaviour, the ADR-008 `Math.min` lib scan, screen-inventory-guard for a new control). Running the whole vitest suite once before starting prepush would have caught all three. Suggest: a `npm test` run in the pre-check list for any lane that adds a control or touches lib/.
- The kit write-guard blocked `git add` for the whole run of a reviewer subagent; a removed worktree path stayed blocked by the prod-gate hook (a new path worked); `git stash` in a worktree is blocked.

(older line, superseded by the one at the very end)
SAFE TO CLOSE-old (head 83baad95c; left: the FJ2 browser walk (needs the app with its backend), Opus review round 2 of the batch-2 diff, F-G second half and FJ2 Question 1 (owner), the deferred-issue texts above)

## Hand-over to a successor lane (nothing below is started)
Named by the coordinator (28 Nov 23:00 IST):
1. The save bar (SaveDraftBar.vue) polls the `execute:<id>` locks and gets a 422 every 5 seconds (checkAddUnknown decides locks of ids that are not builder strategies).
2. The PC's note: after Exit then Cancel on the builder one staged exit stays and the first Discard does not clear it (a reload does).
3. The builder's book panel greys every Exit after a failed read: a clash between an older rule and ADR-330 (60): a QUESTION FOR THE OWNER, not to be decided.
From this lane:
4. F-G second half and FJ2 Question 1 (permanent block vs a release such as "I checked the Orderbook"): the next lock save over an unreadable store overwrites it (unknownLocks.js `writeLock`, `entriesOf`). Owner answer first.
5. Round 2 minor findings F3, F4, F6, F7 above (files: unknownLocks.js `markDecided`, `lockDecidedElsewhere`; PaperStrategies.vue, StrategyBuilderPage.vue, SaveDraftBar.vue real-write cleanup; PaperStrategies `releaseForeignDecided` needs a stale-screen gate like the builder's `paperStale`).
6. The browser walk of FJ2 item 3 (Lane W3 walks the build); a builder price tick between "not stored" and a resend is not driven in a page test.
7. To file as deferred issues (coordinator): the residuals in "Not done" above and items 4 and 5.

SAFE TO CLOSE (head = the commit of this section; the check of that head ends TOTAL PASS before the push; left: the hand-over list above)
