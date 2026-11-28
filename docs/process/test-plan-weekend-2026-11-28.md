STATUS 20:05 | TG2's six plan faults corrected (W-09 PATH-10, W-23 colon, TC-3 menu entry, W-10/W-11 TEST_CATALOGUE_DATE with the Completed/Acted-on word left to the owner, W-15 built sentence, W-21 PC only); round 3 build head a1d70422 (wave 0, 0062 in); ADR-330 (73) not in round 3 | previous push 8a9fa59a8 | next: round 2 results fold-in, wave versions

# Test plan for the closed-market weekend, 28 and 29 Nov 2026 (rounds 1 to 3)

Version 6b, Sat 28 Nov 2026, evening IST (for round 2, Sat 21:00): cloud first, round 2 commit frozen. Written by Lane X2 (documents only; no product code read or changed).
For the owner's PC session. The market is closed until Mon 30 Nov 09:15. Three rounds, each started by the owner; the **PC session is reused** for all three; the message for each is in section 13. The app on the PC has 9 running paper trades, no Kite
login and no live feed. **Paper only: never place or send a broker order.** Monday's live plan is `docs/process/test-plan-2026-11-30.md`.

Version log: v1b Fri 19:40; v1 Fri 22:30 (all lane result files read); **v2 Sat early morning: round 1 is the commit named in section 1, only checks that commit can pass, every check names its board items, the three open findings F1 to F3 are known and not a round 1 failure, two PC data pulls (section 8), round 2 checks (sections 7 and 9).** Next: the round 2 update when the coordinator sends the round 2 branch list. **v3 and v3b (this file; v3b adds Lane FE, Lane FA's new status and the builder walk): a one-page "What to read before 08:00" for the owner; SW-2, SW-6, T1-20 and the sweep corrected against Lane TC's walk of the round 1 commit; the five checks TC could not walk are PC checks in round 1 (TC-1 to TC-5); the round 2 section is built from the fix lanes' result files (one check per fix).** **v4 (this file): the 16 plan and set-up faults of round 1 corrected (the page "Plan version 4" below), the round 2 set-up with the screen-server restart and the route check, W-26, W-32, W-34, W-04 rewritten, one line on every row for FAIL or PARTIAL, the round 2 section rebuilt from the lanes' result files.** **v5 (this file): the PC's seven set-up lessons of the round 1 close folded into section 2 (new block "Lessons of the round 1 close"), every query corrected to select by strategy id and to the real alert tables, memory and speed rules added (rules 15 and 16), migrations 0060 then 0061 applied in one step, the round 1 results expected to be fixed listed on the page "Plan version 4 for round 2".** **v6 (this file): the page "Version 6: CLOUD FIRST" at the top: every check is CLOUD or PC ONLY with a one-phrase reason and its proof; the PC runs the set-up, the PC ONLY checks and a sample of ten (about 254 minutes); rule 17.** **v6b (this file): the round 2 commit `829ff65f` named throughout; the page "Version 6b: READ THIS FIRST" (PC-first faults, TG's seven plan faults, proof level per check); W-26, W-34, W-02, W-03, SW-8, SW-9, R2-0, R2-FD, R2-FA corrected.** **r3 draft (this file): the page "Round 3 page" before the version 6b page.**

## Round 3 page (Sunday 12:00 to 16:00): DRAFT against `integration/weekend-r3-1129`; the final commit is sent at the freeze (Sunday 10:00 IST)

**Build.** Branch `integration/weekend-r3-1129` (Lane Z3). First push `4d975129f273300fc61096a0704784ee42537337` (28 Nov): only three commits above round 2 (`829ff65f2`): FJ's tests (`1ad97343`), the merge of `fix/r3-frontend-joins-1128` at that commit, and Z3's RESULTS file. **Today's diff against round 2 is tests and notes only: no product file differs, so round 3 as it stands today behaves exactly like round 2.** Z3's own line: "ROUND 3 READY FOR THE PC: no (first batch only)". More merges arrive at 21:00 IST Saturday, 07:00 and 10:00 IST Sunday; the build is frozen at 10:00 Sunday and the coordinator sends the final commit. **The next version of this page names that commit and re-marks each lane below with `git merge-base --is-ancestor <branch tip> <commit>`; until then every row says "IF MERGED".**

**Round 3 rules (same as round 2).** Cloud first (rule 17): the PC runs only the lists below. One browser window, one helper at a time, free memory above 3 GB (rule 15). Paper only; never a broker order. Restart the API, the worker, the feed and the screen server (vite) after the checkout; the API's environment carries `FEED_MODE=bus` and `REDIS_URL` (R2-0). Write `git rev-parse HEAD` first. Keep `test/weekend-r1` and `test/weekend-r2` as they are; round 3 uses `test/weekend-r3`. Never `alembic downgrade` except the stated rollback.

**Waves of Lane Z3 (coordinator, 28 Nov 18:45 IST): wave 0 now, wave 1 at 22:45 IST, wave 2 at 01:45 IST Sunday, final at the 10:00 IST Sunday freeze. Each version of this page says the build head it was written against; this version: `4d975129` (wave 0 not yet seen).** Migration 0062 arrives with wave 0, so the round 3 pull order has a database step before the restart:
1. Back up the database; the owner's typed yes before any apply ([OWNER APPROVAL]).
2. `git checkout -b test/weekend-r3 <final commit>`; `git rev-parse HEAD` equals it.
3. Migrate: the section 2 step 3 command; `alembic heads` prints ONE head, `0062_order_request_keys_expiry`; `alembic current` prints the same.
4. The "back and up" check (down to 0061 and up again) is the lane's proof on a FRESH TEST database (`db_run_fresh.py`); it is NOT run on the production database. A downgrade on the real database only on the owner's written word (the rollback is `alembic downgrade 0061_order_request_keys`, nothing else).
5. Restart API, worker, feed, then vite; the route check R2-0b.

**PC ONLY list, round 3 (kept current, coordinator 28 Nov 18:45):** W-04, W-22 (PASSED in round 1: not repeated), AF-07, D-1, D-2, I-85, and R3-T (the real triggers route content). **Live list (Monday only, market open):** I-09, I-21, I-108. (I-85, I-09, I-21 and I-108 are board rows; this plan does not carry their wording: the board text is the source, and the PC reads it there.)

**PC keep-alive (board row I-95):** the PC stays awake for the whole run: power plugged in, sleep and screen lock off, the screen server, API, worker and feed left running between checks, and the machine checked at the start of each round (the PC session is reused for all three rounds). This line is written in rule 18 of section 0. **I-95 is NOT closed by this line: the owner's go-ahead is not on record.**

**Build head seen (coordinator, 28 Nov 19:35 IST): `a1d70422` (wave 0; migration 0062 is in it).** **Decision ADR-330 (73) (real positions get the same screens as paper, nothing sent) is on `origin/fix/ic-live-test-1123` (`6423c95ea`), built on separate branches, and is NOT in round 3 unless the coordinator says so: this page keeps the 27 Nov rule for real rows; this may change.**

**Lane TG2's six plan faults (`test/r3-plan-walk-2-1128`, head `c4f43ddb8`) are corrected in the checks: W-09 (PATH-10), W-23 (`holdback:create_app`), TC-3 (a menu entry), W-10 and W-11 (`TEST_CATALOGUE_DATE`; W-10 word conflict "Completed" / "Acted on" left to the owner), W-15 (built sentence "or change one of them"), W-21 (strategies 194 and 201 exist on the PC only).**

### R3-A. What the PC does first (set-up delta, about 25 minutes)
1. `git fetch origin integration/weekend-r3-1129`, `git checkout -b test/weekend-r3 <the final commit>`, `git rev-parse HEAD` must equal it.
2. **Migrations:** round 2 applied 0060 then 0061. **Round 3 adds ONE migration only IF `fix/r3-leftovers-1128` (RA) is merged: `0062_order_request_keys_expiry` (revises 0061; narrows the app role's INSERT on the order-request-key table to six columns and adds a SECURITY DEFINER expiry function with a 7-day window; the app role still has no DELETE; up, down, up checked by the lane; one head).** `ls backend/ofo_app/alembic/versions | tail -n 3`: if 0062 is there, `alembic heads` must print `0062_order_request_keys_expiry` after the apply; applying it is [OWNER APPROVAL] after a verified backup (the owner's typed yes), same command as section 2 step 3. Lane RA says new code on an un-migrated database only skips the expiry, so migrate and restart in one sitting; a rollback of this migration is `alembic downgrade 0061_order_request_keys` and nothing else.
3. Restart vite and check the routes (R2-0b), including `/api/real/strategies/<id>/triggers`.
4. No new seed (round 1's 17 closes stay). Memory check.

### R3-B. PC ONLY checks of round 3 (the cloud cannot do these)
| Check | What | Why PC ONLY |
|---|---|---|
| **R3-T Real triggers content (new, coordinator 28 Nov)** | `GET /real/strategies/{id}/triggers` (through vite: `/api/real/strategies/<id>/triggers`), **read-only**, on a REAL position. Round 2 already confirmed it answers 200 with an empty list for a strategy with none (Lane FD2). Round 3 reads the CONTENT on a real position: `triggers`, `already_set`, `already_armed`; write the keys and counts only, never a price. Lane FJ's "Not done": this route was never checked against a live server. | needs his real position and a live server |
| **AF-07 Zerodha disconnected (coordinator, 28 Nov; Lane TG: not reached in the cloud)** | With no Zerodha session: the Real total reads dashes (TG saw this already in the cloud), the Connect sentence shows, and the raw JSON of the 409 must NOT print on screen (known D-2 / D-TG-3 until fixed: write "known" if it still prints twice). Each of the other nine screens that carry a real figure shows the same sentence. | his real broker state (none) and his nine real trades |
| W-04, D-1, D-2 pulls | Done in round 2 (PC ONLY list of round 2). Round 3 re-runs one only if its round 2 line was FAIL, PARTIAL or BLOCKED. | his data |
| W-22 | **PASSED in round 1: stays passed, not repeated.** | his data |
| Round 2 sample failures | Re-run on the PC every check of round 2's list (PC ONLY and sample) that ended FAIL, PARTIAL or BLOCKED, once, on the round 3 commit; each is tagged "new" or "known". The round 2 results are not posted yet (last PR #722 comment 28 Nov 12:03 UTC: PC "NOT ready for 21:00 browser work"); the next version of this page lists them. | his data and link |

### R3-C. Lane checks of round 3 (IF MERGED; each is cloud-proven first, the PC does a sample)
| Lane | What a user sees (plain words) | Check on the PC, market closed |
|---|---|---|
| **FJ** `fix/r3-frontend-joins-1128` (in today only up to `1ad97343`, tests; the newer head `ddd65680` is NOT in) | The Exit control always opens the dialog: with the market closed it shows the server's sentence "The market is closed. Exits can be placed from 09:15 on <next trading day>." with Confirm grey and nothing posted; with a leg that has no live price the not-live line shows and Confirm is off. One lock and one key against a double order on every page: after an unknown reply a second Confirm sends nothing, across reload and a second tab; the Orderbook link re-reads. `/settings` opens `/settings/app-settings`. | Open a paper strategy, press Exit with the server stopped mid-reply, press Confirm a second time (same tab, new tab): nothing is sent (count POSTs before and after). Reload the builder and Positions: the lock holds. Live part (Monday): a real unknown reply. **FJ results say "Fixed, not tested in a browser".** |
| FJ new sentences (owner read pending; only if the newer head is merged) | "The plan watch has not been read for this trade." / "No broker is connected, so no real positions are shown." / "No price for <contract>" / "Prices as of <time>" and "Checked at <time>" / "The stop on a leg was removed with the move; set a new one on the new leg." / "Not applicable: real position." (stop row of a real position, no badge, no Cancel) / "Still loading. The server is taking longer than usual to answer." (Alerts Active and History after 4 seconds) / "Updating the numbers..." | Read each where it shows; write the sentence seen; never rewrite it. |
| **FD5** `fix/r3-backend-5-1128` (NOT merged today; no migration) | A real position (a basket sent to Zerodha) refuses every paper order with "Real position: exit and protect it in Kite."; a held condor ("Held at my broker") still lets you record an add or open, but Exit is refused. A rupee loss stop on Alerts reads "Plan loss stop" (was "Plan rupee stop"). Alerts > History loads far faster (62 database reads for 12 strategies down to 6). | Alerts > History with 10 or more answered alerts: loads in about a second (write the server's own time). A rupee loss stop alert reads "Plan loss stop". On a held condor record an add: stored; try Exit: refused with the Kite sentence. (With the market closed the refusal "The market is closed. Orders can be placed once it opens." comes first: tell the PC to write which sentence it sees.) |
| **RA** `fix/r3-leftovers-1128` (NOT merged today; ONE migration, 0062) | New refusal "This took too long, so no order was stored." / "Nothing was stored and the strategy was not changed; pressing again places the orders once." / "Placing these paper orders." / "Press Place again." Open and add on a real position use the Exit words "Real position: exit and protect it in Kite." "Plan loss stop" wording. A paper `stop` on a held or real position is refused; `settle` is allowed. | Only the two refusal sentences are visible with the market closed; the "took too long" sentence needs a slow request: not run by hand. |
| **FE4** `fix/r4-worker-4-1128` (NOT merged today; no migration) | The worker publishes why monitoring is paused ("market_closed" and the others); an unknown reason reads "Not being watched: the reason is not known."; the old armed stop of a real position with the market closed reads "not applicable", not "watched". Issue 876 (a 10 percent loss crossed a 5 percent rule for 14 minutes with no alert) is NOT reproduced; cause unknown. | W-34 again on the round 3 commit (planned and unplanned trades). Issue 876: the PC writes the worker log lines and the stored plan body of strategy 207 (words and counts only) if it can still see the 14-minute case. |
| FD, FA, FB2, FC2, TF (the last one or two commits of each branch) | Notes only in their RESULTS files; their work is in round 2. | none |

### R3-D. Open owner questions that bear on round 3 (recorded, not judged; each check says "owner decision pending")
Whether a held condor may record an add or open while Exit is refused (FD5); one word for rupee and percent loss stops (RA, recommended: same word); an unsent execution plan row blocking paper orders (RA, recommended: an explicit "I did not send it" button); permanent block when lock storage is unreadable (FJ); whether the table total follows the "Add booked P&L" switch (FJ); a lock for the Execute page (FJ); W-26 case B (round 2).

### R3-E. Time (to be fixed in the next version): set-up delta about 25 minutes, PC ONLY about 30, round 2 re-runs about 10 minutes each, lane sample about 40.

## Version 6b: READ THIS FIRST (round 2 commit frozen; Lane TG's seven plan faults corrected; proof level per check)

**The round 2 build is frozen: `integration/weekend-r2-1128` at `829ff65f26716f1efbcbac98ea3ba6aefdc350d9`** (coordinator, 28 Nov 17:15 IST; Lane Z2's final RESULTS: ADR-330 (60) regression closed by FJ `8d4355df2`, sixth review SHIP, READY yes). The PC runs `git rev-parse HEAD` after the checkout: it must print exactly this commit; write it in the results. Both migration files are in it (`0060_plan_stamp_only_on_switch`, `0061_order_request_keys`; `alembic heads` prints one head, `0061_order_request_keys`). Not in this commit, so BASELINE for the PC: `fix/r3-backend-5-1128` (FD5, 28 commits ahead), `fix/r3-leftovers-1128`, `fix/r4-worker-4-1128`, and the last commits of `fix/r2-exit-stops-1128` (FA), `fix/r2-builder-2-1128` (FB2), `fix/r2-pages-1128` (FC2), `fix/r2-backend-1128-fd` (FD), `fix/r3-frontend-joins-1128` (FJ, 2 commits after `8d4355df2`: the Exit fix itself IS in). Section 9 has the full list, checked with `git merge-base --is-ancestor` on 28 Nov.

### A. What the PC reads FIRST tonight: faults of the plan found by Lane TG that touch a PC ONLY or sample check
(Lane TG = the cloud walk of the plan, `test/r2-plan-walk-1128`, head 72845ce53. Each line: the check, what was wrong, what to do.)
1. **Set-up R2-0 (every check depends on it): the API's environment MUST carry `FEED_MODE=bus` and `REDIS_URL`.** Without `FEED_MODE=bus` the API treats "no bus" as "no worker" and EVERY trade reads "Not being watched: no worker has reported in the last 2 minutes." even with the worker running (round 1's W-34 reading may have been partly this). The worker runs as its own process. Check this before W-34.
2. **W-34 (sample): the reason sentence needs a PLAN.** The worker lists only trades that have a plan. A running trade WITH a plan reads (cloud, market closed): "Monitoring paused" / "Health unknown" / "The market is closed." / "Since HH:MM". A running trade with NO plan reads "Not being watched: the worker does not list this trade." with "No plan: nothing is watched for this strategy" beside it: that is the reader's design, not a worker fault. **The PC writes, for each of its nine trades, whether it has a plan.** Round 1's "all nine unwatched" may have been nine trades with no plan.
3. **W-32 (sample): KNOWN FAIL in the cloud (D-TG-2).** The Review dialog of the leg's own expiry control does not print "The stop on <leg> will be removed; set a new one after the move." (the server returns it when asked by hand; the page sends no `armed-exits` or `exit-risk` request). If the PC reads the same, write "known D-TG-2": not a new fault.
4. **W-33 and the nine screens (sample/PC ONLY): with no Zerodha session the stored close shows on every screen (D-1 fixed) but every running trade's paper P&L stays "P&L —" / "Paper P&L paused - prices not live" and Home reads "4 strategies left out" (known D-TG-1).** Expect it; write "known D-TG-1". Also expect `Paper P&L paused - prices not live` many times on Positions > Paper (D-TG-5, eight times in the cloud; R2-FC2 step 5 expects it once) and the raw `{ "error_class": "BROKER_AUTHENTICATION", ... }` text twice on Positions with no session (known D-2, TG D-TG-3).
5. **W-02, W-03, W-13, W-17 (sample): what the page prints while it waits.** Plan watch: the box line "Loading the rule check..." (builder: then "Updating the numbers" at about 22 s) is the expected text; **"Still loading. The server is taking longer than usual to answer." is printed on Alerts (Active and History) only, and only at about 22 s** (nothing for the first 14 s). The plan watch never prints it inside 12 s. Write what you see; if the PC sees "The plan watch is not available right now." or "The page could not get an answer from the server." at 6 to 24 s, that is round 1's fault back. **The real link time is proven nowhere in the cloud: the PC is the only evidence of it** (write the server's own answer time from the API log beside each).
6. **W-25 (sample): the Exit dialog with the market closed** reads "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov." with the legs listed and Confirm grey (cloud PASS). Parts B, D, E (feed or API stopped) are PC only.
7. **SW-6 (sample): Add to Paper with the market closed.** First a box "Name this paper trade ... A name can be up to 20 characters."; then the dialog "Add to Paper ... Held at my broker  This is not a real trade. ... Orders can be placed from 09:15 on Monday 30 Nov." **Confirm is grey and there is no tick box** (cloud PASS). On the PC the server's refusal "The market is closed. Orders can be placed once it opens." (409) is the proof for paper order rows before and after.
8. **R2-FD2 (PC ONLY), step 2: `GET /positions` is read on the API's own address (for example `http://127.0.0.1:8000/positions`), NOT through the vite address: through vite that path is the page.** Step 3 (`/api/real/strategies/<id>/triggers` through vite) is right as written. `GET /api/market/indices` with no session may show SENSEX as unavailable while Home shows the SENSEX close: write both.
9. **R2-FA step 4 (the Exit dialog on Positions):** in TG's first walk (before FJ `8d4355df2`) "Exit (1)" was DISABLED on Positions > Paper while prices were paused. **`829ff65f26716f1efbcbac98ea3ba6aefdc350d9` contains FJ `8d4355df2`**: with it TG saw "Exit (1)" ENABLED and the dialog open with "No price for 1 of 1 legs; the server prices the exit when you confirm.", "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov." and Confirm grey, both on Positions and on the builder. Expect the dialog on both; if Exit (1) is disabled on Positions, write it (known, old behaviour) and use the builder.
10. **W-26 (cloud first; not on the PC list): there is no per-leg lots control on a running trade; use the Multiplier, ALL legs rise, and the discard sentence names every leg** (below, fault 1).
11. **TC-5 (PC ONLY): address `/strategies/completed-strategies` PASSED in the cloud** ("closed 27 Nov 2026, 10:45:00 IST", Final P&L, Charges, Net after charges, Adjustments made); **a settlement needs an expiry day, so a settled trade cannot be walked in the cloud**: the PC reads its real settled trade, if it has one, else writes "none".
12. **SW-9 and SW-8 (sample support): addresses.** The Stops panel is inside Positions > Paper (`?tab=paper&strategy=<id>`); Live Strategies "Stops" opens it. Alerts has no Records page: "Records" is the block "Stops and expiry settlements" on Alerts > History.

### B. Lane TG's seven plan faults and where this version corrects each
| # | Fault found by TG | Where corrected |
|---|---|---|
| 1 | W-26 step 2: there is no per-leg lots control on a running trade; use the Multiplier; all legs rise; the discard sentence names every leg | W-26 steps and expected text |
| 2 | SW-8: "Records" is not a page (`/alerts/records` is "Page not found"); it is the block "Stops and expiry settlements" on History | SW-8 steps |
| 3 | W-26 case B: the dialog has no discard sentence, Confirm grey; after Cancel "4 pending changes" and the staged-exit line remain with a Discard button | W-26 case B text |
| 4 | W-34: the sentence appears only for trades with no plan (not "all running trades") | W-34 |
| 5 | Set-up R2-0: `FEED_MODE=bus` and `REDIS_URL` in the API's environment | R2-0 and this page, A1 |
| 6 | W-02/W-03: "Still loading..." is never printed for the plan watch within 12 s; the box line "Loading the rule check..." is the expected text; only Alerts prints "Still loading." | W-02, W-03, this page A5 |
| 7 | R2-FD2 step 2/3 (API address, not vite, for `GET /positions`); R2-FA step 4 (Exit on Positions disabled before FJ; dialog on the builder); SW-9 (Stops panel is inside Positions > Paper) | R2-FD, R2-FA, SW-9, this page A8, A9, A12 |

Other findings of TG's cloud walk the PC should know (all known or new defects, none a plan fault unless said): **D-TG-1** paper P&L paused with no session; **D-TG-2** leg-expiry Review line missing; **D-TG-3** raw JSON of the 409 twice on Positions with no session; **D-TG-4** the plan sheet saves Stop 9 % beside Stop (Rs) 500 with no "Stop and Stop (Rs) show different values." (W-14); **D-TG-5** the paused sentence eight times on Positions > Paper. **TC-3** (Notification settings): TG found no control named "notification" on Alerts: plan fault, the control is not named: the PC reads the Alerts page and writes the control's real name (cloud-first rule: only if TC-3 is in its sample). **TC-1** (charges tap): clicking "Charges paid" showed none of "Before charges / Estimated charges to close / After charges": the PC writes what it opens.

### C. Proof level of each check (from Lane TG's results, 28 Nov; levels: cloud test = a test file passed; cloud browser = walked in a browser on seeded data; PC = needs his machine or data; live market = Monday only)
| Check | Proof level and result |
|---|---|
| W-34 worker running, market closed | cloud browser PASS for planned trades; PC for his nine (plan or no plan) |
| W-34 worker stopped then started | cloud browser PASS (badge back in 3 s) |
| W-02 / W-03 plan watch slow | cloud browser PARTIAL (no error block; box line only); real link: PC |
| W-13 / W-17 / SW-8 Alerts slow | cloud browser PARTIAL (no error block; "Still loading." at 22 s on Alerts); real link: PC |
| W-33 / AF-03 / AF-04 / SW-1 to SW-9 (stored close, no session) | cloud browser PARTIAL (banner, indexes, closes PASS; paper P&L paused: D-TG-1) |
| W-26 case A | cloud browser PASS (all four legs named in one list; Multiplier) |
| W-26 case B | cloud browser: OWNER DECISION PENDING (recorded, not judged) |
| W-32 leg's own expiry control | cloud browser FAIL (D-TG-2; the server's reply is right) |
| W-01 Reset keeps typed levels | cloud browser PASS ("Nothing differed from the playbook, so nothing was put back.") |
| SW-6 Add to Paper, market closed | cloud browser PASS (Confirm grey, no tick box) |
| Exit with paused prices (FJ, ADR-330 (60)) | cloud browser PASS on `1ad973435` (contains `8d4355df2`; in the frozen commit) |
| W-09 plan stop in scenario mode | cloud: tool limit PARTIAL; live market (Monday T1-05) |
| R2-F1 R1 (builder, cut reply) | cloud browser PASS (no second exit; 1 POST) |
| R2-F1 R2 (Positions, cut reply) | cloud browser PASS (different sentence: "We could not confirm the order. Check Orderbook before trying again.") |
| R2-F1 R3 (Alerts, cut reply) | cannot in the cloud (no alert row with an exit) |
| R2-F3 R4 (cancelled stop) | cloud test PASS for the reply (`cancelled_stops`); page line not walked |
| R2-FJ N1 real position card | cloud browser PASS for the card; PARTIAL for the refusal (market-closed answers first) |
| W-06 / W-12 / AF-05 totals | cloud browser PASS for the pieces read (+457.93; "Includes 1 closed strategy."; "4 strategies left out") |
| W-14 plan sheet messages | cloud browser PARTIAL (D-TG-4: no "show different values" message) |
| W-16 completed trade read-only | cloud browser PASS (a "Plan watch" heading is seen on a closed trade) |
| W-18 Rename and Esc | cloud browser PASS |
| W-19 name on one line | not judged (could not measure) |
| W-25 Exit dialog market closed | cloud browser PASS (parts B, D, E: PC) |
| W-28 (3), (5, 6), (8) | cloud browser PASS |
| W-29 (55), TC-4, W-20 stop warnings | cloud browser PASS (W-20's exact sentence needs B-N1: not in the walk) |
| W-31 one batch per cycle | cloud browser PASS (3 requests in 45 s) |
| TC-1 charges tap | cloud browser PARTIAL |
| TC-2 SENSEX / far expiry | cloud browser PARTIAL |
| TC-3 Notification settings | plan fault, control not found |
| TC-5 Completed page | cloud browser PASS for the page; settlement: PC (needs an expiry day) |
| R2-FA step 2 Stops reference line | cloud browser PASS; "Saved: exit above ..." not captured |
| R2-FA step 4 | cloud browser: dialog PASS on the builder; on Positions disabled before FJ, enabled with FJ |
| R2-FC2 step 5 paused sentence once | cloud browser FAIL (D-TG-5) |
| R2-FD2 `GET /positions`, triggers route | cloud browser PASS (API address; vite for triggers) |
| R2-FD2 `GET /api/market/indices` | cloud browser PARTIAL (SENSEX unavailable in that run) |
| R2-FJ "No broker is connected, so no real positions are shown." | cloud browser PASS |
| W-04, W-21, D-1, D-2 pulls, W-22, T1-18 | PC (his data) |
| W-05, W-07, W-10, W-11, W-15, W-23, W-27, W-29 (54) closed/real Plan button, W-30, W-35, T1-14 to T4-04, R2-F2 (index exit, silent feed), R2-FA to R2-FR test-file steps | NOT walked by TG (budget): cloud test proof only where a lane's result file names one; "TG pending" otherwise (not moved to the PC) |
| Everything needing the live market (T1-xx, AF-07, M-1, M-2) | live market (Monday) |

## Version 6: CLOUD FIRST: what the PC runs in round 2, and what is proven in the cloud

**The owner's question (28 Nov): "if the plan can be walked in a browser in the cloud, why use the PC?"** So every check of this plan is now in one of two lists, with the reason in one phrase:
- **CLOUD** = logic, wording, dialogs, counts, states, refusals, closed-market behaviour: provable with seeded or scenario data in a cloud browser or by a test. Lane TG walks these (`test/r2-plan-walk-1128`, pushed 15:19 IST: it had walked item 1 only); Lanes TA to TF proved many by test; each row names the lane and the proof.
- **PC ONLY** = needs one of: (1) the real database change on his data (0060, 0061); (2) his real rows (the nine running trades, the stored closes, strategies 209, 201, 207, 194, trade 173, his own seed); (3) the real link speed to his database; (4) his machine's memory; (5) a broker session; (6) the live feed.

**The PC's round 2 list (Saturday 21:00) = the set-up (57 min) + the PC ONLY checks (6 to run now: W-04, W-21, TC-5, D-1, D-2, R2-FD; W-22 and T1-18 PASSED in round 1 and are not re-run; AF-09 and AX-01 are Monday) + the cross-check sample of 10 cloud-proven checks chosen from round 1's failures (W-34, W-13, W-17, W-02, W-33, W-25, W-32, SW-6 with W-35, W-07 row (64) the real position row, T3-09 one alert answered). Everything else is NOT run on the PC** (rule 17 of section 0): it stays in this file as the CLOUD list, with its lane and proof.

**Expected PC time for the shorter list: about 254 minutes (4.2 hours)**: set-up 57 + PC ONLY 79 + sample 98 + buffer 20 (234 minutes without the buffer; each sample check that fails adds about 10 minutes for the re-run and the write-up).

**STATUS line of this version: "version 6: PC ONLY 10 checks (6 to run now), sample 10, cloud 81".**

### What Lane TG's walk (cloud, item 1) already says the PC should expect
- **W-34:** PASS for trades that have a plan; **trades with no plan still read "Not being watched: the worker does not list this trade." with "No plan: nothing is watched for this strategy" beside it** (the round 1 sentence). If the PC's nine trades have no plan, round 1's reading was this, not a worker fault: **the PC writes, for each of its nine trades, whether it has a plan.**
- **W-32: FAIL in the cloud (D-TG-2):** the Review dialog does not show the stop sentence ("The stop on <leg> will be removed; set a new one after the move.") although the server returns it when asked by hand. So W-32 in the sample is not a re-run of a pass: write "known D-TG-2" if it reads the same.
- **W-33:** with no Zerodha session the closes show on every screen (D-1 fixed) but the paper P&L stays "paused" (D-TG-1); the PC has no session, so expect paused P&L (known D-TG-1), not a seed fault. The API needs `FEED_MODE=bus` and `REDIS_URL` in its environment (set-up item S7 below).
- **W-02, W-13, W-17:** TG saw no error block with a 9 to 12 s delay in the cloud, but "Still loading..." does not show for the plan watch. **The real 6 s / 24 s link is proven nowhere in the cloud: the PC's sample re-run is the only evidence of it.** (These three are listed CLOUD because the coordinator named them in the sample; the cloud proves the logic only.)
- **W-26 case B:** OWNER DECISION PENDING (recorded, not judged). Eleven CLOUD checks have no named cloud proof yet (W-10, W-14, W-15 same-side variant, W-23 tool alone, W-30, W-31, T2-19, T2-21 (409), T3-06, T3-17, TC-2 SENSEX/far expiry): Lane TG items 2 to 4 are not started; they stay CLOUD (TG pending) and are NOT moved to the PC.

Two honest notes before the tables:
1. **W-02, W-13, W-17 (and in part W-03, W-31, AX-14, SW-8) are the "page gives up before the server answers" class.** Rule (3) would make the real link timing PC ONLY. They are listed CLOUD because the coordinator named them in the sample: the cloud can prove the logic (a delayed route, W-23's tool, plus the query-cost tests), but NO cloud result for the real 6 s / 24 s link is recorded. The sample re-runs them on the PC for exactly that reason. If the sample passes with a real number written beside the server's own time, the class is closed.
2. **W-33 and W-34 are proven in the cloud on synthetic closes and a harness worker** (Lane TC: 15:29:58 seed, idle socket, no Zerodha call; Lane TG: same closes, no session, worker as its own process). The PC's own seed of the real snapshot is rule (2). They are in the sample.
3. **Lane TG's findings change what the sample must look for** (quoted from RESULTS-lane-tg.md): (a) W-34 "PASS for planned trades (#1, #2)"; trades with no plan still read "Not being watched: the worker does not list this trade." with "No plan: nothing is watched for this strategy" beside it, "the exact sentence round 1 called a defect. If the PC's 9 trades were unplanned, round 1's reading was this, not a worker fault": the PC must write whether each of the 9 has a plan. (b) W-33 PARTIAL "banner and closes show on all (D-1 fixed); every running row's paper P&L is still 'paused' (D-TG-1)" with no session; the PC has no session, so expect the same. (c) W-32 FAIL (D-TG-2): the Review dialog does not show "The stop on <leg> will be removed; set a new one after the move." although the server returns it when asked by hand; a cloud FAIL means W-32 on the PC is expected to fail until a fix, not a cross-check of a pass. (d) Set-up: the API needs `FEED_MODE=bus` and `REDIS_URL`, else every trade reads "no worker has reported" (add to S7).

---

### (a) PC ONLY

| id | title (short) | why (one phrase) | est. PC min |
|---|---|---|---|
| W-04 | Adjustment history rows, strategies 209 and 201 | (2) his real rows 209 and 201: does the server hold the rows | 8 |
| W-21 | Lane M read-only SQL (2028 date, contracts) | (2) his real rows: SQL on his database (`paper_orders`, `catalogue_contracts`) | 8 |
| W-22 | Lane J read-only SQL, stop alerts of #207 | (2) his real rows: `paper_alerts`, `strategy_alert_style` by strategy id (PASS in round 1) | 0 (PASS in round 1: not re-run) |
| TC-5 | A settled strategy (trade 173) | (2) his real settled SENSEX trade 173; TC could not seed a settlement | 8 |
| T1-18 | Settlement rows of trade 173 and the stored settlement text | (2) his real row 173 (PASS in round 1) | 0 (PASS in round 1: not re-run) |
| D-1 | Data pull: 27 Nov stop case, strategy 207 (#876) | (2) his real rows of strategy 207, plan body, orders, suggestions, worker log | 20 |
| D-2 | Data pull: year 2028 on a 1 Dec contract, B-N1 #194 | (2) his real rows of strategy 194 and the catalogue (14,474 rows) | 15 |
| R2-FD | Backend: totals, request key, reads, durable key | (1) migration 0061 on his database, (2) his seed read (`GET /api/market/indices` 27 Nov close), (3) role connection count (limit 10, shared) | 20 |
| AF-09 | Items that need an expiry day (D-64, D-59, D-12) | (6) live feed and an expiry day: Monday or Tuesday, not in the weekend run | 0 (Monday) |
| AX-01 | Index tick silent for 60 seconds | (6) live feed: Monday (the silent-feed logic itself is R2-F2, CLOUD) | 0 (Monday) |

n = 10 PC ONLY (8 in the weekend run, 2 Monday-only with 0 weekend minutes). PC ONLY subtotal: **79 min** (W-22 and T1-18 are PC ONLY by the rule but PASSED in round 1, so they are not re-run: 12 minutes less than first counted).

### (b) Cross-check sample (CLOUD-proven checks to re-run on the PC), m = 10

| id | why chosen | min |
|---|---|---|
| W-34 | Round 1 FAIL: every running trade read "Not being watched: the worker does not list this trade." with the worker running; cloud proof is a test worker, the PC has the real worker and 9 real trades. Read half + stop/start half | 15 |
| W-13 | Round 1 FAIL: "Closed by system" on Alerts > History; the page gave up before the 6.5 s answer. One tester, write the API log time beside the page | 8 |
| W-17 | Round 1 FAIL: Alerts Active slowed 5 s showed the server-error block after about 6 s (needs W-23's delay tool + API restart) | 12 |
| W-02 | Round 1 FAIL: plan watch for 9 trades, "not available" for 3 min, 24 s batch read; one tester, 3-minute watch, count requests, write the log's ms | 12 |
| W-33 | The stored close on the after-close screens: round 1 saw no close on any of nine screens (known D-1); cloud proof used synthetic closes; the PC has its own 17-row seed. Restart, nine screens | 15 |
| W-25 | Exit with the market closed per ADR-330 (60): dialogs A to E, parts B and D (feed stopped, API stopped) never run in round 1 | 12 |
| W-32 | A moved leg with a stop: the leg's own expiry chip (round 1 used the wrong control): "The stop on <leg> will be removed; set a new one after the move." | 8 |
| SW-6 (with W-35) | Add to Paper after the close: Confirm pressed once, expect "The market is closed. Orders can be placed once it opens.", order rows before = after (round 1: 965 / 965) | 6 |
| W-07 row (64) (also W-29 (54) step 2) | A real position row: "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."; no Exit, no Stops; real Plan button. Round 1: not walked | 5 |
| T3-09 | One alert answered: a dismissed opportunity read "You dismissed this" and its reason as two words; round 1 row had no reason chosen (the PC has the real dismissed row of 27 Nov 13:32) | 5 |

Sample subtotal: **98 min**. Every sample id is also in table (c) (marked S).

### (c) CLOUD (k = 81; S = in the sample)

Proof column: "TC" = Lane TC walk of 5fc6b102 (RESULTS-lane-tc.md, synthetic closes); "TD" = Lane TD walk (RESULTS-lane-td.md); "TG" = Lane TG walk, not pushed at 10:12; test names are the files the lanes name. "no cloud proof recorded; TG pending" = nothing in the evidence proves it yet.

| id | title | why (one phrase) | lane and proof |
|---|---|---|---|
| W-33 S | Nine screens after a restart, last close stored | seeded closes: a seeded browser proves banner and figures | TC I-26 PASS SW-1,3,4,5,6,7,9, PARTIAL SW-2, SW-8; tests_app/test_closed_label_route.py, test_close_freeze_routes.py; FD2 D-1/D-2 (5 and 59 tests); frontend/tests/market-closed-screens.test.js; PC round 1 was known D-1 ; **TG: "PARTIAL: the banner and closes show on all (D-1 fixed); every running row's paper P&L is still 'paused' (D-TG-1)"; Home "4 strategies left out"; Positions Real prints the raw 409 JSON twice (D-TG-3)** |
| W-01 | Plan save, change, Reset, read back in three places | logic/wording: Reset keeps typed levels by design (plan fault in round 1); a seeded draft proves it | FC3 plan acceptance (38 tests, 0060 guard on a fresh DB); no browser walk recorded; TG pending ; **TG: "PASS" (Reset keeps typed levels; reads "Nothing differed from the playbook, so nothing was put back.")** |
| W-02 S | Plan watch load, one request at a time | logic proved with a delayed route and query-count tests; the real 24 s link is NOT proven in cloud (see note 1) | tests_app/test_route_latency_budget.py, test_slow_price_source_live_day.py, test_plan_read_cost_fd4.py (FD4); W-23 delay in a cloud browser: TG pending ; **TG: "PARTIAL: no error block, but 'Still loading...' never shown for plan watch" (server 218 ms / 183 ms; rows at 10 s and 14 s with 9 s and 12 s delays); plan fault 6** |
| W-03 | Plan watch box, weekend wording | wording: the box texts are seeded-state texts | TC SW-4 ("Not being watched: no worker has reported in the last 2 minutes."); FC3 PlanWatch; PC round 1 builder part PASS; link half = W-02 ; **TG: "PARTIAL" (same row as W-02)** |
| W-05 | Order limits with the market closed | wording/logic: refusal sentences and the 100-lot limit are seeded | TE I-37 (101 refused at 100); TC D-4 (MARKET_DATA_102 refusal); frontend/tests/add-to-paper-r2-fb.test.js; step 0 freeze SQL is optional |
| W-06 | One P&L number in the places | counts/logic on seeded closed and unpriced trades | TC AF-04/AF-05 shapes hold (rows add to the Home total); FD B1 booked result; PC round 1 matched on Home and Positions |
| W-07 | Owner decisions (46) to (64): each walked once | wording/logic per row; (56) and (63) need a close, seeded | PC round 1 walked (52),(54),(55),(60),(62) as expected; TC texts; row (64) is in the sample |
| W-09 | Plan-stop alert in scenario mode | scenario data by design; PC round 1 said "cloud only" | Lane Q3 worker-chain test (test/worker-chain-1127, 10 passed on PostgreSQL), FE: 214 DB tests incl. the Q3 chain, test_worker_j3 |
| W-10 | Compare approaches: Cancel and Confirm | state logic ("Open" then "Acted on"); the opportunity row is seedable | no cloud proof recorded; TG pending (TB I-74 covers staged legs only) |
| W-11 | Full-exit approach stages the held legs | state logic on a seeded opportunity | TB I-74 PASS (4; held staged legs come back); TG pending |
| W-12 | Home closed-strategies line | wording; PC round 1 PASS | TC Home "Includes 1 closed strategy."; PC round 1 PASS |
| W-13 S | "Closed by system" in Alerts History | logic proved with a delayed route; the real 6.5 s link is NOT proven in cloud (note 1) | TB I-60 (frontend/tests/paper-alerts.r2-1128.test.js: failed half keeps its heading, other half keeps rows); FC2 History loading line; TG pending ; **TG: "PARTIAL: no error block, 'Still loading' seen only at 22 s" (12 s delay, server 15 ms)** |
| W-14 | Time-exit wording on the plan sheet | wording; Target boxes are linked (plan fault) | no cloud proof recorded; TG pending |
| W-15 | Two legs on one contract: Save-draft sentences | wording (order is by leg number: plan fault) | PC round 1 saw the sentence; same-side variant: TG pending |
| W-16 | A completed trade opens read-only | wording/state; PC round 1 PASS | PC round 1 PASS; FC3 (settled trade shows no "Checked at Time not available") |
| W-17 S | Alerts Active on a slow connection | logic proved with the delay tool; the real link is NOT proven in cloud (note 1) | FC2 / TD I-86 (frontend/tests d38-timeouts-pages, 3 passed); W-23 tool; TG pending ; **TG: "PARTIAL" (same row as W-13)** |
| W-18 | Typing at once into Rename and Save | wording/logic; PC round 1 PASS | TD I-78 PASS; vitest rename-paper-d65 (6 passed) |
| W-19 | Net Positions name on one line at 1366 px | layout: a cloud browser sets 1366 (the PC's browser could not) | TC I-75 PASS at 1366x768, `NIFTY 24000 PE 2026-12-08` on one line in all 4 rows |
| W-20 | Max-loss line when a stop is typed | wording on a seeded trade (#209 shows it) | TF tests_app/test_leg_stop_lines_tf_1128.py (9; three lines, each at most 80 characters); TA I-63 (15); PC round 1 O-R-07 saw the sentence |
| W-23 | Route-delay tool | a tool: a seeded browser shows the delay and that other routes are unchanged | PC round 1 measured 7.6 s with the delay, health 0.5 s; cloud use inside W-17: TG pending |
| W-24 | What is on this plan and what is Monday's | reading the plan; PC round 1 PASS | PC round 1 PASS |
| W-25 S | Exit dialog with the market closed (ADR-330 (60), (49)) | wording/refusal/closed-market behaviour; stopping the feed or API is process control the cloud has too | TC SW-3 Exit dialog ("The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.", Confirm disabled); TD I-20; frontend/tests/exit-closed-entry-points-r2-fa.test.js, exit-market-reask-r2-fa2.test.js; tests_app/test_exit_market_adr330_60.py; PC round 1 parts A, B, C seen |
| W-26 | Exit all with a staged change | state logic on a seeded two-leg trade; case B is an owner decision | PC round 1 re-run (raise lots: 4 legs listed, grey Confirm, nothing staged after Cancel); FA2 paper-unchecked-confirm-r2-fa2; TG pending ; **TG: case A "PASS, one plan fault (no per-leg lots control)"; case B "OWNER DECISION PENDING (recorded, not judged)"** |
| W-28 | Alert and Stops screens | wording/state; items needing a close are seedable | TC SW-8 and SW-9 match; frontend/tests/paper-alerts.r2-1128.test.js; PC round 1 saw reason lines |
| W-29 | Plan door, Stops lines, closed trade | seeded fixtures (real row, SENSEX trade, bought call were absent on the PC); settled half (57) is covered by PC ONLY TC-5 and T1-18 | TC SW-3/SW-6/SW-9; FA stops-index-closed-r2-fa.test.js; PC round 1 saw Plan buttons and stop lines; real-row step in the sample (W-07 (64)) |
| W-30 | Stop percent weekly and monthly; Reset | seeded monthly Iron Condor and "R2 test" playbook (cannot be made on the PC with the market closed) | Lane R3 `3260e094` and R2 `1d0f56e7` are in the commit; no cloud walk recorded; TG pending |
| W-31 | Plan watch: one batch request per cycle | request count in a cloud browser | PC round 1 saw one batch URL per cycle (PASS part); completion = W-02; TG pending |
| W-32 S | Change expiry of ONE leg (leg's own chip) | wording/logic: the 201 reply names the cancelled stop | FD2 `cancelled_stops` (4 tests); FA2 frontend/tests/paper-cancelled-stops-r2-fa2.test.js (5); FB2 page half; PC round 1 void (wrong control) ; **TG: "FAIL (D-TG-2)": the Review dialog lacks the stop sentence; no `armed-exits` or `exit-risk` request from the page** |
| W-34 S | "Monitoring paused" badge and the worker's reason | worker logic with a test worker; the real worker and 9 real trades are in the sample | FE2 tests_app/test_monitor_reports_fe2_1128.py, test_pause_restart_fe2_1128.py, test_worker_expiry_fe2_1128.py; FE test_index_exit_watch_fe_1128.py; TC SW-4 text; PC round 1 worker-stop half seen ; **TG: "PASS for planned trades (#1, #2)" and "PASS" for worker stopped then started (badge within 30 s); unplanned trades keep the round 1 sentence; set-up needs FEED_MODE=bus** |
| W-35 S | Add to Paper, "prices are not live" ticked | wording/logic: after the close there is no tick box; the tick half needs an open market (Monday) | FA2 frontend/tests/paper-entry-closed-r2-fa2.test.js (3), paper-not-live-tick-r2-fa2.test.js (2); FR entry_facts; TC D-4; PC round 1 saw the closed sentence |
| TC-1 | Charges tap on Positions > Paper | wording; PC round 1 PASS | PC round 1 PASS; TC saw the totals strip |
| TC-2 | SENSEX and far expiry on the Option Chain | seeded SENSEX contracts and closes; round 1 was known D-1 | TC SW-7 (chain with closes, "IV and Greeks: estimated from spot..."); FD2 D-1; the SENSEX/far-expiry step: TG pending |
| TC-3 | Notification settings, "side closed" alert | wording; PC round 1 PASS | PC round 1 PASS |
| TC-4 | Stop warning text on the Stops panel | wording; PC round 1 PASS | PC round 1 PASS; TF I-51; TA I-63 |
| T1-20 | Feed stopped: figures pause, Add to Paper | wording/state; the feed stop is process control | TC (no tick box, paused wording); TD I-20; FA2 paper-not-live-tick-r2-fa2; FC2 O-1 (paused line carries its time) |
| T1-21 | API stopped for seconds: Exit grey, dialog closes | wording/state | TD I-20 PASS (i20_outage.js: grey Exit, reason line, dialog, empty builder) |
| T1-14 | Builder money figures | logic/figures on a seeded trade; Monday for live | TD I-41 PARTIAL (table total, D-11 tiles, D-14 PASS; re-buy BLOCKED: needs a closed contract seeded) |
| T1-16 | Paper total line and the left-out line | counts: seed exactly one unpriced trade (the PC has 9, so it cannot run there) | TC Home "1 strategy left out: its price is not live." and "Includes 1 closed strategy." |
| T2-06 | Builder Greeks tab | seeded trade with a priced index | TD I-79 PASS (Greeks tab); PC round 1 was known D-1 |
| T2-09 | Bulk delete, result line, Undo | counts/logic; PC round 1 PASS | tests_app/test_bulk_delete_undo_tf_1128.py (6); TB I-80 (29 s / 30 s hold) |
| T2-17 | Lists: status word, figures of a closed row | counts across screens on seeded closed trades | TC SW-5 (closed row, Net after charges); PC round 1 figures equal on two screens (plan fault: address) |
| T2-19 | Reset to playbook markers | logic on a seeded draft with a plan from a playbook | FC3 plan acceptance (38 tests); TG pending |
| T2-21 | Strategy Chart on a running paper trade | state/refusal (no open legs, switch off = 409) on seeded trades | FK frontend/tests/payoff-chart-teardown.test.js (6); chart 409: TG pending |
| T3-01 | Leave question and reload line | wording; strikes need the instrument list (seedable) | FB I-30 (contract-list line, 5 tests); FC2 ADR-330 (61); PC round 1 saw the line vanish after Save |
| T3-06 | Phone-width drawer | layout: a cloud browser sets the width (PC could not) | no cloud proof recorded; TG pending |
| T3-09 S | Rename Esc; dismissed outcome in two words | wording on a seeded dismissed row; the PC's real dismissed row is the sample | TD I-78 PASS; vitest rename-paper-d65 (6) |
| T3-10 | API stopped: every list shows its failure and Retry | wording/state | TD I-86 PARTIAL (message on 10, Retry on 2: D-TD-2); FC2 ListLoadFailed.vue; d38-timeouts-pages (3) |
| T3-12 | One date style, 24-hour clock | wording | TC walk (one date style); PC round 1 saw it |
| T3-13 | Wording, labels, "View" button | wording; round 1 lacked a user playbook (seedable) | TD I-88 (View, D-52, D-58 zero-price PASS; D-54 Delete BLOCKED: no playbook) |
| T3-15 | Delete and Undo leave history entries | counts | TF test_bulk_delete_undo_tf_1128.py (6); PC round 1 bulk case passes |
| T3-17 | Lane D screen re-tests | wording/counts on seeded closed legs | FC2 contract-list line; no cloud proof recorded for the no-stop-closed trade; TG pending |
| T4-01 | Number tables, columns separate | layout | TC I-91 (Orderbook, Live card, closed Net Positions PASS; Positions closed row FAIL D-8, fixed in FC2) |
| T4-03 | Strategy name width | layout with 20+ character names (seedable) | TC I-92 PASS (20-character name not cut at 1280x800) |
| T4-04 | Stops form and list side by side | layout on a seeded trade (saving a stop must not touch his running trades) | TD I-93 PASS |
| AF-03 | Mixed trade's banner time (data, not PASS/FAIL) | seeded mixed trade | TC data point: one 15:58:00 row makes the banner read 15:58:00 ; **TG: "no mixed-time case (all legs priced by one close)"** |
| AF-04 | Home Total P&L with one settled or unpriced trade | arithmetic on seeded rows | TC AF-04 shape holds (+3,027.52 + 1,381.23 - 7,600.51 = -3,191.76; closed +457.93; total -2,733.83) ; **TG: "PARTIAL": Home +457.93 = the closed trade only, four running excluded (D-TG-1)** |
| AF-05 | Home against the My Strategies rows | arithmetic, frozen prices; PC round 1 PASS | PC round 1 PASS; TC ; **TG: "same" (trivial sum, D-TG-1)** |
| AF-06 | No "No price for:" line above a priced table | wording | TC (holds); PC round 1 known D-1 |
| AX-14 | Plan watch rows, market closed | wording: state word plus server reason | FC3 PlanWatch; PC round 1 saw "Not checked" / "Wait for fresh prices."; link half = W-02 |
| SW-0 | Restart first, rule, must-not-show list | restart plus console errors on a seeded app | PC round 1 PASS (no console errors); TC D-2 (red 409 with no session; fixed in FD2, 59 tests) |
| SW-1 | Home | wording/figures | TC matches ; **TG: "PARTIAL" (D-TG-1: closes show, P&L paused)** |
| SW-2 | Positions, Real part | no session: no invented figure (the weekend case) | TC (no session: dash plus connect sentence; plan line out of date); PC round 1 PASS ; **TG: "PARTIAL" (raw JSON of the 409, D-TG-3)** |
| SW-3 | Positions, Paper part | seeded closes, banner | TC matches (totals strip, Exit dialog) ; **TG: "PARTIAL" (D-TG-1)** |
| SW-4 | Live Strategies | one banner, honest paused state | TC I-116 PASS (one banner 15:29:58) ; **TG: "PARTIAL" (D-TG-1)** |
| SW-5 | My Strategies and Completed | dash with reason, never 0 | TC matches (no Completed tab on My Strategies: plan fault) ; **TG: "PARTIAL" (D-TG-1; Completed is its own page)** |
| SW-6 S | Builder of a running paper trade | seeded; entry labelled; refusal | TC; PC round 1 PASS (Confirm once: 409, 965 orders before and after) ; **TG: "PASS (Confirm is greyed)"; no tick box** |
| SW-7 | Option Chain | closed banner, last prices | TC (chain with closes); TC-2 covers the rest ; **TG: "PARTIAL" (only 15 closes seeded; strikes read "not available")** |
| SW-8 | Alerts (Active, History, Records) | wording/empty lines; the PC error was the link | TC matches; TB I-60; FC2 History loading line; link half = W-13 ; **TG: "PARTIAL" (slow-answer part as W-13); plan fault 2: Records is the History block, not a page** |
| SW-9 | Stops panel | wording; PC round 1 step not read | TC (NIFTY last ... as of 15:29:58); FA I-29 (frontend/tests/stops-index-closed-r2-fa.test.js) ; **TG: "PARTIAL" (Stops panel line "NIFTY last 24187.35 as of 15:29:58" seen); plan fault 7** |
| AF-07 | Zerodha disconnected: Real total says so | screen logic with a fake broker reply (no real session needed) | TC I-113 PASS after reload, FAIL on an open page (D-13, fixed in FC2) |
| R2-F1 | After an unknown exit, no second exit | logic by tests; real completion is Monday | FB2 frontend/tests/save-bar-add-lock-r2-fb2.test.js (11); FA2 exit-lock-window-r2-fa2.test.js; FD2 request key (paper 10, real 2); FJ parked critical item (R1) |
| R2-F2 | Index exit with a silent feed | scenario data: DB tests with a silent tick | FE tests_app/test_index_exit_watch_fe_1128.py, test_leg_exit_watch_fe_1128.py, test_review_fixes_fe_1128.py (214 DB passed) |
| R2-F3 | Moved-leg stop: the user is told | wording/logic | as W-32 (FD2 cancelled_stops; FA2 paper-cancelled-stops-r2-fa2) |
| R2-FA | Exit dialog and Stops panel (FA, FA2) | wording/logic | FA/FA2 vitest: exit-dialog-age-r2-fa, exit-dialog-placing-r2-fa, stops-index-closed-r2-fa, stop-row-date-r2-fa, exit-market-recheck-r2-fa, exit-closed-entry-points-r2-fa, paper-* r2-fa2 files (full vitest 3831 of 3831); not in the build (FJ brings it) |
| R2-FB | Builder page, finding F1 (FB, FB2) | wording/logic | frontend/tests/contract-list-line-r2-fb, save-bar-add-lock-r2-fb2, leg-show-at-once-r2-fb2, builder-ux-r2-fb2, add-to-paper-r2-fb |
| R2-FC | Small screens, pages, plan screens (FC, FC2, FC3) | wording/counts | tests_app/test_d36_adjustment_counts.py; FC/FC2/FC3 vitest; FC2 not in the build |
| R2-FE | Worker exits and monitoring sentences (FE, FE2, FE3) | scenario worker logic | FE2 tests_app/test_monitor_reports_fe2_1128, test_worker_expiry_fe2_1128, test_worker_saved_plan_fe2_1128, test_pause_restart_fe2_1128, test_unknown_kind_style_fe2_1128, test_checked_body_fe2_1128, test_kind_cache_fe2_1128, test_dropped_and_skew_fe2_1128; tests/adjustment/test_stop_lines_fe2_1128.py |
| R2-FJ | Frontend joins: locks, one key on every page | state logic; two tabs in a cloud browser | FJ vitest (unknown locks); parked critical `decideLock` item; not in the build |
| R2-FK | Chart teardown | no PC steps; a test proves it | FK frontend/tests/payoff-chart-teardown.test.js (6, red on base then green), charges-dialog-drafts-d13-d14 x20 |
| R2-FR | Readers: nearest expiry, unknown kind, heartbeat | scenario data, DB tests | tests_app/test_screen_expiry_fr_1128, test_reader_kinds_fr_1128, test_index_one_rule, test_worker_heartbeat, test_settings_in_force |
| R2-TT | Tests TA, TF, TE, TB, TW: what they proved | no PC steps | TA 15 PASS, TF items 1 to 3 PASS, TE 42 PASS, TB 10 items, TW (TD) 11 items |

Not checks (no row): W-08 ("not on this plan"), W-27 (merged into W-25), the "Open at the end of round 2 build" table.

### (d) Set-up items (round 2; the PC's own work, in order)

| item | what | est. min |
|---|---|---|
| S0 | Look at the database link; count `ofo_app` connections (limit 10) | 2 |
| S1 | Back up the production database (pg_dump over SSH), copy, compare sizes, `pg_restore --list`; VPS disk about 90 percent full | 10 |
| S2 | Stop API, worker supervisor, frontend; fetch and check out the round 2 commit; `git rev-parse HEAD` (R2-1) | 4 |
| S3 | Migrations **0060 then 0061 in one step** after the owner's typed "yes" and the verified backup; `alembic current/heads`; the two migration test files through `db_run_fresh.py` (R2-2) | 14 |
| S4 | Read-only checks after the migration: allow-list assert returns, `strategy_history` invalid count 0 | 3 |
| S5 | Seed: none new; `select count(*) from last_close` reads 17 (R2-4, R2-5) | 1 |
| S6 | Frontend: `npm ci` and `npm run build` if `frontend/` changed (R2-0) | 6 |
| S7 | Restart order API, worker, feed, then the screen server (vite); API environment carries `FEED_MODE=bus` and `REDIS_URL` (Lane TG set-up note 5); free memory above 3 GB (rule 15); Redis up (R2-3) | 9 |
| S8 | Route check through the vite address: `/api/real/strategies/209/triggers`, `/api/plan-watch?strategy_ids=209`, `/api/monitoring-state`, `/api/market/exit-state` all 200 (R2-0b) | 4 |
| S9 | Confirm the build: commit, health reply `healthy / connected`, contract list named (step 8) | 2 |
| S10 | Sanity: nine running paper trades on Positions > Paper, Alerts count equals the bell, no red box on Home (step 9) | 2 |
| | **Set-up subtotal** | **57** |

(Round 1's own set-up took from the 09:51 tunnel fault to the 10:20 comment, about 30 min, with the seed; round 2 has no seed but adds 0060/0061 and the route check.)

### (e) Totals

| quantity | value |
|---|---|
| checks classified (sections 4 to 9, headings) | 91 |
| **n** PC ONLY | **10** (8 weekend, 2 Monday-only at 0 min) |
| **m** cross-check sample (all inside the CLOUD list, re-run on the PC) | **10** |
| **k** CLOUD | **81** (includes the 10 sample checks; n + k = 91) |
| Lane TG verdicts available | 22 rows of table (c) (item 1 only; items 2 to 4 not started): PASS 3 (W-01, SW-6, W-34 planned), FAIL 1 (W-32), PARTIAL 17, OWNER DECISION PENDING 1 (W-26 case B). Lane TG pushed 09:49Z, not pushed at 10:12 container time, seen at 10:17 |
| CLOUD checks with no named cloud proof yet | 11: W-10, W-14, W-15 (same-side variant), W-23 (tool alone), W-30, W-31, T2-19, T2-21 (409), T3-06, T3-17, TC-2 (SENSEX/far-expiry step); plus the real-link timing of W-02, W-13, W-17 (not provable in cloud) |

Expected PC time:

| block | min |
|---|---|
| Set-up | 57 |
| PC ONLY | 79 |
| Sample | 98 |
| Buffer: free-memory check before each block, tabs closed, results written (rules 14 to 16) | 20 |
| **Total** | **254 min = about 4.2 hours** |

Without the buffer: 234 min (3.9 h). If the sample fails any check, add its re-run (about 10 min each) and the "sentence seen, expected, known or new" write-up.

## Plan version 4 for round 2: what changed since round 1

Round 1 (PC, commit `5fc6b102`, 28 Nov, PR #722) closed at 13:58 IST with **PASS 15, FAIL 8, PARTIAL 41, BLOCKED 11 of 75 checks** (the 12:20 detail, 55 checks so far, had 11 PASS, 7 FAIL, 26 PARTIAL, 11 BLOCKED; SW-6 moved from FAIL to PASS at 13:58: draft #220, feed stopped, "Held at my broker" unticked, Confirm pressed once: the dialog showed "The market is closed. Orders can be placed once it opens.", the request `POST /paper/strategies/220/orders` answered 409, paper order rows 965 before and after).. The coordinator's reading: **16 of the 33 FAIL or PARTIAL rows were faults of the plan or the set-up, not of the product.** This version fixes the plan; the rows are in section 1A. The ten changes the coordinator asked for:

1. **Before the first row of round 2 (section 2, "Round 2 additions"):** restart the **frontend server (vite) and the API** on the round 2 commit, write the commit in the results, and confirm that **each route new since `5fc6b102` answers through the frontend's own address** (round 1's route fault: vite reads the API route list once at start, so `/api/plan-watch`, `/api/monitoring-state` and `/api/market/exit-state` lost their `/api` prefix and answered 404 until it was restarted at 11:37).
2. **W-26:** the raise-lots step is mandatory, every step numbered; the expected text is given for the case with a staged change and for the case with none; the case with none is **OPEN: "owner decision pending"**, neither pass nor fail.
3. **W-32:** the control is **the leg's own expiry chip** in the leg row, not the "Change expiry" select (which moves all legs by design).
4. **W-01:** Reset keeps the typed levels by design (ADR-330 (9), (32)): expect the **"Put back to the playbook's values: ..." list or the "Nothing differed from the playbook, so nothing was put back." line**, and write which.
5. **W-04:** use strategies **209 and 201**, never 155 (155 does not exist on the PC).
6. **TC-5 and T2-17:** the address is **`/strategies/completed-strategies`** (`/strategies/completed` is "Page not found").
7. **T1-16:** needs exactly one unpriced trade (the PC has 9): marked **Monday**.
8. **W-02, W-03, W-13:** **one tester only** (the PC's reading: the 24-second plan watch may have been inflated by a second tester creating drafts), and **write the server's own answer time (from the API log request line) beside what the page showed**.
9. **W-34:** round 1's result (every running trade "Not being watched: the worker does not list this trade" with the market closed) is a real defect being fixed in the worker; in round 2 expect the market-closed reason instead, and re-read it on Monday with the market open.
10. **Every row** says what to write down on a FAIL or PARTIAL: **the sentence seen, the sentence expected, and known or new** (the PC needed a second request for that on 28 Nov). Rule 14 of section 0, and a line in every check.

**The round 2 build is frozen (28 Nov 17:15 IST): `integration/weekend-r2-1128` at `829ff65f26716f1efbcbac98ea3ba6aefdc350d9`.** (Earlier versions named `79388551` at 12:30 IST; that is out of date.) Section 9 lists which lanes are in that commit and which are not. **Migration 0060 is not safe for the old code** (section 2, "Round 2 additions", and section 9); 0061 is in the commit.

### Round 1 results to expect as FIXED in round 2 (the coordinator's list, 28 Nov afternoon)
- **The stored close shows with no broker session** (W-33; round 1's known D-1: "no stored close reaches any screen"): in round 2 the nine screens must show the stored close.
- **W-34:** the market-closed reason instead of "Not being watched: the worker does not list this trade."
- **The page no longer gives up before the server answers:** W-02, W-03, W-13, W-17 and SW-8 (round 1: "The plan watch is not available right now.", "The page could not get an answer from the server." with the server answering in about 6 s).
- **Two database changes, 0060 then 0061, are applied in one step** ([OWNER APPROVAL] after the backup). **Round 1 code is NOT safe on the changed database:** migrate and restart on the new code in one sitting; a code rollback also needs `alembic downgrade 0059_last_close`.

### The seven set-up lessons of the round 1 close (PC, 13:58 IST) are in section 2, block "Lessons of the round 1 close".

### 1A. What round 1 found, and what round 2 changes

| Row (round 1 result) | Cause | Round 2 |
|---|---|---|
| W-26 FAIL | **plan/set-up fault:** written on the stale screen server (void), raise-lots step skipped | W-26 rewritten (steps numbered); case B owner decision |
| W-01 FAIL | **plan fault:** Reset keeps typed levels by design; #209's plan block prints no stop or target figure (O-R-09) | W-01 expectation corrected |
| W-02 FAIL | product (24 s for 9 trades; "the poll waited ... for the database gate"); may be inflated by load | one tester; server answer time written |
| W-03 PARTIAL | unclear (same cause as W-02; builder #209: "The page could not get an answer from the server.", "The expiry list could not be read. Try again in a moment.") | one tester; server answer time |
| W-13 FAIL | product: the page gives up on "Answered alerts" before the server answers (about 6 s) | one tester; server answer time written beside the page |
| W-32 FAIL | **plan fault:** used the "Change expiry" select | leg's own expiry chip |
| W-34 FAIL | product (a real worker defect) | market-closed reason expected; Monday re-read |
| W-04 PARTIAL | **plan fault:** strategy 155 does not exist | 209 and 201 |
| W-05, W-35, W-28, TC-2, W-07, T2-06, T3-01, T3-12, T3-17 | known D-1 (no stored Zerodha session: no stored close reaches the screens) | still expected with no session; write "known D-1" |
| W-06 PARTIAL | unclear: steps 2 to 5 not run (the two totals matched: "Includes 17 closed strategies." and "9 strategies left out: their prices are not live.") | run steps 2 to 5 |
| W-14 PARTIAL | plan fault (likely): the Target and Target (Rs) boxes are linked, so "show different values" cannot be reached by typing | correction line in W-14 |
| W-15 PARTIAL | plan fault: the sentence orders the two legs by leg number ("one Buy and one Sell"); the same-side variant was skipped (the side badge did not flip) | expectation corrected |
| W-20 PARTIAL | **plan fault:** B-N1 changed shape; the sentence exists on #209 | use #209 or #201 |
| W-21 PARTIAL | **plan fault:** the table `actionable_alerts` does not exist | item 4 corrected: the alert tables are `paper_alerts` and `strategy_alert_style`; select by strategy id (lesson 3) |
| W-29 PARTIAL | **plan fault:** fixtures absent (real row, SENSEX trade, bought call) | BLOCKED: fixture, name it |
| TC-5 PARTIAL | **plan fault:** wrong address | `/strategies/completed-strategies` |
| W-31 PARTIAL | **plan/set-up fault:** stale tabs polluted the count | close old tabs, restart vite, count once |
| W-25 PARTIAL | parts B, D, E not run (they need the feed or API stopped) | run them |
| T1-16 PARTIAL | **plan fault:** needs exactly one unpriced trade; the PC has 9 | Monday |
| T2-17 PARTIAL | **plan fault:** wrong address (Completed screen) | `/strategies/completed-strategies` |
| T3-09 PARTIAL | **plan fault:** the dismissed row had no reason chosen | dismiss one with a reason first |
| T3-13, T3-15, T4-01 PARTIAL | unclear: steps not run (no user playbook; single delete then Undo; Live card leg table) | run them |
| T4-03 PARTIAL | **plan fault:** the long-name fixtures C5 to C9 do not exist | rename five trades to 20+ characters first |
| W-30, W-33, W-09, W-10, W-11, W-17, W-19, T1-14, T2-19, T2-21, T4-04 BLOCKED | no monthly Iron Condor trade / "R2 test" playbook (cannot be created with the market closed); known D-1; needs owner approval; no alert with an opportunity row; throttle and window resize not possible in that browser; Monday only; no plan on a draft; saving a stop would change a running trade | BLOCKED stays unless the coordinator supplies the fixture |
| PASS (11): W-12, TC-1, W-16, W-18, TC-3, W-22, W-24, TC-4, EXTRA-2028 (the year reads 2026-12-01), T1-18, T2-09 | | not re-run |

**Round 1 set-up facts that matter for round 2 (PC, 10:20 IST):** the database tunnel was down at 09:51 and restarted hidden at 09:53; migration 0059 applied 09:59; the DB test file `test_migration_0059_last_close.py` showed 9 passed and 4 failed (a test defect: a time sent as text, error 22000 against the expected 23514: for Lane N); `db_run.py` ran an old test copy at revision 0030; **the seed refused 15 of 17 rows because the snapshot's `name` column holds the trading symbol; the PC fixed it with a renamed-key copy and "written 17" followed, a rerun "unchanged 17"** (set-up step 5b of this plan now says so); API log "paper settlement: no broker session" (known D-1). Data pulls: for strategy 207, 0 suggestion rows 13:14 to 13:36 and 4 later, all lapsed; the 2028 date: no stored expiry of 1 Dec 2028.

## What to read before 08:00 on Saturday (for the owner; written for round 1, kept)

Round 1 starts at 08:00 on the commit `5fc6b102`. Three things need your eyes first; the details are in the sections named at the end of each line.

### 1. The three open review findings (known; not a round 1 failure)
Lane Z's independent Opus review of the stop and exit paths says REVISE. The three findings are open in the round 1 build and are fixed (or being fixed) in round 2:
- **F1** After an exit whose outcome is unknown, the page can unlock Exit after 5 seconds although the server may still commit the first exit, so a second partial exit can double-exit (2 of 4 lots twice = 4 lots). Round 2 fix: Lane FB `fix/r2-builder-1128` (the unlock now waits 120 seconds); the server-side request key is Lane FD's, not done. Section 7, R2-F1.
- **F2** When the index price feed is silent, an index exit may never fire while the trade still reads "watched" (the 23 Nov case: NIFTY ticks stopped at 15:15:18). Round 2 fix: Lane FE `fix/r2-index-exit-watch-1128` ("Fixed, not tested", pushed 06:03). Section 7, R2-F2.
- **F3** When a leg is moved, the stop on the old leg is cancelled correctly, but you are told through two reads that can fail, so the new leg may have no stop and no line. Round 2 fix: Lanes FD and FA (not done at 05:18). Section 7, R2-F3.

### 2. What the lanes decided for you tonight (21 entries from the build, plus round 2)
The literal heading "Decided for the owner" is not in the older result files; these are their equivalent entries ("decided meanwhile", "Decisions I took (owner away)", "SPEC CHANGE pending the owner"). Each is one line with its lane. **You confirm or reverse any of them; none of them is final until you say so.**

| # | Decided | Lane |
|---|---|---|
| 1 | A tick stamped 15:29:59 that arrives at 15:30:03 counts as the close (ADR-330 (36) says "received up to 15:30:00") | N |
| 2 | Paper entries outside market hours stay refused (ADR-212); the tick box exists only in market hours; allowing after-hours entries would be a SPEC CHANGE | N |
| 3 | Once a price is shown after the close it never moves until the next open; an earlier day's price carries its date | N |
| 4 | A closed trade's ending line names only: your exit, your stop, expiry settlement, "not recorded", "No plan was set" (plan stop, target and time-exit endings are not built: a close after a plan alert reads "your exit") | V |
| 5 | A percent plan target on a closed trade prints "target not available", never an invented number (no entry max profit is stored; that needs a migration, not done) | V |
| 6 | The Plan button is added to real position groups too | V |
| 7 | A fired leg stop's pop-up and History row carry no max-loss line | V |
| 8 | The per-lot figure is shown only when every leg has the same lot count | P |
| 9 | An unknown expiry kind gets timing style "intraday", not a guessed weekly or monthly row | J3 |
| 10 | A paper order with no freeze limit stored is not refused (ADR-081); a hard refusal would be a SPEC CHANGE | W |
| 11 | Paper exits are not lot-checked, so an exit is never blocked; this departs from ADR-092 "every order": SPEC CHANGE (Lane K now refuses an exit above a stored freeze limit: ADR-330 (51)) | W, K |
| 12 | The lot check is per order: 8 lots open, then 8 more with a limit of 10 is accepted (Lane K now counts the total the leg will hold: ADR-330 (50)) | W, K |
| 13 | Plan breakevens stay before charges, with a basis line (you answered ADR-330 (17): same) | Q |
| 14 | The Live card "Entry price" column shows the paper book's average price; to be checked against Positions (**open question LQ-2**) | Q |
| 15 | With no figure from the server, "Real P&L" shows a dash with a sentence (the build now shows the Connect sentence or the figure: see Lane TC below) | Q2 |
| 16 | 30 spec-silent controls: today's behaviour is written into the requirements (a table to read in one place) | U |
| 17 | After the close, the total is blank with its reason when no trade can be priced | L |
| 18 | A leg with no live price blocks Confirm; after hours a held close counts as live (ADR-212) | U |
| 19 | Lane M's side-closed question is asked with or without a plan (ADR-330 (46)); the patch is not applied in the build | M |
| 20 | Round 2, Lane FA: the price age is told against the browser's clock when the dialog opens; the dialog re-asks the market state on every Confirm (no timer: run discipline E2); a stop row for a leg not among the open legs reads "NIFTY 22300 PE 3 Nov" | FA |
| 21 | Round 2, Lane FB: a failed re-read keeps the contract-list line already shown; after an unknown add the page locks until the strategy is reopened; **no change** to Add to Paper's two steps (the name step, the tick): one press would be a SPEC CHANGE to ADR-330 (19) and (28) | FB |
| 22 | Round 2, Lane FC: "Now" is the worker's stored reading with its time, for open records only; the take-profit and real-mode exits sentences are new (below); the far-month badge is the existing "Monitoring paused" with the server's reason | FC |
| 23 | Round 2, Lane FD: nothing brought over where the build already holds the same change (booked result in the totals); the real first-fill connection hold is left as a listed gap | FD |
| 24 | Round 2, Lane TB: "Select all N shown" is the label; the partial-failure sentence is the shared "The page could not get an answer from the server."; "staged exits" read as ADR-330 (49); the "30 second hold" is the Undo wait | TB |
| 25 | Round 2, Lane TE: the full run excludes the `full_chain` marker; each named test file ran on its own clean database | TE |
| 26 | Lane TC (walk of the round 1 commit): the real app with no stored Zerodha session builds no market book, so the seeded closes cannot reach any screen (defect D-1); TC used a harness with a silent socket for the other screens; paper fills were inserted by SQL because the route refuses paper orders after the close (the plan's old SW-6 line "the entry is the last captured price" conflicts with it) | TC |

### 3. New on-screen sentences waiting for your read
About 70 sentences (round 1 build) plus those of round 2. **They are listed word for word in the appendix at the end of this file (Appendix A), grouped by screen.** The ones you will see first on Saturday: the exit dialog line **"The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."** (decision (60)); the three lines under a stop (**"If this stop fires, the sold <leg> is left without protection."**, **"Max loss now: Rs <amount>."**, **"Max loss then: Rs <amount> (worst case: NIFTY at zero)."**); **"Not being watched: no worker has reported in the last 2 minutes."**; **"Contract list of <date>. Today's list loads at about 08:35."**; the price banner family (**"Market closed. Prices are from 27 Nov 2026, 15:30:00 IST."**, **"Prices are not live. Figures are as of HH:MM:SS IST."**); and the round 2 sentences (the exit-dialog age lines, **"Working out the outcome..."** per leg, **"The last paper order got no answer and may be stored..."**, **"This approach is not built because the whole trade would not be in profit with every open leg closed at its planned price."**).

### 4. Two things that will look wrong on Saturday and are known
- **No Zerodha login on the weekend (Lane TC defect D-1):** with no stored Kite session the app may not show the seeded closes at all ("Not available" for the indexes). If the PC sees that, it writes "known D-1", not a seed failure (section 6, "Lane TC's corrections").
- **The 13:28 stop case (#876) and the 2028 date** need two read-only data pulls from the PC (section 8): words and counts only, never a price value, address, login, port or key.

### 5. Questions that still wait for you
LQ-2 (Live card "Entry price"), LR-Q18 (which time the builder banner shows for a mixed trade), LR-Q19 (should "Plan: Get Rs X" come back), U-Q12 (what a greyed Add Selected says), Lane H's three unbuilt asks, Q4, Q7, Q8 and Q9 of 13 Nov, and OQ-2 of the modular-doors file (delete the dead exit door). Answers given in chat after 27 Nov evening were not checked.

## 0. Rules of the run (read first)

1. **Write down the build commit for every result** (round 1: `5fc6b102`; there is no tag; section 2 step 8 says how to confirm it). Every PASS names the commit. **Every check names the board items it proves** (its "Board items" line).
2. **Four states in every result** (column "State"): `Fixed, not tested` / `Passed in cloud` / `Passed on PC (market closed)` / `Approved (PC, live)`. This plan can only move a check to `Passed on PC (market closed)`; `Approved (PC, live)` is Monday's. **PASS only if every step was run and the expected text was seen.** Otherwise PARTIAL, and name the steps not run. A seen
   difference from the expected text is FAIL: write the exact text seen.
3. **Never write NOT CHECKED for lack of time.** If a check could not be run, write what blocked it (for example "the branch was not in
   this round's build"). A check that is more than the round's time allows is split: run the first half, PARTIAL, and say where you stopped.
4. **Alerts: look in Active AND in History** every time a check says "alert".
5. **Every new problem is an observation:** screen, the exact text, the time (HH:MM IST). **Every awkward thing is a usability note**
   (UX-nn) with the same three parts. Keep them in two separate lists. Do not fix anything during a round.
6. **Status comment on PR #722 every 60 minutes**, in the fixed short format of 27 Nov:
   `STATUS HH:MM | Kite connected: no (weekend) | feed: none | build head: <short id> | now: <check id> (started HH:MM) | done since last status: <ids with PASS/FAIL/PARTIAL> | observations: <ids> | blocker: none or <what>`
   then a blank line, `---`, and `_Generated by [Claude Code](https://claude.ai/code)_`.
7. **A check is never skipped because a helper's budget is low:** give the helper more.
8. Run order inside a round: set-up (section 2), then the checks of the round in the order of section 4, critical (money, stops, exits,
   prices) first.
9. A fix lane whose branch is not in the round's build: its checks are run anyway as a baseline (write "BASELINE: fix not in build");
   they are run again in the first round that carries the fix.
10. **Each round re-runs the previous round's FAILs first**, then the checks that first carry a new fix. Before each block of checks: look at the server link (a dropped link is **"infra, re-run", never FAIL**) and count the database role's connections (limit 10, shared): `SELECT count(*) FROM pg_stat_activity WHERE usename = 'ofo_app';` [X2: role name taken from the allowlist check in section 2; confirm]. The two-user speed run (T2-16) only when fewer than 6 are in use.
11. Types: **Functionality** = the app does the right thing; **Screen** = the right words, numbers, layout; **User experience** = easy
    to use and understand (usability notes go here).
12. **Known F1, F2, F3** (section 7) seen in round 1 are written as observations tagged "known F1/F2/F3", not as a FAIL. They are not on the round 1 pass line.
13. Record each result as one row in `docs/process/screen-checks-2026-11-28.md` (create it) with columns:
14. **On every FAIL or PARTIAL write three things (round 2 rule):** **the sentence seen** (exact), **the sentence expected** (exact, from the check), and **known or new** (known = named in this plan as a known defect or finding, for example D-1, F1 to F3; new = anything else). The PC needed a second request for this on 28 Nov.
15. **Memory rule (PC round 1, 13:37: free memory fell to 1.7 GB and the API, worker and feed had to be stopped):** one browser window, one helper at a time, tabs closed after each check; **check free memory before each block of checks and stop below 3 GB** (write the figure). Chrome is opened again for round 2 and kept to one window.
16. **Speed checks (Plan watch, Alerts, anything timed) are never run with a second tester working** at the same time; write the server's own answer time beside what the page showed.
17. **Cloud first (owner, 28 Nov; version 6): the PC runs only its own list**: the set-up, the PC ONLY checks and the cross-check sample of the page "Version 6: CLOUD FIRST". **Every other check is NOT run on the PC**; it is proven in the cloud (Lane TG's walk and the lanes' tests) and stays in this file as the cloud list. If a PC check on the list fails and its cloud proof said PASS, write it as new and send it back: the cloud proof was wrong.
18. **PC keep-alive (board row I-95):** the PC stays awake for the whole run (power plugged in, sleep and screen lock off); the API, worker, feed and screen server are not stopped between checks except where a check says so; at the start of each round the PC writes the machine's free memory and that it did not sleep since the last round.
    `| Check | Items proved | Build head | What I did on the screen | What the screen showed (exact text) | Screenshot file(s) | PASS / FAIL / PARTIAL (unrun steps) / BLOCKED (what) | State (one of the four) | Build commit | Time IST |`. Screenshots stay on the PC (never copy images into the repo).

## 1. Round 1 and what the build carries

**Round 1 build: commit `5fc6b1023234b9efb948db731d903ad957f341c1`** (short `5fc6b102`) on branch `integration/weekend-1127`. **There is no tag** (a tag push is refused for build lanes): every result names the commit. The branch tip has moved on (it now holds only Lane Z's documents); the PC takes the commit above, not the tip.

| Round | When (IST) | Build | What it is for |
|---|---|---|---|
| 1 | Sat 28 Nov 08:00 to 12:00, started by the owner | commit 5fc6b102 | the checks of section 4 and section 6 (market closed, paper only), the two data pulls (section 8) |
| 2 | Sat 28 Nov 21:00 to Sun 01:00 | the round 2 commit the coordinator sends (section 9; `integration/weekend-r2-1128`) | round 1's FAILs again, the three known findings F1 to F3 (section 7), the fix lanes FA to FE (section 9) |
| 3 (final build) | Sun 29 Nov 12:00 to 16:00 | the final build | round 2's FAILs again; this is the build Monday runs |

**What is in the build** (Lane Z's note; all are ancestors of the commit, checked with `git merge-base --is-ancestor`): Lane M3's join of the 27 Nov lanes (U index-quote `f61f7935`, J loss-stop `3e0b9780`, R plan-save `8b45807a`, R2 plan-read `1d0f56e7`, O alert-screens `b07425fc`, V plan-door, K order-limits `8880aa24`, L pnl-totals, N last-close with **migration 0059** (`1ff969f2`), W live-test-small `bcbff804`, M maxloss-line `5a718413`, H speed-fixes `90c4fed5`, stop-follows-leg `6bd22cb6`), plus Lane U2 exit-all (decisions (59), (60); code `a7ccf4a9`), Lane R3 plan-read-2 (`3260e094`), builder-open (`0faf4e71`, decision (61)), Lane Y page-handovers (`546d653f`: "Monitoring paused" badge, one Plan watch request, decision (64) real-position row), Lane K2 order-door-2 (code `5ee104a5`), worker-join final (`c1eb7a67`), Lane J3 worker-2 (`b1d8d3ee`) and Lane Q3's worker-chain tests (`0a0bdea2`). **Left out:** `hotfix/worker-2-1127` is in; `feat/0058-plan-acceptance-1127` (its migration is renumbered 0060 and is a round 2 item) is NOT in; Lane Y item 3 ("not-live notice once") is not built.

**Known and open in this build, NOT a round 1 failure** (Lane Z's independent Opus review of the stop and exit paths = REVISE; the coordinator's pull comment lists them as "known and open, to be fixed in round 2"): **F1** the builder can unlock Exit too early after an exit with an unknown outcome; **F2** an index exit may not fire when the index price feed is silent while the trade reads as watched; **F3** a cancelled stop of an old leg is not always told to the user when a leg is moved. Each has a round 2 check written now (section 7). If a round 1 check shows one of these, write it as "known F1/F2/F3", not as a new FAIL.

**What cannot be tested with the market closed** (not on this plan; they are Monday and mostly optional, section "Monday" of `test-plan-2026-11-30.md`): any exit that completes (the server refuses exits when the market is closed); Add to Paper size checks (Lane K: the market-closed gate refuses first); AF-01 prices frozen at 15:30; the instrument list across 08:35 and decision (61)'s line; plan-stop alerts (the worker computes nothing while the calendar says closed; the weekend proof is Lane Q3's worker-chain test, 12 of 12 cases pass in the cloud, plus the scenario-mode try W-09).

## 2. Set-up for each round (prepared now; nothing is prepared at execution time)

Do these in order, then write one line "round N set-up done at HH:MM, commit <short id>". It is not a test: no PASS or FAIL. Sources: Lane Z's pull order (RESULTS-lane-z.md, "THE PULL ORDER FOR THE PC"), Lane N's and Lane J's RESULTS; lines marked `[X2]` are this plan's own logistics. **[OWNER APPROVAL]** = waits for the owner's typed "yes" (the owner starts each round and gives each approval himself).

0. **Look at the database link first** (it reconnects by itself in about 10 s; look anyway). Count the database role's connections: `SELECT count(*) FROM pg_stat_activity WHERE usename = 'ofo_app';` (limit 10, shared). [X2: role name from the allowlist check in step 4; confirm.]
1. **Back up the database first** (production `ofo_dev` on the VPS over SSH): `pg_dump -Fc -d ofo_dev -f <backup folder>/ofo_dev-<date>-<hhmm>-round<N>.dump`; copy to `%USERPROFILE%\\ofo-backups`; verify the size is equal on both machines and `pg_restore --list <file>` shows TABLE DATA entries above 0 (the 26 Nov dump was about 1.8 MB, 47 entries). If it fails, stop. [X2: the VPS disk is about 90 percent full: delete the dump of the round before last.]
2. **Pull the commit** (Lane Z, step 2 read with the coordinator's "no tag"): the PC's local test branch `test/screen-2026-11-27` (head `bdb0d126`, not on origin, kept in a git bundle) **stays exactly as it is, never reset**. Then: `git fetch origin integration/weekend-1127`, `git checkout -b test/weekend-r1 5fc6b1023234b9efb948db731d903ad957f341c1` (a new local branch), and confirm `git rev-parse HEAD` equals that commit. For rounds 2 and 3 the coordinator sends the round's commit; use the same command with a new branch name (`test/weekend-r2`, `test/weekend-r3`). Stop the API, the worker supervisor and the frontend before the checkout.
3. **Migration 0059_last_close** (round 1 only; rounds 2 and 3: `alembic current` must still end `0059_last_close (head)`), **[OWNER APPROVAL]**: one new table `last_close` and grants on that table only; no change to any existing table; old code runs unchanged with the table present; new code on an un-migrated database serves "not available"; migrate-first and migrate-last are both safe. **Old-code-safe proof (Lane N's RESULTS, word for word):** "0059 adds one table (`last_close`) and grants on that table only (SELECT; INSERT; UPDATE of price, price_at, source; no DELETE or TRUNCATE). It changes no existing table, column, constraint, trigger, function or grant, and does not rebuild the grant allow-list function. No code before this push reads or writes `last_close`. So old code runs unchanged with the table present; new code on an un-migrated database logs one error per write or read and serves no stored close (fails closed: "not available"). Migrate-first and migrate-last are both safe. The PC applies it only with a verified backup." Lane Z proved 0057 to 0059 to 0057 to 0059 on a scratch database. Command (Lane Z): `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`; `alembic heads` prints one head, `0059_last_close`. [X2: Lane J's older text says never to use `db_run.py` for the production migration because it targets `ofo_test`; the two instructions conflict. Use Lane J's own command below, which names `ofo_dev`, and read the head from it.] Lane J's command, word for word, from the checkout root: `python -c "import os,subprocess,sys,urllib.parse; sys.path.insert(0,'scripts/orchestrator'); import db_run as d; g=d.read_env(d.GLOBAL_ENV); u='postgresql+asyncpg://'+g['WINDOWS_VPS_PG_ADMIN_USER']+':'+urllib.parse.quote(g['WINDOWS_VPS_PG_ADMIN_PASSWORD'],safe='')+'@127.0.0.1:5432/ofo_dev'; e=dict(os.environ,ALEMBIC_DATABASE_URL=u); [subprocess.run([sys.executable,'-m','alembic','-c','backend/ofo_app/alembic.ini']+a,env=e,check=True) for a in (['current'],['upgrade','head'],['current'])]"` Expected: the last line ends `0059_last_close (head)`. Never run `alembic downgrade`. No other migration is applied this weekend (none of the other lanes adds one); a migration without a written old-code-safe proof is not applied and its checks are BLOCKED. Migration 0058/0060 (plan acceptance) is not in the build.
4. **Read-only checks after the migration:** `SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post');` returns without an error; `SELECT count(*) FROM strategy_history WHERE NOT public.ofo_strategy_change_items_valid(change_summary);` returns 0.
5. **Round 1 only: Lane N's one-time seed, BEFORE any restart** (17 rows expected: 15 open contracts + NIFTY 50 + SENSEX):
   5a. DB tests (on a FRESH test database, lesson 2: `db_run_fresh.py`): `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/test_migration_0059_last_close.py tests_app/test_basket_facts_unheld_index.py tests_app/test_close_freeze_routes.py tests_app/test_closed_label_route.py` (all pass).
   5b. Dry run: `set PYTHONPATH=backend` then `python -m ofo_app.last_close_store seed <snapshot folder>\\close-2026-11-27-seed.json --map instrument_id=tradingsymbol --map price_at=price_time --check` (the renamed-key copy of Friday night's snapshot, lesson 4; only if a seed is needed: round 1's seed stays, so rounds 2 and 3 seed nothing). Expected: "would write 17", "skipped 0"; the "database:" line must be the production database; "keys in the first row" and "mapping chosen" show price from the tick price and price_at from the tick's own time; the first row shows a 27 Nov 15:30:00 +05:30 time. If a field is reported twice, re-run with `--map price_at=<key>` (or `price=`).
   5c. **[OWNER APPROVAL]** Real run (the same command without `--check`): "written 17", "unchanged 0", "skipped 0"; a second run prints "written 0", "unchanged 17".
6. **Frontend:** `npm ci` then `npm run build` in the checkout the app serves from (never in a worktree).
7. **Restart order: API, then worker, then feed.** Ctrl+F5 once. No Kite login (weekend). The feed process is started and stopped by the PC for W-25: RESULTS gives no start command ("stop the FEED process"; "FEED_MODE=bus as today"): write the command you use in the log. With the feed stopped the API reads NOT_CONNECTED within about 3 to 5.5 s.
8. **Confirm the build:** `git rev-parse HEAD` equals `5fc6b1023234b9efb948db731d903ad957f341c1`; the health page answers `{"status":"healthy","database":"connected"}`; the health reply names which contract list is in use (decision (61)): write it.
9. **Sanity (2 minutes):** Positions > Paper lists the 9 running paper trades; Alerts > Active opens and its row count equals the bell number; no red error box on Home. If something is red, that is observation O-01.

### Lessons of the round 1 close (PC, 28 Nov 13:58 IST) that change the set-up

1. **After the checkout, restart the frontend server (vite) too, and check one new route through it** (vite reads the route list once at start): R2-0 and R2-0b below.
2. **Migration tests run on a fresh test database:** use `db_run_fresh.py` (for example `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/test_migration_0059_last_close.py` and, for round 2, the migration test files of 0060 and 0061); `db_run.py` tests an old copy at revision 0030. (The PC named the file; if its arguments differ from `db_run.py`, copy the PC's working command into the round log.)
3. **Every query selects by strategy id, never by a name like '#207'.** The alert tables are **`paper_alerts`** and **`strategy_alert_style`**; there is no `actionable_alerts` table. W-21, W-22, W-09 and D-1 below are corrected; run `\d public.paper_alerts` first to list its columns and select the id, rule, outcome, answer and time columns of the strategy.
4. **The seed with the real snapshot** needs the renamed-key copy `close-2026-11-27-seed.json` and the flags `--map instrument_id=tradingsymbol --map price_at=price_time` (until Lane FD4's fix is on the PC). **Round 1's seed stays: round 2 seeds nothing** (`select count(*) from last_close` reads 17).
5. **The full push check (`prepush.py`, about 40 minutes and a lot of memory) is never run on the PC.** The PC's results branch (local `test/weekend-r1` at `8a278ad3`, holding `docs/process/screen-checks-2026-11-28-r1.md`) stays local; the cloud pushes it. `ci_local` (16 pass, 0 fail on `8a278ad3`) is not the push gate.
6. **Memory:** rule 15 of section 0: one browser window, one helper at a time, tabs closed after each check, free memory checked before each block, stop below 3 GB.
7. **Speed checks never with a second tester working:** rule 16.

### Round 2 additions to the set-up (do these before the first row of round 2)

R2-0. **Restart the frontend server (vite) AND the API on the round 2 commit** (stop both, check out the commit, `npm ci` and `npm run build` if `frontend/` changed, start the API, the worker, the feed, then the frontend server). **Why:** vite reads the API route list (`docs/api/openapi.json`) once when it starts: after a checkout with new routes, every new route loses its `/api` prefix and answers 404 (round 1: `/api/plan-watch`, `/api/monitoring-state` and `/api/market/exit-state`, until vite was restarted at 11:37). **Write the commit** (`git rev-parse HEAD`) in the results. **The API's environment must carry `FEED_MODE=bus` and `REDIS_URL`** (Lane TG, 28 Nov): without `FEED_MODE=bus` the API reads "no bus" as "no worker" and every trade shows "Not being watched: no worker has reported in the last 2 minutes." even with the worker running; the worker runs as its own process.
R2-0b. **Confirm each route that is new since `5fc6b102` answers through the frontend's own address** (the vite port, not only the API's port 8000): open each in the browser's address bar and write the status: `http://127.0.0.1:<vite port>/api/real/strategies/<id>/triggers` (the one new route of the round 2 build, Lane FD2; use a strategy id that exists, for example 209; an empty list is a good answer), and again the three of round 1: `/api/plan-watch?strategy_ids=209`, `/api/monitoring-state`, `/api/market/exit-state`. All must answer 200. A 404 means vite is stale: restart it and look again. Routes whose behaviour changed (same paths: `POST /paper/strategies/{id}/orders` with its request key, positions, monitoring status, execute, plan accept, opportunities, exit market, plan-watch batch, playbooks) are covered by the checks of section 9.
R2-1. **Pull the round 2 commit `829ff65f26716f1efbcbac98ea3ba6aefdc350d9`** (frozen by the coordinator 28 Nov 17:15 IST; it is also the last commit of Lane Z2's RESULTS file): `git fetch origin integration/weekend-r2-1128`, `git checkout -b test/weekend-r2 <commit>`, `git rev-parse HEAD` must equal it. Keep round 1's local branch `test/weekend-r1` exactly as it is. No tag.
R2-2. **Migrations 0060_plan_stamp_only_on_switch then 0061_order_request_keys, applied in ONE step, [OWNER APPROVAL], after a verified backup** (coordinator, 28 Nov afternoon). 0060 only replaces the plan guard function (no table or column change, no row changed; it re-pins the app-role allow-list md5). 0061 (Lane FD3) is additive (one new table for the order request key). **Round 1 code is NOT safe on the changed database** (0060: accept does not stamp `accepted_at`, and a plan with a NULL playbook pointer loses its stops on edit): migrate and restart the new code in one sitting; if the code is rolled back, run `alembic downgrade 0059_last_close` as well. Command: the section 2 step 3 command; `alembic heads` prints one head, `0061_order_request_keys`. **Only if the final round 2 commit carries both files** (the coordinator sends the commit, expected about 16:30 IST; check `ls backend/ofo_app/alembic/versions | tail -n 3`); if it carries only 0060, apply 0060 and write that 0061 is not in the commit. The order request key needs Redis (R2-3).
R2-3. **Redis must be up:** the order request key is refused with 503 `request_key_store_unavailable` when the store is down.
R2-4. **No new seed (lesson 4).** Round 1's 17-row last-close seed stays (`select count(*) from last_close` must still read 17). Restart order: API, then worker, then feed, then the frontend server.
R2-5. **Round 1's seed note:** the dry run of step 5b refused 15 of 17 rows because the snapshot's `name` column holds the trading symbol; the PC made a copy of the snapshot with the key renamed and "written 17" followed. If it happens again, do the same and write it; Lane N should add a flag.

## 3. How the checks are written

Each check: **id**, the **board items** it proves (UX-nn, OBS-nn, D-nn, N-nn, T-ids, ADR-330 points, issue numbers; the board itself is the coordinator's private status page, so the ids come from the repo's triage and ledger files), what it proves (one line), **Type**, **27 Nov result** (where the check existed), **First carried** (the round whose build is the first to contain the fix; "no fix needed" where only unrun steps remain), exact steps, the exact expected text or figure, and what to write down.
Ids keep their 27 Nov names (T1-20, AF-02, ...). New ones are W-01 and up. A "MONDAY ONLY" mark means the check needs live prices and is in `test-plan-2026-11-30.md`; the table at the end of that file lists where each 27 Nov check went.

## 4. The checks

Order of the round: **W-33 first** (seed done, restart, nine screens), then A (money, stops, plans, prices: W-01 to W-07, W-09, W-30 to W-32, W-34, W-35), then B (W-10 to W-29), then the reused 27 Nov checks (section 5), then the after-close checks and the sweep (section 6). Critical (money, stops, exits, prices) first inside each part.

### W-33 The nine screens after a restart, with the last close stored (Lane N; decisions (56), (62), (63))
- **Board items:** AF-02, AX-05, A3; ADR-330 (56), (62), (63); the "no price" half of the 27 Nov sweep
- **Proves:** AF-02 and the "no price" half of the 27 Nov sweep (27 Nov: after the API restart every running trade read "no price" and Home read "Paper P&L paused - prices not live"); AX-05; A3; decision (56). **Type:** Screen / Functionality. **First carried:** R1 (Lane N `fix/last-close-1127` b6777ce7). **Run only after set-up step 5 (the seed wrote 17 rows).** Without the seed the result is BASELINE: write what you see.
- **Known defect D-1 (Lane TC), read before the walk:** with no stored Zerodha session the real app builds no market book and the seeded closes may not reach any screen: the banner may read only "Market closed.", the indexes "Not available", and the chain status `NIFTY- live`. The weekend PC has no Kite login: if the app still holds Friday's session the screens show the closes; if the session expired, D-1 applies. **If you see D-1, write "known D-1" and mark the walk PARTIAL; it is not a seed failure** (check the seed rows with `select count(*) from last_close` first: 17).
- **Lane N's walk, word for word. 1. Restart the API.** Within 30 s open each screen; expected on every one: the banner **"Market closed. Prices are from 27 Nov 2026, 15:30:00 IST."** and the 27 Nov 15:30 figures; no "no live quote", no "Time not available", no load or feed-stop time labelled as a price time.
  - Home: NIFTY and SENSEX at their 27 Nov closes; paper rows priced.
  - Positions Real and Paper: the banner; the 9 running paper trades priced (tile greying waits for Lane V).
  - Live Strategies: the banner at once, also while a card is loading; no moving "Checked at".
  - My Strategies: the banner at the top.
  - Builder #209: legs at the close; the panel "as of" is a price time; a load time, if shown, says "Checked at".
  - Option Chain: held contracts priced at the close; other strikes "not available" with the reason.
  - Leg picker: a strike with no leg shows one figure that does not move over 2 minutes (27 Nov "AF-01 extra": picker prices kept changing).
  - Stops panel: "NIFTY last <close> as of 15:30:00" (not "Index values unavailable.").
  - Add to Paper: **no tick box**; Confirm sends once and the server's market-closed sentence shows (this replaces the 27 Nov AF-08 expectation of a tick box; the tick box is a market-hours, feed-stopped case: Monday).
- **2. Restart the API again:** the same figures and times (read back from the table, not re-written). **3. Stop the feed while the API runs:** the banner keeps the close time, never the stop time.
- **Other expected sentences (Lane N, pending owner read):** "Prices are not live. Figures are as of HH:MM:SS IST." / "Prices are not live." (no time known); "Market closed. Prices are from 15:30:00; 1 leg as of 26 Nov, 15:29:59."; "Checked at HH:MM:SS IST"; "NIFTY last 25,607.20 as of 15:58:01"; "Paper P&L paused - prices not live" (no ", as of" clause when no time known). The 27 Nov sweep texts to compare: Home read "Market closed. Prices are from 27 Nov 2026, 15:58:01 IST." with Total P&L "—"; Positions Paper all 9 trades "no price"; the Exit dialog opened with an enabled Confirm; Live Strategies "Checked at 27 Nov 2026, 16:07:45 IST" moved while the banner was fixed.
- **Open owner questions Lane N decided meanwhile:** a 15:29:59 tick arriving 15:30:03 counts as the close; once a price is shown after the close it never moves until the next open.
- Then run the sweep SW-0 to SW-9 (section 6) for the screens not in this walk.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-01 Plan save, change and reset, read back in three places
- **Round 2 correction (PC round 1, 28 Nov):** Reset keeps the typed levels by design (ADR-330 (9), (32)). Step 4 expects either the **"Put back to the playbook's values: ..."** list (naming what differed) or the **"Nothing differed from the playbook, so nothing was put back."** line: write which, and which values stayed. #209's plan block prints no stop or target figure (O-R-09): read the stop in the plan sheet. Steps 3, 5, 6 and 7 were not run in round 1: run them.
- **Board items:** T1-13 follow-up; A-H #209 (Stop (Rs) 100 saved, block kept Rs 996.13); #201; UX-34 (plan block keeps the old stop); OBS-26; T2-19
- **Proves:** Lane R hotfix (A-H #209: Stop (Rs) 100 saved but the plan block kept Rs 996.13; #201 "no server answer in 3 tries"); T1-13 follow-up; T2-19 (Reset to playbook).
- **Type:** Functionality. **27 Nov result:** T1-13 PASS; T2-19 FAIL (changed and switched-off markers not shown). **First carried:** R1 (Lane R `hotfix/plan-save-1127` 8b45807a).
- **The three places** (call them P1, P2, P3): P1 = the plan block on the trade's builder page; P2 = the Plan watch box and the Stops panel (Positions > Paper row, and builder `?strategy=<id>`); P3 = Settings > Adjustments > Show for this strategy > Change plan values.
- **Steps (feed absent, as on the weekend):**
  1. Pick running paper trade A (any of the 9). Write the plan values in P1, P2, P3 before touching anything.
  2. Open the plan of A, type **Stop (Rs) 100**, press Save. If the app refuses (no prices), write the exact sentence and read the three places: all must still show the OLD values. If it saves, the three places must all show Rs 100 and keep it after you reload and wait for the next Plan watch read.
  3. Change a second value (Target (Rs) 500), Save, read the three places again.
  4. Press "Reset to playbook". Read the three places: all must equal the playbook values; the sheet marks what changed and what is switched off (27 Nov FAIL: markers not shown; write what is shown).
  5. Percent stop on a MONTHLY strategy (Lane R round 3 step 1), feed absent: type a percent stop, Save: expect the price-read refusal and the stored plan unchanged in P1, P2, P3. Same for Reset to playbook.
  6. Stop the backend, press Save on the plan sheet: expect the sheet to stay open with the typed value and the single sentence **"Not confirmed: reload to see whether it was saved."**; the browser Network tab shows ONE request; no "Try again" button.
  7. Settings > Adjustments > Show for one strategy > Change plan values; unplug the network (DevTools > Network > Offline), Save: same sentence, typed values still in the boxes, no "Try again".
- **Expected:** step 2/5 refusal wording is the catalogue row `plan_save_prices_not_read` (wording "pending owner read"); Lane R's slow-price text is **"Prices could not be read in time to check this plan."** Write the exact refusal text seen. P1 = P2 = P3 in every step.
- **Not possible this weekend:** Lane R round 2 step 2 (prices slow, over 4 s). The route-delay tool (W-23) is the only slowing tool and RESULTS does not name the route the plan save uses: MONDAY ONLY (T1-13 re-run) unless a later version names the route.
- **Write down:** build head; the three places before and after, each step; exact refusal text; request count.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-02 Plan watch load: one request at a time, never "not available"
- **Round 2 correction (PC round 1, 28 Nov):** **ONE tester only** (nobody else creating drafts or using the app). Open the API log and write the **server's own answer time** (the `request GET /api/plan-watch` line, in milliseconds) beside what the page showed. Round 1: every box read "The plan watch is not available right now." for the first minutes; about 24 s for 9 trades, about 6 s for 1 (log: "the poll waited ... for the database gate").
- **Board items:** T2-01, T2-02 (FAIL); N-12; OBS-18 (answers 7 to 20 s); issue-list rows 8 and 22 (34 requests a minute)
- **Proves:** Lane R plan-watch load hotfix (27 Nov n=204 requests in about 6 minutes; N-12 "answer takes 15-20 s"; T2-01/T2-02 FAIL).
- **Type:** Functionality / Screen. **27 Nov result:** T2-01 FAIL, T2-02 FAIL (0 of 10 boxes filled within 60 s), AX-14 FAIL. **First carried:** R1 (Lane R 8b45807a; Lane R2 `hotfix/plan-read-1127` 1d0f56e7, Lane R3 3260e094: both in the commit).
- **Steps:** 1. Open Positions > Paper with 5 or more planned rows. Open DevTools > Network, filter `plan-watch`, leave it 3 minutes. 2. Count: requests pending at one moment (expected: at most 1) and in all (expected: about 9 or fewer). Rows keep their numbers and show "Updating the numbers..." and never "not available". 3. Switch to another browser tab for 2 minutes: no plan-watch requests; come back: exactly one starts. 4. Open the builder of a planned strategy: its box reads about every 15 s.
- **Expected texts:** "Updating the numbers..." (never "not available" when the server answered); a box before its first rows reads "Loading the rule check..." and never "Updating the numbers..." first. **Round 2b (Lane TG, cloud): the plan watch never prints "Still loading. The server is taking longer than usual to answer." inside 12 s; the expected text while it waits is the box line "Loading the rule check..." (the builder then shows "Updating the numbers" at about 22 s). Only Alerts prints "Still loading." (at about 22 s). If it is not there for the plan watch, that is not a failure.**
- **Write down:** the two counts, time to first rows per box, any "not available".
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-03 Plan watch box, weekend wording (market closed)
- **Round 2 correction (PC round 1, 28 Nov):** **ONE tester only**, and write the **server's own answer time** (API log request line) beside what the page showed. Round 1: builder #209 showed 16 rows, each "Not checked", "Updating the numbers...", and also "The page could not get an answer from the server." and "The expiry list could not be read. Try again in a moment."
- **Round 2b (Lane TG):** while the answer is slow the box reads **"Loading the rule check..."** (this is the expected text; "Still loading..." is not printed for the plan watch); no error block was seen with a 9 or 12 s delay in the cloud.
- **Board items:** T2-01, T2-02, T2-04 ("Not applicable" line), AX-14, AX-13
- **Proves:** Lane R box rendering and AX-14; T2-01, T2-02, T2-04 (the "Not applicable" line), AX-14.
- **Type:** Screen. **27 Nov result:** FAIL ("not available right now", no trigger rows). **First carried:** R1 (Lane R).
- **Steps:** 1. Builder of a strategy with a plan: first the box says **"Loading the rule check..."**; the answer then shows its rows with the as-of time. 2. Positions with plan rows: each compact box shows rows, not "not available", after its turn in the queue. 3. With no prices (weekend) the rows show **Paused** or **Not checked** with the server's text, never an empty box. 4. Stop the backend for one minute: the last rows stay, marked **"Could not refresh the rule check..."**, with the as-of time. 5. Open the console: a `plan watch: line N degraded ... field(s): ...` warning, if shown, names the field; write the line and the raw 200 body of `/api/strategies/<id>/plan-watch`. 6. Builder `?strategy=<id>` for A-H #209: Stops panel and plan rows show; **16 rows marked Not checked**. 7. T2-04 part: a trade whose one side is closed: the row, the two answers and the "Not applicable" line (27 Nov: the line could not show because Plan watch was unavailable).
- **Write down:** every box's words, the console line, step 6's row count.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-04 Adjustment history: does the server hold the rows? (D-27, read-only): strategies 209 and 201
- **Board items:** D-27, T2-14. **Type:** Functionality. **Strategy 155 does not exist on this PC (round 1 got "The page or action you asked for is not available here."): use 209 and 201, never 155.**
- **Steps (Lane R's steps, with the ids changed):** 1. Log in to the app in the PC's browser. Open the builder on trade **209** and open "Adjustment history"; open devtools, Network tab, filter "adjustment-history". 2. The request is `GET /api/strategies/209/adjustment-history` (read only): copy the full JSON reply and the status code to `d27-209-adjustment-history.json`. 3. Write: (a) `rows.length`; (b) per row `step` (entry / adjustment / settle / stop), `number`, `at`, `is_exit`, `orders[].kind/side/quantity`; (c) `totals.adjustments_used` and `totals.adjustments_max`; (d) what the builder's section shows (the "no step recorded" line, the error line, or N rows). 4. Repeat for **201**. 5. Rows in the JSON but the section empty or short = a screen defect; a 404 or `rows: []` = the server has none (then also `GET /api/paper/strategies/209`, saved as `d27-209-paper-book.json`, with `orders[]` count, kind, time and `status_word`).
- **Expected:** the builder section matches the JSON. Round 1 read: #209 has 1 entry row and no adjustment row (write what you see).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-05 Order limits: what can be seen with the market closed (Lane K)
- **Board items:** T2-10 (FAIL); ADR-330 (50), (51), (52); Lane W item 15; triage C-item 1
- **Proves:** T2-10 (27 Nov FAIL: Add to Paper accepted 5000 lots on one leg with no refusal); decisions (50), (51), (52); Lane W item 15; Lane K. **Type:** Functionality / Screen. **First carried:** R1 (Lane K `fix/order-limits-1127` 8880aa24).
- **Why short:** Lane K's RESULTS: "Add to Paper is refused by the existing market-closed gate before any size check, so the size sentences cannot be seen closed." The size checks (101 lots; 60 then 50; an exit above the freeze) are **MONDAY ONLY** (Monday plan, T2-10). Do these two steps:
- **Step 0 (Lane K, word for word): count the stored freeze quantities for the running indexes.** On the PC database: `SELECT exchange_segment, count(*), max(file_date) FROM public.exchange_freeze_limits GROUP BY 1;` Write the rows. If there are no rows for an index (SENSEX has none: no BSE_FO source), "exit above freeze" for that index is **not testable on the PC (BLOCKED: no stored freeze quantity), not FAIL**; the lots limit is testable on every index (Monday).
- **Step 1:** Settings page: "Most lots in one leg" shows **100** (it was 10,000). If it shows anything else: FAIL, write the number.
- **Step 2 (Add to Paper with the market closed):** put one draft leg in the builder (5000 lots), press Add to Paper, read the answer. Expected today (Lane N's walk, and Lane U's code): the server's market-closed sentence, nothing in the book. Write the sentence word for word. (Lane U's code text, not in its RESULTS: "The market is closed. Orders can be placed once it opens." with "No order can be placed while the market is closed." and "Return during market hours and execute again." If the screen differs, that is an observation.)
- **Expected sentences (for Monday; pending owner read):** "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)."; "An exit of {lots} lots on {contract} is above the most one order can carry ({max_lots} lots)."; "The entry price for {contract} must be above 0."
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-06 One P&L number in the places (Lane L), prices frozen
- **Board items:** T1-15 (FAIL); D-06, D-07, D-40, D-41, D-56, D-68; ADR-330 (62); UX-32; AF-07 (also AF-05, T1-16)
- **Proves:** D-06, D-07, D-41, D-56, D-68, D-40; T1-15 (27 Nov FAIL: Home total and Positions Paper total differ in the same minute; they cover different trade sets); decision (62); UX-32; AF-07 (Positions with Zerodha disconnected). **Type:** Screen. **First carried:** R1 (Lane L `fix/pnl-totals-1127` d94ca716).
- **Steps (market CLOSED, frozen prices; Lane L, word for word):** 1. Open Home, note "Total P&L" (call it X). Open Positions, note "Paper P&L" with its "(after charges)" label: it must equal X to the paisa. 2. Open Live Strategies and My Strategies: the sum of the rows listed with a figure plus the settled ones equals X unless the line "N strategies left out" says otherwise. 3. Tick "Show closed positions": the number in "Includes N closed strategies" equals the number of closed rows listed; if not, the line is hidden (by design). 4. Completed Strategies: with a held-at-broker row, the label reads "Select all N-1 of the N shown" (27 Nov UX-AF2: "Select all 16 shown" while 17 were listed). 5. (UX-32) Open Home, change a trade in another tab, return to the Home tab: the Total P&L updates within a second without a reload. 6. (AF-07) Positions with Zerodha disconnected shows "-" and the connect sentence under Real P&L. Also, for one running trade X1 and one closed trade Y1, write the figure in the five places (Live card, My Strategies row, Positions, Home, builder) in the same minute.
- **Expected texts:** "Select all {n} of the {m} shown" (for example "Select all 16 of the 17 shown"); "Includes N closed strategies"; "N strategies left out"; "Paper P&L paused - prices not live"; "Paper P&L" with "(after charges)" once, never twice. If it still differs while CLOSED: write both figures and the "Includes/left out" lines of each page. (Monday: reload Home then Positions within 10 seconds; one price tick of difference is allowed.)
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-07 Owner decisions (46) to (64): each walked once
- **Board items:** ADR-330 (46) to (64)
- **Proves:** each decision of `spec/decisions/ADR-330.md` points (46) to (64) (read at head 657cd12a of `fix/ic-live-test-1123`; (64) from Lane Y's result file). **Type:** Functionality / Screen. Rows: **walk now** = this plan has the steps; **Monday** = needs a live market; **rule** = no walk of its own.

| n | Decision in short (its own words) | Where | First carried | Walk |
|---|---|---|---|---|
| 46 | Side-closed question comes for every trade, with or without a plan, and stays until answered when the plan is removed | running trade whose call side closed | Lane M (patch not applied) | Monday: needs a live trade whose side closes |
| 47 | All plan exits alert on the first check past their level or time (loss stop % and rupee, 2x-credit, profit target, time exit); no candle-close wait, no quiet time, no daily cap | Alerts > Active | Lane J 3e0b9780 | Monday T1-05; weekend try W-09 |
| 48 | The stop is removed with the move; review step says "The stop on <leg> will be removed; set a new one after the move."; then the app offers a new stop on the new leg | builder, Change expiry on a leg with a stop | `fix/stop-follows-leg-1127` 6bd22cb6 (no PC steps) | Walk the review step now (W-32); confirming the move needs prices: Monday |
| 49 | Only the changed leg's Exit is blocked: "This leg has a change waiting; review or discard it first."; other legs exit | Positions, builder | Lane U f61f7935 | Walk now (W-25 case D) |
| 50 | The lots limit counts the total the leg will hold after the order: "This would make <leg> 16 lots; the limit is 10." (Lane K's wording: "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ...") | Add to Paper, Increase quantity | Lane K | Monday (market-closed gate comes first) |
| 51 | A paper exit above the freeze quantity is refused as a real order would be | Exit dialog | Lane K (exit refused) | Monday; no freeze row: not testable (W-05 step 0) |
| 52 | A user with no limit set gets 100 lots per leg | Settings, Add to Paper | Lane K | Settings shows 100 now (W-05 step 1); refusal at 101 lots Monday |
| 53 | An opportunity is "Acted on" only when a paper order from it is accepted; Cancel leaves it open | Compare approaches | Lane W bcbff804 (in the commit) | Walk now (W-10) |
| 54 | Each running trade on Positions has a Plan button beside Exit and Stops, opening the builder's plan sheet | Positions | Lane V fb66dfb1 | Walk now (W-29) |
| 55 | Three lines under a leg stop: "If this stop fires, the sold <leg> is left without protection." / "Max loss now: Rs <amount>." / "Max loss then: Rs <amount> (worst case: NIFTY at zero)." | Stops panel | Lane V | Walk now (W-29) |
| 56 | One line at the top when prices are not live: "Prices are not live. Figures are as of <time> IST."; each trade keeps its last figures, greyed, with no repeated sentence | Positions, Live Strategies | Lane N b6777ce7 | Walk now (W-33, part of the nine-screen walk) |
| 57 | A closed trade opens read-only: "This trade is closed. Its legs and result are shown below; it cannot be changed." and one line "Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23."; no Plan watch box | builder of trade 173 | Lane V (closed sentence also Lane W) | Walk now (W-29, W-16) |
| 58 | Rule: a paper order differs from a real one only by its tag | every order screen | deferred issue | rule; seen through (49), (51), (59), (60) |
| 59 | Exit all is not blocked with a staged change; "Exit all closes every open leg. The change waiting on <legs> is not sent and will be discarded."; after: "The change waiting on <legs> was discarded."; Cancel gives the change back | Positions, builder | Lane U2 a7ccf4a9 (in the commit) | Cancel part now (W-26); the discard sentences Monday (optional) |
| 60 | Market closed: the Exit dialog opens, shows the legs, "The market is closed. Exits can be placed from 09:15 on <next trading day>.", Confirm greyed | Positions Exit | Lane U2 a7ccf4a9 (in the commit) | Walk now (W-25 A to D) |
| 61 | 08:30 to about 08:35 the builder keeps yesterday's list with "Contract list of <date>. Today's list loads at about 08:35." | builder | builder-open `0faf4e71` (in the commit; the page that shows the line is Lane V's, "not built" per Lane J2) | Monday 08:30 to 08:40 (optional) |
| 62 | Home and Positions total show the booked result of closed trades: "Includes N closed strategies." and "9 strategies left out: their prices are not live." | Home, Positions | Lane L d94ca716 (Lane N for the closed-market state) | Walk now (W-06, W-33) |
| 63 | While the market is closed a restart reads the stored close back; every screen shows it with its own date and time; none stored: "prices are not available" with the reason | every price screen | Lane N b6777ce7 | Walk now (W-33) |
| 64 | A real position row and alert tag: "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."; no Exit, no Stops (Lane Y item 1b) | Positions real card | Lane Y `546d653f` | Monday 09:45 (needs the real position; optional) |

- **Write down for each walked row:** the check id above, the sentence seen word for word, PASS / FAIL / PARTIAL.

### W-08 Instrument list across 08:35: not on this plan
- N-07 to N-11 and decision (61): the refresh runs on weekdays only, from 08:35, so it cannot be seen on a weekend. **Monday 08:30 to 08:40** (Monday plan), with the fallback "if a builder says No legs yet at 08:40, restart the API and note it".
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-09 Plan-stop alert in scenario mode (market closed): try it, Monday T1-05 is the real proof
- **Round 3b plan fault (Lane TG2, cloud, 28 Nov): use scenario path PATH-10, not PATH-01.** PATH-01 is a profit drift and can never reach a loss stop. Set `OFO_SCENARIO=PATH-10` for the API and the worker, plan Stop (Rs) 500, frames 0 to 9, 25 s after each frame. (Proof level: cloud browser PASS on PATH-10.)
- **Board items:** T1-05 to T1-08; ADR-330 (47)
- **Proves:** T1-05 to T1-08 chain (stop level crossed, one alert row in the plan's rule list). **Type:** Functionality. **First carried:** R1 (Lane J `hotfix/loss-stop-1127` 3e0b9780).
- **Honest limits:** Lane J's RESULTS: "Not proven end to end here: I did not run this chain with a plan stop on a path scenario; whether a PATH fixture reaches a given rupee level mu[st be checked]." There is **no price-replay tool** (cancelled; Lane Q2). The scenario worker exists (`python -m ofo_app.background` with `OFO_SCENARIO`), and ticks only on PATH scenarios. If the try does not give an alert, the result is **PARTIAL: tool limit, Monday T1-05** (not FAIL).
- **[OWNER APPROVAL] before step 1:** scenario mode changes `APP_ENV` for the API and the worker and seeds a trade into `ofo_dev` (the database with the 9 running paper trades; the seed script refuses any other database). Restart the normal app afterwards.
- **Steps (Lane J (b) and (c), word for word):** set `APP_ENV=development` and `OFO_SCENARIO=PATH-<nn>` for both processes (`backend/ofo_app/scenario_mode.py`); seed the trade with `python scripts/orchestrator/dev_run.py <checkout> python scripts/seed_scenario.py PATH-<nn>`; save a plan with a Stop (Rs) on "Scenario PATH-<nn>"; move the market frame by frame with `POST /api/scenario/frame` (the worker reads the shared frame index before every cycle). A frame past the stop must give one alert row within a minute (or at entry + 5 minutes when the stop was already crossed at entry). Do it for: a rupee stop, a % stop (T-06), a profit target (T-07 and rupee), the time exit, a stop already crossed when the plan is saved. For each, the read-only check: `SELECT rule_id, shown_at AT TIME ZONE 'Asia/Kolkata' FROM public.adjustment_suggestions g WHERE g.strategy_id = <the id of the strategy named Scenario PATH-<nn>, read on screen> ORDER BY shown_at;` and, if no row appears, the worker log line `background: strategy <id> check skipped: <reason>` (reasons `prices_STALE`, `prices_LEG_MISSING`, `not_ticked`, `no_gate_read`).
- **Expected:** one `adjustment_suggestions` row per crossed rule, and the alert in Alerts > Active (look in History too). The 5-minute period after entry delays an alert and never swallows it.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-10 Compare approaches: "Open in builder and prepare basket", Cancel and Confirm (Lane W item 10; T2-13)
- **Round 3b (Lane TG2, cloud PARTIAL): the API must run with `TEST_CATALOGUE_DATE` set to the scenario day** (else no contract matches); "Compare approaches" is the link on Positions > Adjustment opportunities. **Word conflict, owner decision pending:** with the worker running TG2 saw the row close as **"Completed at <time>"**, not "Acted on"; decision (53) in this plan says "Acted on - Paper - not sent to Zerodha"; the spec (REQ-112 AC-2) uses the word "Completed", but its AC-3 sets it only from Zerodha-confirmed fills. The PC writes the word it sees; neither word is a fail until the owner picks.
- **Board items:** T2-13 (FAIL); UX-22; issue-list rows 13 and 26; REQ-112 AC-2; ADR-330 (53)
- **Type:** Functionality. **27 Nov:** T2-13 FAIL (an opportunity stayed "Acted on" after Cancel with no order placed). **First carried:** R1 (Lane W). Needs an alert with an opportunity row (Alerts has rows from 27 Nov; if none is open: BLOCKED, name it).
- **Steps:** Alert > Compare approaches > "Open in builder and prepare basket" > Cancel. Look at the opportunity. Prepare again, Confirm.
- **Expected:** after Cancel the opportunity still reads **"Open"**; after Confirm it reads **"Acted on - Paper - not sent to Zerodha"**.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-11 Full-exit approach stages the held legs (Lane W item 11)
- **Round 3b (Lane TG2, cloud: not done): the API must run with `TEST_CATALOGUE_DATE` set to the scenario day.** The confirm list is the builder's "Review and add".
- **Board items:** UX-21 (staged exits show "No legs yet")
- **Type:** Functionality. **First carried:** R1. **Steps:** Alert > Compare > the full-exit approach > "Open in builder and prepare basket" > Cancel on the confirm list.
- **Expected:** the held legs show as exiting with **"N pending changes"**, never "No legs yet"; wording **"Exiting these legs (staged, not placed yet)"**.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-12 Home closed-strategies line (Lane W item 1)
- **Board items:** T1-16 / ADR-330 (35), (62) family (no own id found)
- **Type:** Screen. **First carried:** R1. **Steps:** Home with closed strategies; then Positions. **Expected:** the line under "Total P&L (after charges)" reads the same **"Includes N closed strategies."** as on Positions.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-13 "Closed by system" in Alerts History (Lane W item 2; T1-09-close)
- **Round 2 correction (PC round 1, 28 Nov):** **ONE tester only**; write the **server's own answer time** (about 6 s in round 1) beside what the page showed. Round 1: the page showed a red box "The page could not get an answer from the server." under Answered alerts before the server answered.
- **Board items:** T1-09-close; T1-09 (FAIL); ADR-330 (3); triage C-item 12
- **Type:** Screen. **First carried:** R1. **Steps:** Alerts > History: an alert whose trade closed unanswered. **Expected:** **"Closed by system: the trade closed at 10:23"** (your trade's time in place of 10:23). Also check Alerts > Active holds none of them (27 Nov T1-09 FAIL was the same alerts staying Active after the last leg was exited during market hours; that exit step is MONDAY ONLY).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-14 Time-exit wording on the plan sheet (Lane W item 3; T1-10)
- **Round 2 correction (PC round 1, 28 Nov):** The Target and Target (Rs) boxes are **linked** (typing in one fills the other), so "Target and Target (Rs) show different values." cannot be reached by typing. Write what you see (round 1 saw "Target is not valid." and "Stop is not valid."); the different-values sentence is pinned by Lane W's unit tests, not reachable on screen.
- **Board items:** T1-10; UX-17
- **Type:** Screen. **First carried:** R1. **Steps:** plan sheet: a time-exit date in the past, Save. Then clear and type values that are not valid in each of Time exit, Target, Stop, Target (Rs), Stop (Rs), Max adjustments. Then type different values in Target and Target (Rs), and in Stop and Stop (Rs). (The alert half "Time exit reached" needs the worker, which computes nothing while the market is closed: MONDAY ONLY, the 09:25 time-exit trade.)
- **Expected:** **"Time exit date is in the past."**; **"Time exit date is not valid."**; **"Time exit is not valid."**; **"Target is not valid."** (same for Stop, Target (Rs), Stop (Rs), Max adjustments); **"Target and Target (Rs) show different values."**; **"Stop and Stop (Rs) show different values."**; Monday: the alert reads **"Time exit reached: the plan's time exit is HH:MM"**.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-15 Two legs on one contract: the Save-draft sentences (Lane W item 4)
- **Round 2 correction (PC round 1, 28 Nov):** The sentence names the two legs in screen order: expect "Legs 1 and 2 are the same contract (NIFTY 1 Dec 24050 CE), one <side of leg 1> and one <side of leg 2>." (round 1 saw "one Buy and one Sell"). For the same-side variant use leg 2's own Buy/Sell toggle to give both legs the same side (the badge did not flip in round 1: write what the toggle does).
- **Board items:** issue-list row 2; OBS-03; D-60
- **Type:** Screen. **First carried:** R1. **Steps:** builder: two legs on one strike and expiry; Save draft; once with the same side, once with opposite sides. Check the leg numbers in the sentence equal the numbers on screen.
- **Expected (same side):** **"Legs 1 and 2 are the same contract and side (NIFTY 1 Dec 25900 CE, Sell)."** then the BUILT sentence **"Join them into one leg with more lots, or change one of them."** (Lane TG2, 28 Nov: the plan said "...or change one to a different contract."; the spec has no exact sentence for this case (closest ADR-319, REQ-030 AC-12), so the built sentence is the expected text; TG2 checked the API replies only: PARTIAL; the PC reads it on screen.) **(opposite sides):** **"Legs 1 and 2 are the same contract (NIFTY 1 Dec 25900 CE), one Sell and one Buy."** then **"A strategy holds one leg per contract: remove one of them, or change one to a different contract."** (27 Nov N-03 saw a red box "This strategy definit..." for two identical legs: write the full text seen.)
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-16 A completed trade opens read-only (Lane W item 8)
- **Board items:** UX-11, UX-23; ADR-330 (14), (57)
- **Type:** Screen. **First carried:** R1. **Steps:** My Strategies > a Completed trade > Open in Builder. Then a running trade, then a fresh builder. **Expected:** the completed trade shows on the right **"This trade is closed. Its legs and result are shown below; it cannot be changed."**; the running trade and the fresh builder keep their own text.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-17 Alerts Active on a slow connection (Lane W item 9)
- **Board items:** UX-12, UX-33
- **Type:** User experience. **First carried:** R1. **Steps:** DevTools > Network > Slow 3G; open Alerts > Active. **Expected:** "Loading..." first, then the rows (never an empty page between).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-18 Typing at once into Rename and Save (Lane W item 7; T3-09, N-02)
- **Board items:** T3-09; N-02; issue-list row 5; OBS-02
- **Type:** User experience. **First carried:** R1. **Steps:** My Strategies > Rename on a row, type immediately; press Esc. Builder > Save, type immediately. **Expected:** the text goes in; Esc closes (27 Nov N-02: Esc was ignored until the rename box was clicked: write if it still is).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-19 Net Positions name on one line at 1366 px (Lane W item 13)
- **Board items:** UX-29
- **Type:** Screen. **First carried:** R1. **Steps:** browser width 1366 px (DevTools device toolbar, Responsive, 1366); a paper strategy with an open position > Net Positions. **Expected:** "NIFTY 1 Dec 25900 CE" (your contract) on one line.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-20 Max-loss line when a stop is typed (Lane M; T1-03)
- **Round 2 correction (PC round 1, 28 Nov):** B-N1 changed shape in round 1: use #209 or #201 (Positions > Stops). Expect "If this stop fires, max loss becomes ... (now ...)" with no date and no year, and "Sold option with less protection: <leg>" naming the leg with a short date ("1 Dec"). Round 1 saw the Exit dialog on #209 print "NIFTY 25600 PE 2026-12-01" (ISO date, O-R-07; UX-A18): write it as known.
- **Board items:** T1-03; N-01; OBS-01 (issue-list row 4); UX-07 (UX-03, UX-08 not fixed)
- **Proves:** the ISO date "2028-12-01" in the max-loss line (27 Nov T1-03; N-01). **Type:** Screen. **First carried:** R1 (Lane M `hotfix/maxloss-line-1127` 5a718413; passed on the PC on 27 Nov at 14:20 for T1-03).
- **Steps:** Positions > Paper > B-N1 (the trade used on 27 Nov; if it is gone, any paper trade with a sold NIFTY PE) > Stops. On NIFTY 1 Dec 25650 PE type the stop **"Above 102.55"**.
- **Expected, exactly:** **"If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25). Sold option with less protection: NIFTY 1 Dec 25750 PE."** (the figure is unchanged; no ISO date, no year). The "now" figure may need a price: if it differs only in "now", write it and mark PARTIAL; the rest must match. The "fired index exit quotes its own tick" half (T1-11) is MONDAY ONLY.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-21 Lane M read-only SQL (data only; send the rows)
- **Round 3b (Lane TG2): strategies 194 and 201 do not exist in the cloud database; they exist only on the PC (his real rows), so W-21 is PC ONLY and stays so.** In the cloud write PARTIAL; optionally list the `paper_alerts` columns first (`\d public.paper_alerts`).
- **Round 2 correction (PC round 1, 28 Nov):** The table `actionable_alerts` does not exist (round 1); the alert tables are `paper_alerts` and `strategy_alert_style` (lesson 3): item 4 below is corrected; select by strategy id.
- **Board items:** D-2 data pull (2028 date); OBS-01
- Run each on the VPS with `psql -d ofo_dev` over SSH (read only):
  - Item 1: `SELECT id, name, instrument_type, strike, expiry, exchange_token, first_seen_at, last_seen_at, currently_listed FROM public.catalogue_contracts WHERE id IN (SELECT DISTINCT contract_id FROM public.paper_orders WHERE strategy_id = 194);` (if an expiry reads 2028-12-01 the row is wrong at the source).
  - Item 3: `SELECT DISTINCT o.contract_id, c.expiry FROM public.paper_orders o JOIN public.catalogue_contracts c ON c.id = o.contract_id WHERE o.strategy_id = 194;` and `SELECT id, expiry FROM public.catalogue_contracts WHERE name = 'NIFTY' AND strike = 25750 AND instrument_type = 'PE';`; and from the browser the request URL of `GET /paper/strategies/194/leg-stop-risk` with its reply body.
  - Item 4 (corrected: the table is `paper_alerts`, there is no `actionable_alerts`): `\d public.paper_alerts` to list the columns, then select its id, rule, outcome, answer and time columns `WHERE strategy_id = 201 ORDER BY id;` (by id, never by name).
- **Type:** Functionality (data). No pass rule: PASS = the rows were read and sent. If strategy 194 or 201 does not exist: PARTIAL, say so.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-22 Lane J read-only SQL for the stop alerts (data only; send the rows)
- **Board items:** D-1 data pull (#207); T1-05 to T1-08
- **#207:** `SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r WHERE r.strategy_id = 207 ORDER BY 1, 2;` (`held_at_entry = t` and `seen_clear = f` on `plan.rupee_loss` means the stop was held at entry).
- **A-E #202:** `BEGIN READ ONLY; SELECT h.id, h.rule_id, h.trigger_id, h.stage, h.value, h.threshold, h.reason, h.held_at AT TIME ZONE 'Asia/Kolkata' AS held_ist FROM public.adjustment_held_crossings h WHERE h.strategy_id = 202 ORDER BY h.id; SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r WHERE r.strategy_id = 202 ORDER BY 1, 2; SELECT g.id, g.rule_id, g.trigger_id, g.value, g.threshold FROM public.adjustment_suggestions g WHERE g.strategy_id = 202 ORDER BY g.id; ROLLBACK;`
- **A-D #200:** `adjustment_held_crossings` should hold a `plan.rupee_loss` row with reason daily limit, value about 162.5, threshold 100, held about 11:00 to 11:05 (use the A-E query with strategy id 200).
- Worker log lines to look for at any time the worker runs: `background: strategy 209 check skipped: prices_<state>` (reasons `prices_STALE`, `prices_LEG_MISSING`, `not_ticked`, `no_gate_read`). Type: Functionality (data). PASS = rows read and sent.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-23 Route-delay tool (Lane Q2; makes the app slow on purpose, for T2-08-style and slow-answer checks)
- **Board items:** T2-08 (tool check only)
- **Proves:** that Lane Q2's only working tool runs. **Type:** Functionality. **First carried:** R1 (Lane Q2 5bdfdde0).
- **Steps:** 1. Write a rules file (JSON) with times that carry the offset `+05:30` (a naive time is refused), for example:
  `{"delay_routes": [{"prefix": "/api/strategies/", "suffix": "/plan-watch", "seconds": 5, "from": "2026-11-28T10:00:00+05:30", "until": "2026-11-28T10:10:00+05:30"}]}`
  2. Set the environment variable `OFO_HOLDBACK_FILE` to the file's path. 3. Start the API with **`python -m uvicorn --factory holdback:create_app --app-dir tests_app`** instead of the usual start (it wraps the real API). 4. Open a planned strategy's builder inside the window: the plan-watch answer takes about 5 s longer. 5. Restart the API the usual way afterwards.
- **Expected:** the delayed route answers about 5 s late; other routes unchanged. The `withhold_tokens` and `silence` keys need the Kite relay, which is not built: do not try them (T1-23 and AX-01 are MONDAY ONLY, and are "not possible" until the relay exists).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-24 Lane U: what is on this plan and what is Monday's
- Lane U (`hotfix/index-quote-1127`) fixes live-price reads and the exit sentences. On this plan: T1-20 and T3-10 (section 5) and W-25 (Exit dialog with the market closed). **Monday only:** every step that needs ticking prices or a completing exit (T1-02, T1-22, T2-08 completing part, the 429 log lines, "not live" flips, Lane U's measurements for Monday's open).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-25 The Exit dialog with the market closed (Lane U2, decision (60); Lane U, decision (49))
- **Round 2 correction (PC round 1, 28 Nov):** Round 1 ran the dialog lines ("The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.", Confirm grey; on #210 both legs' Exit disabled with "This leg has a change waiting; review or discard it first."). Round 2: also run parts B, D and E (they need the feed or the API stopped; the main session stops them).
- **Board items:** T2-08 (FAIL), T1-02c, UX-01, UX-04, UX-09, UX-13, UX-20, UX-25, UX-31, UX-35, issue-list rows 10, 11, 21, 25, OBS-16, OBS-17, ADR-330 (49), (60). **Type:** Functionality / Screen. **In the build:** Lane U2 `a7ccf4a9`, Lane U `f61f7935`.
- **Expected text (all, Lane U2, pending owner read):** **"The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."** (the next trading day in place of "Monday 30 Nov"); Confirm grey; the legs the exit would close are listed.
- **A. Feed running.** Builder, open a paper trade, tick one leg, Exit. Expected: the dialog opens with the leg, the line above, Confirm grey; Cancel; no order in the Orderbook. Repeat with Exit all (one row per open leg, same line).
- **B. Feed stopped** (stop the feed process, API up). Same steps. Expected: the same line (**not** "Prices are not live"), Confirm grey.
- **C.** Positions > Paper > tick a leg, Exit; and Exit all if offered there. Expected: the same line, with the feed running and stopped.
- **D.** Stop the API for 10 s, then press Exit. Expected: **"The market status could not be read. Try again in a moment."** and Confirm grey; start the API and reopen: the market line.
- **E. Decision (49), Lane U step 4:** stage a lots change on leg 2 of a trade with 3 or 4 legs. Expected: leg 2's Exit is grey with **"This leg has a change waiting; review or discard it first."**; legs 1, 3 and 4 have Exit enabled. Exit leg 1: the dialog lists only leg 1's exit (with the market closed the line above and Confirm grey); leg 2's change is still staged after Cancel. After a trade change: **"The change waiting on <legs> was not kept because the trade changed; stage it again."** (pending owner read).
- **Not on this plan:** an exit that completes ("Exit placed on paper (order n).", "Placing exit...", the unknown-outcome lock): Monday, and F1 (section 7). Lane U2's known minor items: the market answer is fixed for one opening of the dialog (opened 15:29:55 keeps Confirm on after 15:30; opened 09:14:50 stays grey after 09:15 until reopened): not a round 1 check.
- **Write down:** the time the feed was stopped and started, the sentence word for word on each screen.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-26 Exit all with a staged change (decision (59), Lane U2): two cases, numbered
- **Board items:** ADR-330 (59); PC round 1 row W-26 (FAIL: written on a stale screen server, raise-lots step skipped, void). **Type:** Functionality / Screen. **In the build:** Lane U2 `a7ccf4a9`. **The raise-lots step is mandatory.**
- **Steps (each numbered; do all):**
  1. Builder of a running paper trade with at least 2 legs (round 1 used #201, 2 legs).
  2. **Raise the lots with the Multiplier (the leg rows' lots are plain text on a running trade; there is no per-leg lots control). Do not press Review. ALL legs rise.** A pending change shows (for a four-leg trade "4 pending changes"; Lane TG, 28 Nov). **Mandatory: without it you are testing case B, not case A.**
  3. Press **Exit all**. Read the dialog.
  4. Press **Cancel**. Read the builder: the raised lots must be back exactly as you typed them.
  5. Press Exit all again and then **Discard** (if offered). Read the builder.
  6. **Case B (nothing staged):** discard everything first (builder shows no pending change), press Exit all, press Cancel. Read the builder.
- **Expected, case A (a staged change; decision (59)):** the dialog lists every open leg and the market-closed line **"The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."** (Confirm grey); the dialog **names the change waiting** on the leg you raised: **"Exit all closes every open leg. The change waiting on <leg> is not sent and will be discarded."**; **Cancel restores the raised lots exactly, and no exit is staged.** Write the sentence the dialog really shows (if it shows only the market-closed line and not the discard sentence, write that: it is the market-closed variant of the dialog).
- **Round 2b (Lane TG, cloud PASS):** the discard sentence names EVERY leg whose lots changed, in one list: "Exit all closes every open leg. The change waiting on <leg>, <leg>, ... is not sent and will be discarded." (four legs: all four named). After Cancel the lots are back as typed ("2 lot" on all four, "4 pending changes", multiplier still 2) and no exit is staged.
\1\n- **Case B as seen in the cloud (Lane TG):** the Exit all dialog has NO discard sentence and Confirm is grey; after Cancel the builder reads "4 pending changes" and "Exiting these legs (staged, not placed yet)" with a Discard button. Still an owner decision.\n- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new. Monday (optional): the discard sentences after a Confirm ("The change waiting on <leg> was discarded.").

### W-27 (merged into W-25)
- Decision (60) is walked by W-25 A to D. This id is kept so that the 27 Nov mapping does not move.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-28 Alert and Stops screens (Lane O), market closed is fine
- **Board items:** T2-19 items 1, 2, 3, 5 to 8, 10, 12; UX-02, UX-16, UX-24, UX-26, UX-27
- **Proves:** T2-19 item 1 (needs Lane R2's patch applied first), items 2, 3, 5 to 8, 10, 12; UX-02, UX-16, UX-24, UX-26, UX-27. **Type:** Screen. **First carried:** R1 (Lane O `fix/alert-screens-1127` b07425fc). Lane O's RESULTS "market CLOSED is fine" except the two live parts named below.
- **Steps and expected (Lane O, word for word):**
  1. (Lane O's patch is merged by Lane R3 plan-read-2, which is in the commit; if the sentences below are missing, write the commit and mark FAIL) T2-19: open a trade with a plan, Customise triggers, switch off T-05 and change another condition, save. Open the plan sheet, press "Reset to playbook", confirm. Expected under the button: **"Put back to the playbook's values: triggers.T-02"** and **"Switched on again: triggers.T-05"**. If nothing differed: **"Nothing differed from the playbook, so nothing was put back."** The typed levels stay.
  2. Alerts > Active, a plan stop / target / time-exit alert whose row used to show only the trade name. Expected a reason line, for example **"Plan loss stop: 15.5750 (rule 15.4000)"**; with no figures **"Plan profit target"**. The title still reads "<name> (#id, expiry)".
  3. Alerts > History: headings **"Answered alerts"** and **"Stops and expiry settlements"**. If one read fails, its error line sits under its own heading, not above the other list. If answered is empty but records exist: **"No answered alerts yet."**
  5 and 6. Builder or Positions, a saved trade with an armed leg stop: Plan watch, "Armed in the Stops panel". Expected **"Leg stop on NIFTY 3 Nov 23450 CE: fires when the price rises above 90.00; price now 40.15"** (date as "3 Nov", never 2026-11-03). Market closed: no "price now" part (the "price now" part is the live one: Monday).
  7. Save a draft in the builder (do not add to paper): Plan watch shows **"No plan: nothing is watched for this strategy"**, not "This strategy was not found" (27 Nov N-04).
  8. Positions or builder, a saved trade, Stops panel, "Stop on a leg": each row reads **"Stop when the price goes [Above/Below]"** and **"Stop price [box]"** (visible words, not only a hint).
  10. Builder with a leg whose price you typed, then press Shift, Width, Hedge, a strike step or change the expiry so that leg moves. Expected under the leg list: **"Your price for leg 1 was replaced by the captured price 12.30, because Shift moved the leg to another contract."** (Hedge / Width likewise; expiry: "because you changed the expiry"; a strike step: "because you moved the strike"). If the new contract has no live price (the live part: Monday): "Your price for leg 1 was removed, because Shift moved the leg to another contract and the new contract has no live price right now."
  12. Click each top-menu item: each opens its page. In the picker, "Pick from Option Chain" with OI or Greeks shown switches back to LTP.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-29 Plan door, Stops lines and a closed trade (Lane V, decisions (54), (55), (57))
- **Round 2 correction (PC round 1, 28 Nov):** The fixtures for the real row, the SENSEX trade and the bought-call trade were absent in round 1: for each missing fixture write "BLOCKED: fixture <name>"; it is not a FAIL.
- **Board items:** ADR-330 (54), (55), (57); UX-A02, UX-A03; UX-10, UX-03, UX-08, UX-11, UX-23
- **Proves:** decisions (54), (55), (57); UX-A02, UX-A03. **Type:** Screen / Functionality. **First carried:** R1 (Lane V `feat/plan-door-1127` fb66dfb1). Lane V states none of these needs a feed.
- **(54) Positions page, filter All:** 1. Open Positions with one running paper trade and one running real trade (if no real position is open: write that and use paper only). 2. Each shows a **"Plan"** button (paper: beside Stops and Exit; real: right end of the group header). 3. Press Plan on the paper trade: the plan sheet opens (title, playbook, target, stop). Press Close. 4. Open the same trade in the builder, press its "Edit plan": the SAME sheet. 5. Press Plan on a trade with no plan: the sheet opens to set the first plan. 6. A fully closed trade shows no Plan button. (27 Nov: the plan sheet took 15 to 60 s to load: write the seconds.) Failure text: "Could not open the plan. Try again."
- **(55) Builder, running one-lot NIFTY iron condor:** 1. Stops panel, type a stop level on the bought 25650 PE leg. 2. After the pause, three lines appear, each on its own line: **"If this stop fires, the sold ... is left without protection."** / **"Max loss now: Rs ..."** / **"Max loss then: Rs ... (worst case: NIFTY at zero)."** 3. Type a stop level on the bought call leg: line 3 reads **"no upper limit (worst case: NIFTY keeps rising)"** and shows no amount. 4. Type a stop on the sold short call: the old one sentence appears. 5. Same on a SENSEX trade: the lines say SENSEX. While waiting: **"Working out max loss for this stop..."** shows from the moment a valid level is typed, then the answer replaces it; an invalid level shows none. Lane V's engine figures for the 27 Nov condor: Max loss now -7,800; Max loss then -1,674,725; exposed leg the sold 25850 PE (your trade may differ: write the figures; the three lines are the check).
- **(57) Closed trade:** 1. Open the builder on settled trade 173. 2. It shows **"This trade is closed. Its legs and result are shown below; it cannot be changed."**, the closed legs, the result, and one line **"Plan: stop Rs ..., target Rs .... Closed by expiry settlement at 15:30."** (or "your exit at HH:MM"). 3. No Plan watch box, no Add/Edit button, no "Add a leg to start one" (27 Nov T1-18 FAIL text).
- **UX-A03:** a fired leg stop's pop-up and History row carry NO max-loss line; the message is "Stop-loss: ... exited at ..." (seen only when a stop has fired: if none exists, write that).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-30 Stop percent read back in three places, weekly and monthly; Reset to playbook (Lane R3 plan-read-2, Lane R2)
- **Round 2 correction (PC round 1, 28 Nov):** Round 1: BLOCKED (no monthly Iron Condor trade, no "R2 test" playbook). A trade cannot be created with the market closed (Add to Paper is refused): stays BLOCKED unless one already exists; then it is Monday's.
- **Board items:** T1-13 follow-up, UX-34 (plan block keeps the old stop), T2-19 (Reset to playbook), triage C-item 7, Lane R2 monthly stop box showing 50 (27 Nov). **Type:** Functionality. **In the build:** Lane R3 `3260e094`, Lane R2 `1d0f56e7`. Lane R3's RESULTS "PC steps with the market CLOSED", word for word.
- **Set up once:** Settings > Adjustments > the Iron Condor playbook > make a copy named "R2 test" with T-06 weekly 50 / 50 / 40 and monthly 30 / 30 / 20 (the system playbook has equal rows, which would hide the difference), make it your active Iron Condor playbook. Have one running MONTHLY trade and one running WEEKLY trade (both Iron Condors, plan accepted from "R2 test"). The contract list must be loaded (a market day fetched at least once). [X2: if the PC has no such pair, that is BLOCKED: no monthly Iron Condor trade.] Expected stop box values (first stage): monthly trade 30, weekly trade 50.
- **Steps:** 1. Monthly trade: type stop 45 > Save > read on Positions, the builder and Plan watch: 45 everywhere. Weekly trade: the same, 45. 2. Monthly trade: change only the Target > Save: stop stays 30 on the answer, and 30 after closing and reopening, on Positions, builder and Plan watch. Weekly trade: stays 50. 3. Which row the live check used: open Plan watch for each trade, read the stop line: the monthly trade's stop line is the 30 % of its stored max loss (not 50 %); the weekly trade's the 50 %. In the worker log look for the line "adjustment check:" of the strategy. 4. Press "Reset to playbook" on each trade, confirm: the sheet shows **"Put back to the playbook's values: ..."** and **"Switched on again: ..."** (or **"Nothing differed from the playbook, so nothing was put back."**). Change T-02 first and switch T-05 off so you have something to see. The typed target, stop and time exit stay. 5. A trade whose expiry is 30 Mar 2027 (if you have one): the sheet shows no stop number and says why; a rupee stop saves. 6. Save a plan and, in the same moment, switch the PC network off or kill the backend request after the click (timeout); then reload: the plan is there complete. 7. If the contract list is not loaded: percent stop Save is refused with **"The stop could not be saved: whether this trade expires weekly or monthly could not be read."**; a rupee stop saves.
- Report any step where the stop number differs between Positions, builder and Plan watch for the same trade.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-31 Plan watch: one batch request per cycle (Lane Y item 2, Lane H)
- **Round 2 correction (PC round 1, 28 Nov):** Close every other browser tab of the app, restart the frontend server (vite), reload Positions once and count over one minute (stale tabs polluted round 1's count).
- **Board items:** T2-01 / T2-02 cause (n=204 requests in about 6 minutes); issue-list rows 8 and 22 (34 requests a minute); OBS-18. **Type:** Functionality. **In the build:** Lane Y `546d653f` (the Positions page change Lane H did not build) and Lane H `90c4fed5`.
- **Step (Lane Y, "PC step (market closed)"):** Positions with at least 5 open rows (with a plan): browser network tab filtered on `plan-watch`: ONE `/api/plan-watch?strategy_ids=...` per cycle, and none of `/api/strategies/<id>/plan-watch`. Also `grep -c "request GET /api/plan-watch" <api log>` after one minute: 1 (not N).
- If you still see one request per row: FAIL (the page change should be in the build), write the commit.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-32 Change expiry of ONE leg (the leg's own expiry chip): the review line (decision (48), #774)
- **Board items:** ADR-330 (48); issue #774; UX-16, UX-24; finding F3 (the after-move half); PC round 1 row W-32 (void: it used the wrong control). **Type:** Screen. **In the build:** `fix/stop-follows-leg-1127` `6bd22cb6` (Lane FA2 / FD continue F3).
- **Name the control exactly:** use **the leg's own expiry chip in the leg row** (the small expiry label on that one leg). **Do NOT use the "Change expiry" select: it moves ALL legs by design** (PC round 1 saw both legs of #210 move, "4 pending changes", with the sentence "Your price for leg 1 was removed, because you changed the expiry and the new contract has no live price right now."; that is the select's designed behaviour, not this check).
- **Steps:** 1. Open a running paper trade that has a leg stop (Positions > Stops lists it; round 1 used #210 / B-P4). 2. In the builder, click the expiry chip of the ONE leg that has the stop; pick another expiry. 3. Read the review step before confirming. 4. Do NOT confirm (with the market closed the server refuses; the review shows the market-closed line and Confirm is grey); press Cancel.
- **Expected:** **"The stop on <leg> will be removed; set a new one after the move."** (the leg named as the screens name it, for example "NIFTY 13 Oct 22800 CE"). Only that leg moves. If the leg has no stop the line does not show: write which leg you used and whether it has a stop. After a move (Monday): the app offers "Set a stop on <new leg>" (pending owner read).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-34 "Monitoring paused" badge: the worker's reason with the market closed, and when the worker stops (Lane Y item 1; worker fix)
- **Board items:** REQ-165 AC-6 / issue #868 family; UX-10; PC round 1 row W-34 (FAIL, real defect). **Type:** Functionality / Screen. **In the build:** Lane Y `546d653f`; the worker fix is in the round 2 lanes (section 9).
- **Round 1 result (a real defect, being fixed in the worker):** with the worker running and the market closed, every running trade read **"Monitoring paused" / "Health unknown" / "Not being watched: the worker does not list this trade."** (the PC saw this on all 9 running trades and on builder #209).
\1\n- **Round 2b (Lane TG, cloud): the trade needs a PLAN to be watched.** Planned running trade, worker running, market closed: "Monitoring paused" / "Health unknown" / "The market is closed." / "Since HH:MM" (same on Live Strategies, Positions and the builder; the API says `reason: market_closed`). A running trade with NO plan reads "Not being watched: the worker does not list this trade." with "No plan: nothing is watched for this strategy" beside it: that is the reader\'s design; the PC writes whether each of its nine trades has a plan. If the API\'s environment lacks `FEED_MODE=bus` every trade reads "no worker has reported" (R2-0).\n- **Stop/start half (Lane Y):** stop the worker process, wait 2 minutes, reload Live Strategies, Positions, and the builder of a running trade: each shows "Monitoring paused", "Health unknown", **"Not being watched: no worker has reported in the last 2 minutes."** Start the worker: within 30 s the badge goes. Restart the worker supervisor again at the end.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### W-35 Add to Paper with "prices are not live" ticked: the entry facts survive (Lane K2, order-door-2)
- **Board items:** the "entry spot was not stored" family (ADR-330 (28)); Lane K2 item 1. **Type:** Functionality. **In the build:** Lane K2 code `5ee104a5` (its RESULTS' PC steps are on the branch tip `f3e75bc7`, not in the build copy).
- **Steps (Lane K2, "market CLOSED, Saturday 08:00", word for word):** 1. Stop the feed process; open the app; the closed banner shows. 2. Open a fresh strategy in the builder, tick "prices are not live", type an entry price on each leg, press Add to Paper. 3. Read the strategy's entry facts: the Adjust page "Entry distance" line for that strategy (it names the entry spot and the call/put distance). **Expected: it shows the spot and distances, not "the entry spot was not stored".** Same step without the tick: the save is refused with its sentence and nothing is stored. (With the market closed Add to Paper may be refused by the market-closed sentence before this: write the sentence; then the result is PARTIAL: Monday.)
- The real order door (a leg above 100 lots refused) is Monday.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### TC-1 The charges tap on Positions > Paper (SW-3; Lane TC could not walk it)
- **Board items:** SW-3, T1-14 (charges basis). **Type:** Screen. **First carried:** R1 (baseline).
- **Steps:** Positions > Paper: read the totals strip, then open its charges tap. **Expected labels:** "Before charges", "Charges paid", "Estimated charges to close", "After charges". Seen elsewhere by TC: the totals strip `Charges paid ₹311.73`, `Booked P&L (after charges)`, `Unbooked P&L (after charges)`. Write what you see.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### TC-2 SENSEX and a far expiry on the Option Chain (SW-7; not walked)
- **Board items:** SW-7. **Type:** Screen. **Steps:** 1. Option Chain: hover a blank cell and write its title text. 2. Switch to SENSEX and to a far expiry; tick two contracts and read the Add controls. 3. Look for rows marked "Currently unavailable on Zerodha". **Expected:** the banner "Market closed. Prices are from <time>."; a blank cell "-"; "Currently unavailable on Zerodha" and "Some contracts are currently unavailable on Zerodha and cannot be added."; as applicable "This expiry is not in the catalogue." / "The catalogue lists no options for this expiry." / "No strikes match the filters."; on a Saturday the broker status says "market closed", never "reconnecting"; no "Stale", "Delayed" or "Unhealthy" word on closed cells.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### TC-3 Notification settings and a "side closed" alert (SW-8; not walked)
- **Round 3b plan fault (Lane TG2, cloud PASS): Notification settings is an ENTRY IN THE ALERTS MENU (page `/alerts/notification-settings`), not a button on the Alerts page.** Expected line unchanged: "No notification channels are set up yet."
- **Board items:** SW-8. **Type:** Screen. **Steps:** 1. Alerts: open notification settings and read the empty line. 2. If a "side closed" alert exists, open its "Add the legs again" confirm and read it; do not confirm. **Expected:** "No notification channels are set up yet."; the "Add the legs again" confirm text is not in the sources: write it as an observation. If no side-closed alert exists: write "none exists" (TC could not create one).
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### TC-4 The stop warning text on the Stops panel (SW-9; not typed by TC)
- **Board items:** SW-9, ADR-330 (55). **Type:** Screen. **Steps:** Stops panel (Positions > Stops): type a level in one leg stop and read its warning text; do not click Save unless a rule under test needs it; read the reason line next to Save. **Expected:** the three lines of W-29 (decision (55)) when a bought leg protects a sold leg; otherwise the server's warning text as sent; "Saved: stop <direction> <level>" / "Already set: stop ..." only after Save. Write what you see.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### TC-5 A settled strategy (not seedable by TC)
- **Round 2 correction (PC round 1, 28 Nov):** The Completed screen is at **`/strategies/completed-strategies`** (`/strategies/completed` is "Page not found", round 1 O-B-08). Round 1 saw on the builder of #173: "Paper - settled at expiry: SENSEX closed at <level>", "This trade is closed. Its legs and result are shown below; it cannot be changed.".
- **Board items:** T1-18, ADR-330 (57). **Type:** Screen. **Steps:** the settled SENSEX trade 173 (or any real settled row): Completed Strategies, the builder (W-29 (57)), Alerts > Records. **Expected:** Records row "Paper - settled at expiry"; Completed "closed <time>" or "closed: time not available"; "Charges not available: <reason>" where charges are missing. TC could not seed a settlement (it needs an expiry day).

## 5. Reused 27 Nov checks that can be proven with the market closed

Only the steps not run on 27 Nov are listed for a PARTIAL. Expected text that the old plan did not hold is marked: write what you see as an observation.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T1-20 The price feed is stopped: figures pause, Exit is blocked, Add to Paper asks for a tick
- **Proves:** with no price feed the paused sentence carries its "as of" time, the tick box says when the entry price was captured, and the what-if says it is not shown.
- **Type:** User experience
- **27 Nov result:** FAIL: "Paused sentence lacks the 'as of' time on Home and the tick box; Confirm refused when prices are not live." Home read "Paper P&L paused - prices not live" with no "as of <date>, <time> IST"; tick text "Prices are not live; the entry is the last captured price." has no "as of HH:MM"; D-37 NOT CHECKED; D-18 not run.
- **Fix carried first:** R1 (Lane U hotfix/index-quote-1127 head f61f7935, in the commit; the 'as of' time on tick text: no fix lane named)
- **Needs:** market closed OK (weekend: there is no price feed at all, so there is nothing to stop; write that down)
- **Steps:**
  1. NEW-T02: On a weekend there is no feed. Open Home and read the Paper P&L line.
  2. D-37: Open the builder with a saved or new strategy. In the what-if, pick a level and a date (prices are not live).
  3. ADR-330 (28), corrected by Lane TC: Add to Paper on a new unsaved shape and cancel (do not Confirm): there is **no tick box** after the close; the Price box is empty for a draft with no planned entry (hint "Enter a price in steps of 0.05"). The tick-box form ("Prices are not live; the entry is the last captured price, as of HH:MM.") is a market-hours, feed-stopped case: Monday.
  4. (Monday) Type your own entry price for one leg with prices not live: the tick box still shows; tick it and press Confirm: the typed price is the entry.
- **Expected:**
  - NEW-T02: "'Paper P&L paused - prices not live, as of <date>, <time> IST' with the time of the last price."
  - D-37: the what-if Target and Date readouts say "not shown while prices are not live" beside the dash.
  - ADR-330 (28) (weekend, Lane TC): no tick box after the close; the server's market-closed sentence "The market is closed. Orders can be placed once it opens." appears only on Confirm (W-33). The tick-box wording is Monday's.
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T1-21 The API is stopped for a few seconds: Exit goes grey and the page closes the dialog by itself, nothing staged is wrongly kept
- **Proves:** with the API down Exit is grey with a reason line, every list shows "-" and then comes back; nothing staged is wrongly kept.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "API stopped 15:16 to ~15:20:30. Grey button and reason line pass ('Prices are not live; try again when they update'); builder opened empty; s1 not checked (reload cleared tick), s3 and round 3 not checked (need API stop inside a dialog; only one 3-minute stop window)."
- **Fix carried first:** R1 (Lane U hotfix/index-quote-1127 head f61f7935, in the commit; the 'as of' time on tick text: no fix lane named)
- **Needs:** market closed OK for the grey-button and outage-list steps; MONDAY ONLY: steps 3 and 5 (Exit dialog open while the API stops), because after hours the server refuses exits, so no dialog confirms.
- **Steps:**
  1. Positions > Paper: tick one leg of a running trade; "Exit (1)" is blue (s1; the 27 Nov reload cleared the tick, so do not reload).
  2. Stop the API for a few seconds. Read the Exit button and the reason line.
  3. MONDAY ONLY: Start the API, tick a leg, click Exit; while the dialog checks, stop the API. (s3)
  4. Tick a leg, click Exit, press Cancel yourself.
  5. MONDAY ONLY: Exit path round 3 in the builder of a running paper trade (per-leg Exit, lot change, API stopped with the dialog open).
  6. Stop the API for a few seconds: look at the legs table, the P&L Table, the Full table and the Paper P&L panel rows. Then start the API and look again. (Also in this window do the T3-10 outage checks.)
- **Expected:**
  - "'Exit (1)' turns grey (dimmed, no-entry cursor) with the reason line."
  - "the tick stays ('Exit (1)')" after your own Cancel.
  - "the legs table, the P&L Table, the Full table and the Paper P&L panel rows all show '-'; restore: all come back." (D-N07 remainder: with the API down the P&L Table tab "shows an error block"; ADR-330 (29) says that stays: see T3-10.)
  - MONDAY ONLY items: "the dialog closes by itself and the tick is cleared ('Exit (0)') once prices are back."; round 3: "the dialog closes by itself and '2 pending changes' remain (your kept exit and your lot change); only the third leg's exit is gone."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T1-14 The builder's money figures: charges basis, booked P&L, closed legs, the average exit
- **Proves:** the 0DTE max/profit-left figures (D-14) and the re-buy of a closed contract (#725, #741 follow-up) show the right rows and totals.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "Most steps pass; D-11 table total not visibly changing." Not run: D-14 and re-buy steps.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** MONDAY ONLY: the unrun steps need a trade expiring today (D-14) and closing a leg then buying the same contract again (#725, #741 follow-up); after hours the server refuses exits.
- **Steps:** none (MONDAY ONLY).
- **Expected:** none (MONDAY ONLY).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T1-16 The Paper total line: "Includes N closed strategies." and the left-out line
- **Round 2 correction (PC round 1, 28 Nov):** **MONDAY** (needs exactly one unpriced trade; the PC has 9 unpriced, so the singular "1 strategy left out: its price is not live." cannot be shown on the weekend). Round 1 saw "Includes 17 closed strategies." and "9 strategies left out: their prices are not live.", matching on Home and Positions.
- **Proves:** the Paper total line names its closed strategies and, when a trade has no price, says it was left out.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "'Includes N closed strategies.' confirmed; the left-out line never arose." Not run: left-out line wording.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK (look for a trade with no live price; after a weekend or a restart some trades may read "no price"; if none does, write that no trade was left out)
- **Steps:**
  1. Positions > Paper with at least one closed paper trade. Look under the total for the left-out line (shown only if a trade has no live price). Add up the rows shown and compare with the total.
- **Expected:** "If a trade has no live price, the left-out line '1 strategy left out: its price is not live.' is shown too, and the total adds up to the rows it shows."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T1-18 Settlement rows of a settled trade (SENSEX trade 173 on the PC) and the stored settlement text
- **Proves:** a settled trade's builder shows its closed legs and result, not an empty builder.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Settlement text and closed legs pass; right pane still says 'Add a leg to start one' on a settled trade." (No unrun steps; the failing item is step 2.)
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. N-48: Open the builder of trade 173 (SENSEX settled trade). Look at the right pane: no "No legs yet", no Add leg; the closed legs and "Closed: result" show. Write the exact text the pane shows.
- **Expected:** "no 'No legs yet', no Add leg; the closed legs and 'Closed: result' show." If trade 173 is gone: NOT CHECKED (no settled trade on the PC).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T2-06 The builder re-check after the merge (Greeks tab)
- **Proves:** the builder's Greeks tab shows for a saved paper trade.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Payoff, live P&L and leave question pass." Not run: Greeks tab not opened.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. Open a saved paper trade in the builder.
  2. Open the Greeks tab and read it.
- **Expected:** "the payoff, Greeks and live P&L show" (Greeks tab text beyond this: expected text not in the old plan: tester writes it as an observation).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T2-09 Bulk delete, the result line, and Undo (dismiss, 30 s hold)
- **Proves:** the "deleted" result line stays 30 seconds and Dismiss removes it.
- **Type:** User experience
- **27 Nov result:** PARTIAL: "Delete, result line and Undo pass, including a running trade." Not run: Dismiss, 30 s hold.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. My Strategies: save two throw-away drafts (e.g. "UNDOTEST-1", "UNDOTEST-2"); search UNDOTEST; tick both; Delete selected; Delete.
  2. Wait 30 seconds and look at the result line. Do not touch it.
  3. Click Dismiss on the line.
  4. Delete one more draft by its own Delete; read the line; click Dismiss.
- **Expected:** "the line '2 deleted.' stays with 'Undo' and 'Dismiss' beside it; wait 30 seconds: still there." Own Delete: "the line '1 deleted.' (or the server's summary) with Undo stays too; Dismiss removes it."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T2-17 Lists: the status word, current legs, and the figures of a closed row
- **Round 2 correction (PC round 1, 28 Nov):** The Completed screen is at **`/strategies/completed-strategies`**, not My Strategies (My Strategies lists only Draft and Running). Compare it with Positions > closed: both counted 17 in round 1.
- **Proves:** a closed row shows the same figures on every screen that lists it.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Closed-row figures consistent on Completed Strategies only; no cross-screen compare possible; counts 14 versus 15 unexplained." Not run: cross-screen compare.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK (a closed row's figures are fixed)
- **Steps:**
  1. D-42: My Strategies: find a closed trade (e.g. a closed condor); it is listed as Completed. Write down its figures.
  2. Find the same trade on the other screens that list it (Positions > Paper closed rows, Completed list) and write down its figures there; compare them with step 1. Also write the count of closed trades shown on each screen. (The old plan has no separate cross-screen step: tester writes the comparison as an observation.)
- **Expected:** "as quoted": "My Strategies: a rolled condor shows its current legs; closed C4 listed as Completed". Figures of one closed row equal on every screen (expected figures not in the old plan: tester writes them as an observation).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T2-19 Reset to playbook (ADR-330 (9), (32)) (reset markers)
- **Proves:** after "Reset to playbook" the changed and switched-off markers show.
- **Type:** Screen
- **27 Nov result:** FAIL: "Reset sentence and kept values match, but the changed and switched-off markers are not shown."
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. Take a plan saved from a playbook: switch one condition off, type a Rs 400 stop and a 15:15 time exit, Save.
  2. Open the plan sheet > Edit > "Reset to playbook"; read the confirmation; Confirm.
  3. Look for the changed / switched-off markers.
- **Expected:** "one confirmation says the typed levels stay; Confirm: the condition is on again, the Rs 400 stop and 15:15 stay, the changed / switched-off markers show."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T2-21 The Strategy Chart on a running paper trade (D-51, ADR-203, ADR-330 (43))
- **Proves:** with no open legs the chart tab says so, and with the switch off it answers 409.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "Chart line drawn with HTTP 200." Not run: no-open-legs sentence, switch-off 409 text.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** MONDAY ONLY: the no-open-legs sentence needs the remaining legs exited one by one (after hours the server refuses exits), and the 409 text needs the switch lines turned off after that.
- **Steps:** none (MONDAY ONLY).
- **Expected:** none (MONDAY ONLY).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-01 The leave question and the reload line
- **Proves:** the reload line "goes after Save".
- **Type:** User experience
- **27 Nov result:** PARTIAL: "Wording and reload line pass." Not run: "line goes after Save".
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. Builder: add two legs (unsaved). Read the line under the bar.
  2. Press Save. Check that the line goes.
  3. A running paper trade with one pending change shows the line too.
- **Expected:** "Unsaved legs are not kept if you reload or close this page. Save to keep them." After Save the line goes.
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-06 The phone-width drawer
- **Proves:** at phone width the leg drawer fills the screen and returns to the editor.
- **Type:** Screen
- **27 Nov result:** NOT CHECKED: "Phone width cannot be set in this browser ('resize_window does not change the page width')."
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. In Chrome press F12 to open DevTools, then click the device toolbar button (or Ctrl+Shift+M), pick a phone (width under 640 px), reload.
  2. Open the builder and click Add/Edit.
  3. Look at the drawer and its header row; click "Show Editor".
- **Expected:** "the drawer fills the screen and its own header row carries 'Show Editor'; it returns to the editor. On a PC the tab stays on the drawer's edge."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-09 Rename can be cancelled with Esc; a dismissed outcome reads as two words
- **Round 2 correction (PC round 1, 28 Nov):** First dismiss one adjustment opportunity **with a reason chosen** (round 1's row read "You dismissed this at 27 Nov 2026, 13:32:23 IST" with no reason word); then read the outcome and the reason as two separate words.
- **Proves:** a dismissed opportunity reads "You dismissed this" and its reason as separate words.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Rename Esc passes." Not run: dismissed-outcome part (no dismissed opportunity exists).
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK (if no dismissed opportunity exists, dismiss one first if an opportunity is listed; otherwise write that none exists)
- **Steps:**
  1. Positions > Adjustment opportunities: find a dismissed opportunity and read it.
- **Expected:** "a dismissed opportunity reads 'You dismissed this' and its reason as separate words (a screen reader pauses between them)."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-10 The API is stopped: every list shows its failure message with Retry
- **Proves:** with the API down every list shows its failure message with Retry and comes back.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "API stopped: My Strategies 'Could not load your strategies. Nothing was changed.' with Retry (correct); builder 'The page could not get an answer from the server.' but no 'P&L Table' tab." Not run: other lists, reload during outage, Retry press, Current positions / Adjustment opportunities, D-N07 part.
- **Fix carried first:** R1 (Lane U hotfix/index-quote-1127 head f61f7935, in the commit; the 'as of' time on tick text: no fix lane named)
- **Needs:** market closed OK (the API is stopped on purpose)
- **Steps:**
  1. Stop the API while the frontend still serves.
  2. Open My Strategies, Current positions and Positions > Adjustment opportunities; read each.
  3. S-05: Reload My Strategies while the API is stopped.
  4. D-N07 (ADR-330 (29)): open the builder's "P&L Table" tab.
  5. Start the API again and press Retry on each list: the lists come back.
- **Expected:** "each shows its failure message with Retry, never 'You have no saved strategies yet', an empty inbox 'Showing 0-0 of 0 rows', a blank Real section, or 'not connected'." S-05: "grey placeholder rows while it loads, never a bare 'Loading...'. If the read fails: 'Could not load your strategies. Nothing was changed.' with Retry." D-N07: "The error block 'The page could not get an answer from the server' stays; it shows no number" (ADR-330 (29)).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-12 Dates and clocks: the one date style and the 24-hour clock (D-57, D-65)
- **Proves:** one date style and 24-hour clock everywhere (D-57) and a builder rename saves (D-65).
- **Type:** Screen
- **27 Nov result:** PARTIAL: "D-66 and D-53 pass." Not run: D-57, D-65.
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK
- **Steps:**
  1. D-57: Look at the Adjustments page dates, the disconnect banner "Last updated: HH:MM:SS IST" (shows when no feed), and the market-closed line "Prices are from HH:MM:SS IST."
  2. D-65: Rename a paper trade from the builder; then look at My Strategies: its status matches.
- **Expected:** D-57 "One date formatter ('23 Nov 2026', 24-hour IST) on every screen"; D-65 the rename saves without an error.
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-13 Wording, labels and the "View" button
- **Proves:** the wording of the builder hint, playbook delete and the price-zero sentences (D-52, D-54, D-58).
- **Type:** User experience
- **27 Nov result:** PARTIAL: "Label ADR-330 (30) passes." Not run: D-52, D-54, D-58 (in latest pull).
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK
- **Steps:**
  1. D-52: Empty builder hint with the feature off and on.
  2. D-54: Adjustments > Playbooks > own playbook: Delete, Cancel, Delete; look for a Test button.
  3. D-58: C2 opportunity line, C9/C6 drawer reasons, Stops form Above=0, an ADJ-02-type rule line with the side.
- **Expected:** D-54 "Delete asks 'Delete this playbook?' (Cancel keeps it); the dead Test button is removed"; D-58 "Zero price: 'A price of 0 cannot be used. Enter 0.05 or more'". D-52 hint text, and the C2 / C9 / C6 / ADJ-02 wording: expected text not in the old plan: tester writes it as an observation.
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-15 Delete and Undo leave "Deleted" and "Restored" entries in the history (ADR-330 (31))
- **Proves:** a 3-row bulk delete and Undo leaves "Deleted" and "Restored" in each history.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "Single and one-row bulk delete with Undo pass (builder error blocked the rest)." Not run: 3-row bulk, History entries.
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK
- **Steps:**
  1. My Strategies: tick 3 draft rows, Delete selected, Delete, then Undo.
  2. Open the history of each of the 3 strategies; also of a single deleted-then-undone draft.
- **Expected:** "two entries 'Deleted' and 'Restored', each with its time, and no Restore button on either." "each of the 3 histories has one 'Deleted' and one 'Restored'."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T3-17 Lane D's screen re-tests: create-strategy error box, closed-leg stop sentence, a deleted strategy's plan, the chain's day count
- **Proves:** #745, #749 and T-Q7 show as expected.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Deleted trade plan hidden and link says 'not found'." Not run: #745, #749, T-Q7 in latest pull.
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK
- **Steps:**
  1. #745: Create Strategy > Guided > "I already know my strategy" > NIFTY.
  2. #749: Open a paper trade with a leg closed by a stop-loss.
  3. T-Q7: Market > Option Chain: read the "N days left" and compare with the server's count (plain look only; no clock change).
- **Expected:** #745 "no red 'took too long' box above a list that loaded." #749 "the closed-leg table's stop-loss sentence sits on its own full-width line under the row, not squeezed into the Exit column." T-Q7: "'N days left' still matches the server's count" (further text: expected text not in the old plan: tester writes it as an observation).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T4-01 Number tables: columns visibly separate (closed rows, Live card leg table)
- **Proves:** every number column is separate under its own header.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Orderbook Lots, payoff and Greeks tables pass." Not run: closed rows, Live card leg table.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. Open a placed paper strategy in the builder; check the closed rows in the net positions table.
  2. Then look at a Live card's leg table.
- **Expected:** "every number column (e.g. Qty 65 and Price 101.20) is visibly separate and sits under its own header."
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T4-03 Strategy name width (compact paper list, builder card)
- **Round 2 correction (PC round 1, 28 Nov):** The long-name fixtures C5 to C9 do not exist on the PC: first rename five paper trades to names of 20 characters or more (Rename on My Strategies), then read the compact paper list and the builder card: no name cut off.
- **Proves:** names are not cut on the compact paper list and the builder card.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "My Strategies names pass." Not run: compact paper list, builder card.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. At desktop width open the compact paper list and read the names (C5 to C9).
  2. Open the builder card and read the name.
- **Expected:** "Name column has a 9.5rem floor (one shared class) on My Strategies, the compact paper list and the builder card" (the names are not cut).
- **Write down:** build head, screen text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### T4-04 Stops form and list side by side (Save-scroll part)
- **Proves:** after Save the new row is brought into view.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Side-by-side form and list pass." Not run: Save-scroll part.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK
- **Steps:**
  1. Positions > Paper > Stops at 1536 px: Save a new stop and watch the list.
- **Expected:** "Save brings the new row into view" (exact on-screen text: expected text not in the old plan: tester writes it as an observation).
- **Write down:** build head, screen text, time.

## 6. After-close checks and the 9-screen sweep (seed first in round 1, then restart)
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### Lane TC's corrections to the lines below (walk of the round 1 commit 5fc6b102, 28 Nov)

Lane TC (`test/r2-walk-close-1128`) walked these screens in a browser on the round 1 commit with **synthetic closes** (a stored time of 15:29:58 and five seeded strategies) and a harness market with a silent socket, because with no stored Zerodha session the real app builds no market book (defect D-1). So the **text shapes** below carry over to the PC; the figures and the time 15:29:58 do not (the PC's seed carries Friday's 15:30:00-style time). Where a sweep check below says something different from this list, this list wins.

| Where | The old plan line | What the build shows (word for word) |
|---|---|---|
| SW-2 Real P&L | "Real P&L is not shown yet: the server does not price Zerodha positions." | With a Zerodha session: the figure with its read time, for example `+650.00` and `Zerodha, as at 03:30:41 IST`, never added to Paper P&L. With no session (the weekend): `—` and **"Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, check margin and prepare/execute your strategy."** The banner IS mounted on Positions. A red 409 `gate_broker_not_connected` console error on Positions load with no session is known defect D-2. "No open Zerodha positions." only with a session and no open position. |
| SW-6 / T1-20 steps 3 and 4 / AF-08 Add to Paper | a tick box "Prices are not live; the entry is the last captured price, as of HH:MM." | **No tick box**, no "prices are not live" sentence. The dialog's Price box is empty for a draft with no planned entry (hint **"Enter a price in steps of 0.05"**). A Confirm sends once and the server refuses with MARKET_DATA_102: **"The market is closed. Orders can be placed once it opens."** (cancel in SW-6; Confirm only in W-33). The tick-box form is a market-hours, feed-stopped case: Monday. Open owner question (TC D-4): should the dialog say the market is closed before Confirm? |
| SW-3 Exit dialog (one leg ticked, not confirmed) | "Prices are not live; try again when they update" | `Exit Paper positions` with `Price about 147.50, as of 15:29:58, the server sets the exit price when you confirm`; `The app could not check whether this exit leaves a sold option without protection. You can still confirm.`; `This is not a real trade. Paper orders use no real money.`; **`The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.`** Cancel enabled, **Confirm disabled** (the 27 Nov FAIL "Confirm enabled" is fixed). Wording defect D-12: "You can still confirm." beside a disabled Confirm. |
| SW-3 totals and card | "No paper total yet", totals "—" | The priced total is shown; the unpriced strategy is left out (Home count line) with the paused text on its own row: totals strip `Booked P&L (after charges)`, `Unbooked P&L (after charges)`, `Total Decay`, `Charges paid`, `Today (after charges)`; a leg cell `147.50` with `15:29:58` below; an unpriced leg `no price` with `No price for: NIFTY 8 Dec 24350 CE, NIFTY 8 Dec 24350 PE.` |
| SW-4 Live Strategies | "Checked at" time; "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." | There is **no "Checked at" line** on Home, Positions, My Strategies or Live Strategies ("Checked at HH:MM:SS IST" appears only in the builder's paper panel). The card reads `⏸ Monitoring paused`, `Health unknown`, **`Not being watched: no worker has reported in the last 2 minutes.`**, `estimated from spot`, `NIFTY 24187.35` with no "at <time>", an unpriced card `P&L — · Paper P&L paused - prices not live`, a draft `Draft — Live data not connected`. |
| SW-5 My Strategies | | matches: `P&L ... (after charges)`, `P&L — · Paper P&L paused - prices not live`, Completed `closed 27 Nov 2026, 10:45:00 IST`, `Final P&L +520.00 · Charges ₹62.07 · Net after charges +457.93 · Adjustments made 0 · Adjustment cost 0.00`. The compact paper list repeats `Paper P&L paused - prices not live` twice under a paused row (D-11). |
| SW-6 Builder | "As of HH:MM:SS IST" is a price time | `Oldest leg price as of 15:29:58 IST`, each leg `15:29:58`, `Time value at the last close prices, as of 15:29:58`, `Paper P&L (not real): +3,027.52 (after charges)`; **but** `Checked at 03:22:40 IST` and `As of 03:22:36 IST` under the Plan boxes are the **current** time (D-5). A doubled sentence `OI not available for this expiry: OI not available for this expiry: live market data is stale.` under the payoff chart (D-6). `No fixed maximum` overlaps `Intrinsic value` at 1366x768 for a strategy with no fixed maximum loss (D-10). |
| SW-7 Option Chain | "IV and Greeks missing" | `NIFTY 24187.35 as of 15:29:58`; the banner; **"IV and Greeks: estimated from spot (the forward could not be derived from the chain)."**; seeded contracts show the close, every other cell `-`, Change `not available` (only Change says "not available"; plain cells are `-` with no reason sentence). With no session the chain status line reads `NIFTY- live` after the close (D-1). |
| SW-8 Alerts | | matches: Active `No alerts yet. Alerts start when strategy monitoring rules are added.`; History/Records `Stops and expiry settlements` / `No stops or expiry settlements yet.` |
| SW-9 Stops panel | "Data: paused / Data: stale" line | after the close: `NIFTY last 24187.35 as of 15:29:58`, `Paper - exits are recorded in the app, not sent to Zerodha`; **no "Data:" line exists** and no "live" word on Home, Positions, Live Strategies or the builder. |
| SW-0 "an empty cell" | must not show | a closed row on Positions has empty Unbooked and P&L cells (D-8); expect it, write it as known. `NIFTYRunning` and `NIFTYCompleted` run together (D-7). |
| AF-03 mixed banner | "...; 1 leg as of {later}." | did NOT appear in TC's case: one stored 15:58:00 row makes the builder read `Market closed. Prices are from 27 Nov 2026, 15:58:00 IST.` (a snapshot after the close keeps its own later time; not judged a defect). The live-feed-past-15:30 case is blocked on a weekend. |
| AF-07 Real total, Zerodha disconnected | "no old figure stays" | after a reload yes (`—` and the Connect sentence); on an open page the figure `+650.00` stays more than 70 s after the disconnect (D-13): write "reload needed". |

**Known defects of the round 1 commit (Lane TC; write them as "known", not new):** D-1 no stored Zerodha session means no stored close reaches any screen (the real weekend app may show "Not available" for the indexes and `NIFTY- live` on the chain); D-2 a red 409 on Positions load with no session; D-4 the Add to Paper wording versus the route's refusal; D-5 "Checked at" and "As of" under the builder's Plan boxes show the current time; D-6 the doubled OI sentence; D-7 `NIFTYRunning` run together; D-8 empty cells on a closed Positions row; D-10 `No fixed maximum` overlaps `Intrinsic value`; D-11 the paused text twice in the compact list; D-12 "You can still confirm." beside a disabled Confirm; D-13 an open Positions page keeps the old Real figure.


(AF-01, AF-02, AF-08 and AX-05 of 27 Nov are now W-33, Lane N's nine-screen walk, which has the new expected texts; the freeze across 15:30 is Monday.)

# Weekend re-run checks (no live feed): AF-01 to AF-08, AX-05, AX-14, sweep SW-0 to SW-9

Sources: test-plan-2026-11-27.md section 3 (AF-nn), test-plan-2026-11-27-addendum.md (AX-05, AX-14, 2.2 sweep), PC results results-722.md.
Weekend rule for every check: the market is closed and the price feed is already stopped, so do not "stop the feed". Wherever a source says "after 15:30", the weekend app is already in that state; the label date will be the last trading day's date, not 27 Nov.
Where a source has no exact text, the line says "expected text not in the sources: tester writes it as an observation".

---
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-03 The mixed trade's banner time (open owner question LR-Q18)
- **Proves:** what banner time a mixed trade shows (ADR-330 (36) mixed case). Data, not PASS or FAIL.
- **Type:** Screen
- **27 Nov result:** DATA: "The new 25700 PE leg read 'Close, 27 Nov 2026, 15:30:00 IST', so no mixed-time case could be reproduced."
- **Fix carried first:** R1 (Lane N fix/last-close-1127, in the commit; replaced by W-33)
- **Steps:**
  1. After AF-02's restart is NOT needed; do this before it if possible. Take a builder that held its legs through the close.
  2. Add a new strike (one leg of the other kind, priced for the first time after the close).
  3. Note the banner time and each leg's time.
- **Expected:** "it follows the open question LR-Q18": there is no expected text; write the banner time and each leg's time. If it appears, the server sentence for a mixed trade (from AX-05) is "Market closed. Prices are from {frozen}; 1 leg as of {later}." or "Market closed. Prices are from {frozen}; {count} legs as of {later}." On the weekend with no feed a new strike may have no price at all: write what the leg shows (expected text not in the sources: tester writes it as an observation).
- **Write down:** build head, banner text, each leg's time, time of the check.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-04 Home's Total P&L with one settled or unpriced trade: sum of the priced trades plus a count line
- **Proves:** ADR-330 (35); AC-R06 (FAILED on 26 Nov); N-46.
- **Type:** Screen
- **27 Nov result:** DATA: "Home read 'Market closed. Prices are from 27 Nov 2026, 15:30:00 IST.'; no unpriced trade existed, so the excluded-trade case could not be shown." (Later sweep, after the restart: Home Total P&L "—" with "Paper P&L paused - prices not live".)
- **Fix carried first:** R1 (Lane N fix/last-close-1127, in the commit; replaced by W-33)
- **Steps:**
  1. With one settled or unpriced trade present (after a restart all 9 trades may be unpriced, which is also worth writing down), open Home.
  2. Read "Total P&L" and the count line.
  3. Open My Strategies and read each row's P&L; add the priced rows yourself.
- **Expected:** "Home's 'Total P&L' shows a figure over the trades that can be priced, with the count line, and equals the sum of those rows on My Strategies." The count line reads like "1 strategy left out: its price is not live." (26 Nov figures: rows #185 -214.23, #184 +1,387.51, #172 +15,338.05, #171 -802.86, #170 +67.33, #173 "—"; Home "Total P&L —".)
- **Write down:** build head, Home Total P&L text, count line, each My Strategies row figure, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-05 Home against the My Strategies rows, same minute, prices frozen
- **Proves:** R-06 step 5; whether the two totals agree.
- **Type:** Screen
- **27 Nov result:** PASS: "Home and Positions totals agree; running rows plus closed trades reconcile; gap to My Strategies is exactly the closed trades."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:**
  1. "(Not part of this fix: the gap against My Strategies is not proven wrong; check it after 15:30 when prices stop.)" On the weekend prices are already stopped.
  2. Read Home's total and the My Strategies rows within one minute.
- **Expected:** the two agree; write both numbers and both times.
- **Write down:** build head, Home total, My Strategies row figures, both times.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-06 No "No price for:" line above a priced table (N-44)
- **Proves:** N-44.
- **Type:** Screen
- **27 Nov result:** PASS: "Builder banner 'Market closed. Prices are from 27 Nov 2026, 15:30:00 IST.' and legs 15:30:00; no 'No price for:' line above a priced table."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:**
  1. Open the builder of a running paper trade.
  2. Look at the Paper P&L panel when every leg shows a price. (If the API was restarted and legs show "no price", this check cannot be run: write that.)
- **Expected:** "no 'No price for: ...' line when every leg shows a price."
- **Write down:** build head, banner text, leg times, whether the line appeared, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AX-14 Plan watch box rows, market closed: Paused / Not checked with the server's text
- **Proves:** the Plan watch box shows trigger rows with a state word and the server's reason (Step 3 stand-alone checks).
- **Type:** Screen
- **27 Nov result:** FAIL: "Plan watch box never shows trigger rows or state words; ends 'not available right now'." (T2-01 FAIL: builder box never shows rows within 60 s and ends "not available"; T2-02 FAIL: Positions 0 of 10 boxes filled within 60 s.)
- **Fix carried first:** R1 (Lane R hotfix/plan-save-1127 head 8b45807a; Lane R2 hotfix/plan-read-1127 1d0f56e7 and Lane R3: in the commit)
- **Steps:**
  1. Open the "Plan watch" box in the builder (beside the live P&L) of a strategy that has a plan, and on each open Positions paper row.
  2. Wait up to 60 s (the PC saw answers take 15-20 s). Read each trigger row's state word.
  3. Market closed: look for "Paused" and "Not checked" and read the server's sentence beside it. "Not checked" cannot be forced by clicking (it needs a missing price or level): if it does not appear, NOT CHECKED (reason: cannot be forced).
- **Expected:** each trigger row shows a state word from "Watching" (NotMet), "Fired" (Met), "Not applicable", "Not checked" (NotComputable), "Paused". For "Not checked" the server's reason sentence, for example "This rule is not checked now; it never counts as passed.", "This trigger is not checked in this version." or "This rule is not checked in this stage."; an absent figure shows a dash and the reason, never 0; empty box "Nothing to watch yet."; no plan "No plan: nothing is watched for this strategy". There is no row text "checked, not met" in the source.
- **Write down:** build head, each row's state word and sentence, how many seconds until the box filled (or the "not available right now" text), time.

---
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### Sweep: pre-open-data sweep (feed absent; judged against ADR-212 and REQ-049 AC-4)
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-0 Restart first, then the rule and the "Must not show" list
- **Proves:** with the API restarted and no feed, no screen presents a stale or missing number as live.
- **Type:** Functionality
- **27 Nov result:** the 27 Nov sweep ran after an API restart (15:53) with the feed stopped (15:58:00): Home banner "Market closed. Prices are from 27 Nov 2026, 15:58:01 IST." with Total P&L "—" and "Paper P&L paused - prices not live" (FAIL); Positions Paper all 9 trades "no price", Exit dialog opens with enabled Confirm (FAIL); Live Strategies "Checked at 27 Nov 2026, 16:07:45 IST" moves while banner is fixed (FAIL). Full row list is under SW-1 to SW-9 below.
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:**
  1. Restart the API. Write down the restart time. The feed is already stopped (weekend).
  2. Open Chrome DevTools > Console and keep it open; any red error on a screen below is a fail.
  3. Run SW-1 to SW-9 in order.
- **The rule in plain words:** after the close, with the feed stopped, the app must NOT show a stale number as if it were live (REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."). The paper screens show each open leg's LTP, unbooked P&L, strategy totals and decay from the last close the feed holds, under the one market-closed banner (ADR-212, ADR-177); a contract with no held close stays unpriced with its reason ("no price" or a dash), never a default, 0 or blank; a paper entry, exit or fill stays refused. Note: a restart can lose the held close (the AF-02 defect); if so, the 27 Nov expectation of "no price" is the failing behaviour, not the pass.
- **Must not show on any screen:** "undefined", "NaN", "null", "[object Object]", a raw error or stack trace, an empty cell, "0" or "₹0" or "0.00" standing in for a missing price, a time that is the page-load time instead of the price time, the words "live" or "Data: live" or "Index values are live." next to a closing price, and any English that is not in the quoted strings.
- **Expected:** see each SW check.
- **Write down:** build head, API restart time, DevTools console errors (text), time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-1 Home (`/home/overview`)
- **Proves:** index strip, banner and the three figures are honest after the close.
- **Type:** Screen
- **27 Nov result:** FAIL: Home banner "Market closed. Prices are from 27 Nov 2026, 15:58:01 IST." with Total P&L "—" and "Paper P&L paused - prices not live".
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Home and wait about 10 s. 2. Read the index strip (NIFTY 50, SENSEX): the banner line, each value, the small time beside it. 3. Read the three figures "Running strategies", "Unread alerts", "Total P&L". 4. Reload once and read again.
- **Expected:** banner "Market closed. Prices are from <HH:MM:SS>." with the time about 15:29 to 15:30 IST (the price's own time); with no usable time "Market closed." alone, never "Prices are from Time not available."; a missing index value "Not available"; socket dropped "Reconnecting - prices as of <time>" or "Live prices are reconnecting"; labels "Running strategies" / "Unread alerts" / "Total P&L"; Total P&L is the server's after-charges text with "(after charges)", or a "—" dash with "Paper P&L paused - prices not live" or "Paper P&L is not available right now."; a failed read of one figure "Could not be read right now." in that figure only. Also must not show: an index value with no banner and no time, a value labelled live, "Index values are live." after the close, Total P&L as "0", "-0" or "undefined", the page-load time in the banner.
- **Write down:** build head, banner text, index values and times, the three figures, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-2 Positions, Real part (filter "Real", then "All")
- **Proves:** no invented Real number (ADR-016); empty state wording.
- **Type:** Screen
- **27 Nov result:** PARTIAL: Positions Real "No open Zerodha positions." with no banner.
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Positions; click "Real", then "All". 2. Read the "Real P&L" total and each Zerodha position row (Contract, "Your units", P&L). 3. With no Zerodha position open, read the empty state. 4. Reload.
- **Expected (corrected by Lane TC):** with a Zerodha session: "Real P&L" shows the server's figure with its read time ("Zerodha, as at HH:MM:SS IST", for example `+650.00`), never added to Paper P&L (two separate cards). With no session (the weekend): `—` with **"Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, check margin and prepare/execute your strategy."**; the old line "Real P&L is not shown yet: the server does not price Zerodha positions." must be GONE. "No open Zerodha positions." is expected only with a session and no open position. The "Market closed. Prices are from <time>." banner IS mounted on Positions (if absent, record a finding). A red 409 `gate_broker_not_connected` console error on Positions load with no session is known defect D-2: write it as known. Must not show: a Real P&L number the server did not send, Real and Paper totals added together.
- **Write down:** build head, total text, empty state text, banner present or not, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-3 Positions, Paper part (filter "Paper")
- **Proves:** paper screens show the last close with its banner; no fill after hours.
- **Type:** Screen
- **27 Nov result:** FAIL: Positions Paper all 9 trades "no price", Exit dialog opens with enabled Confirm.
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Positions > "Paper". 2. Read the totals strip ("Paper P&L" and its charges tap). 3. On one open paper strategy read its card: Total P&L, Booked, Unbooked, Total Decay, Greeks, each leg row (LTP, unbooked, or "no price"). 4. Tick "Show closed positions" and read the closed legs. 5. Open the charges tap. 6. Try Exit on an open strategy and read the refusal; do not confirm anything. 7. Reload.
- **Expected:** banner "Market closed. Prices are from <time>." (not mounted in PaperStrategies by the source read: record if missing); a leg with no held close: cell "no price" and "No price for: {legs}." or "Expired contracts have no price: {legs}.", totals "—" with the reason; paused totals only if a leg is unpriced or the list read failed: "Paper P&L paused - prices not live" and "No paper total yet: prices are not live"; a leg expiring today still open after 15:30: "Market closed. Open legs that expire today settle at HH:MM."; missing Greeks or decay "—" with the reason; Exit refusal "Prices are not live; try again when they update"; charges labels "Before charges", "Charges paid", "Estimated charges to close", "After charges". Must not show: a dash for LTP, Unbooked or Total when the legs did have a close, "Paper P&L paused - prices not live" instead of close figures for legs that have a close, a leg price with no banner or time, an unpriced leg as "0" or blank, an Exit that places a fill (27 Nov: Exit dialog Confirm stayed enabled).
- **Write down:** build head, banner text, card figures, leg cell texts, Exit dialog text and whether Confirm was enabled, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-4 Live Strategies
- **Proves:** one banner, honest paused state, fixed time while no feed.
- **Type:** Screen
- **27 Nov result:** FAIL: "Live Strategies 'Checked at 27 Nov 2026, 16:07:45 IST' moves while banner is fixed."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Live Strategies. 2. Read the one banner at the top and confirm there is exactly one, not one per card. 3. For each running paper card read the "P&L" line, the "Checked at" time, the badge "⏸ Monitoring paused" and the dot "Health unknown" (if shown), the status label, the spot line, Max Profit / Max Loss, each leg's LTP. 4. Open the "Stops" and "Exit" links on a card; they only open pages. 5. Wait 60 s for a socket drop or reconnect line.
- **Expected:** page banner "Market closed. Prices are from <time>."; card P&L "P&L <figure> (after charges)", paused "P&L —" with "Paper P&L paused - prices not live", read failed "P&L —" with "Paper P&L is not available right now."; "⏸ Monitoring paused", "Health unknown"; no live answer "Draft — Live data not connected"; a leg no longer live "This leg is no longer a live contract (expired, delisted, or its exchange token now belongs to another contract). It is not priced."; under a paused card "No numbers are shown as live for this strategy."; status "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused."; reconnect "Reconnecting - prices as of <HH:MM:SS>"; nothing running "Nothing is running."; "Waiting for the first answer..."; "Loading next..."; the spot line has no "at <time>" after the close; per-leg health words are not shown while the market is closed. Must not show: several banners, "Prices are from" with the load time, figures shown as live while the badge says paused, LTP "0", "-" with no reason on a leg that has a close, a blank card, "Loading this strategy..." that never ends, the legs' health words after the close.
- **Write down:** build head, banner text and count, "Checked at" time on two reads a minute apart, badge and dot text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-5 My Strategies (and the Completed tab)
- **Proves:** row P&L is the close figure or a dash with a reason, never 0.
- **Type:** Screen
- **27 Nov result:** PARTIAL: My Strategies running rows "P&L — · Paper P&L paused - prices not live".
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open My Strategies and the Completed tab. 2. For each running row read the P&L line and the "last saved <time>" text. 3. On Completed read "Final P&L", "Charges", "Net after charges", "Adjustments made", "Adjustment cost" and "closed <time>". 4. Reload.
- **Expected:** "P&L <figure> (after charges)", or "P&L —" with "Paper P&L paused - prices not live" or "Paper P&L is not available right now."; Completed "closed <time>" or "closed: time not available"; "Charges not available: <reason>" and "not available: <reason>" for net; read failed "Could not load your strategies. Nothing was changed." with Retry; status words only "Draft", "Running", "Completed" or "Status not available". Must not show: "Final P&L undefined", "Charges 0" for an unreadable charge, a Running row with a number and no label, "last saved Time not available" (report it as a defect).
- **Write down:** build head, each row's P&L line and saved time, Completed figures, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-6 Builder of a running paper trade (My Strategies or Live Strategies > the trade)
- **Proves:** the builder works from the last close under the banner with the entry labelled.
- **Type:** Screen
- **27 Nov result:** FAIL: Builder #209 "Rule not checked: No adjustment opportunity checked: prices stale or missing." x17 (and 15:55 observation: paper panel "as of Time not available" beside "As of 15:55:37 IST").
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open the builder of a Running paper strategy. 2. Read the banner under the header, the index level card, the paper panel (Total, per-leg figures, Booked/Unbooked), the legs table LTP column, the "As of HH:MM:SS IST" line and the Orderbook. 3. Read At Expiry / Estimated Now, Greeks and IV tiles. 4. Try "Add to Paper", then cancel without confirming. 5. Read the Exit control's reason.
- **Expected:** banner "Market closed. Prices are from <time>." or for legs priced only after the close "Market closed. Prices are from {frozen}; 1 leg as of {later}." / "...; {count} legs as of {later}."; paper panel "As of HH:MM:SS IST"; leg expiring today "Market closed. Open legs that expire today settle at HH:MM."; unpriced leg "Paper P&L paused - prices not live, as of <time>" and "no price"; money-time labels "at the last close prices, as of {time}" or "at the last close prices", never the live forms; Add to Paper (corrected by Lane TC; cancel, do not Confirm): **no tick box**; the Price box is empty for a draft with no planned entry (hint "Enter a price in steps of 0.05"); the server refuses a Confirm with "The market is closed. Orders can be placed once it opens." (MARKET_DATA_102); targets "not shown while prices are not live" beside "-"; level card with no index price "—"; Exit "Prices are not live; try again when they update". Must not show: the live form of a money-time label after the close, an entry price without a close label and time, a "price has moved" marker driven by a closing price, a live-looking Estimated Now, a made-up number for an unpriced leg, a successful paper fill.
- **Write down:** build head, banner text, panel "As of" text, Add to Paper dialog text, Exit reason, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-7 Option Chain
- **Proves:** chain shows the closed-market banner and last prices, no live wording.
- **Type:** Screen
- **27 Nov result:** FAIL: "Option Chain every strike LTP '- not available'."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Option Chain; NIFTY, nearest expiry. 2. Read the spot, "as of <time>", the banner, any health text, a strip of rows around the ATM, the IV and Greeks columns. 3. Hover a blank cell for its title text. 4. Switch to SENSEX and to a far expiry; tick two contracts and read the Add controls. 5. Look for rows marked "Currently unavailable on Zerodha".
- **Expected:** ADR-177 example: on a Saturday the chain reads "Market closed. Prices are from 15:29:58." and the broker status reads market closed, never "reconnecting". Banner "Market closed. Prices are from <time>."; spot with "as of <time>", no spot-health sentence while closed; no "live" word on the socket status; no data yet "Waiting for live data."; "Option chain unavailable: not connected to live data."; "The underlying price is missing, so no strikes can be chosen yet." or "The underlying price is missing right now: option prices are shown, but the ATM strike, moneyness, IV and Greeks are not."; "This expiry is not in the catalogue.", "The catalogue lists no options for this expiry.", "The catalogue could not be read.", "The expiries could not be read, so no chain is shown.", "No strikes match the filters."; missing cell "-", Change / OI Change missing "not available"; "Currently unavailable on Zerodha" and "Some contracts are currently unavailable on Zerodha and cannot be added." Must not show: a "Stale" / "Delayed" / "Unhealthy" word on every closed cell, "live" socket text, an empty chain with no sentence, bid/ask 0 as "₹0", a different time per row in place of the banner time, "undefined" or "NaN" in IV/Greeks.
- **Write down:** build head, banner text, spot and "as of" time, cell texts seen, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-8 Alerts (Active, History, and the block "Stops and expiry settlements")
- **Proves:** no alert fires silently from a closing price; honest empty and paused lines.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Alerts History 'The page could not get an answer from the server.' above 11 records."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Alerts > Active and Alerts > History; the Records list is the block **"Stops and expiry settlements" on History** (there is no Records page: `/alerts/records` is "Page not found"). 2. For each fired row read the "fired" line and the "no longer true" line and any data-health text. 3. Open notification settings and read the empty line. 4. If a "side closed" alert exists open its "Add the legs again" confirm and read it; do not confirm. 5. Confirm no new alert fired at or after 15:30 because of the closing prices.
- **Expected:** empty Active/History "No alerts yet. Alerts start when strategy monitoring rules are added."; empty Records "No stops or expiry settlements yet."; notification settings "No notification channels are set up yet."; paused "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused."; market-closed variant "Market closed. Prices are from {time}." with "Prices on screen are the last ones before the close; none are arriving, as expected." (line from a grep context in the source: verify); expiry settlement record "Paper - settled at expiry"; alert rows show the server's fired and "no longer true" lines and answer buttons as sent. Must not show: a stop or target alert that fired from the closing price after 15:30 with no data-health text, a fired alert with no data-health line, "Live data: live" on a closed market, a blank Records list with no empty line, "undefined" in a row title.
- **Write down:** build head, History/Records texts, any error text, time.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### SW-9 Stops panel (inside Positions > Paper, `?tab=paper&strategy=<id>`; the Live Strategies "Stops" link opens it; it is not a separate page)
- **Proves:** index level on the Stops panel carries its own time; no "Data: live" after the close.
- **Type:** Screen
- **27 Nov result:** FAIL: "Stops panel 'Index values unavailable.' while other screens show 25607.20."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Stops for a Running paper strategy. 2. Read the label line, the index line below it, the "Conditional exit" Above/Below boxes, the leg stop rows and the triggers list. 3. Type a level in one leg stop and read its warning text; do not click Save unless a rule under test needs it. 4. Read the reason line next to Save. 5. Look at any trigger row for a data-health word.
- **Expected:** label "Paper - exits are recorded in the app, not sent to Zerodha"; index line live "<NIFTY> now <value> as of <HH:MM:SS>", not live "Index values unavailable."; after the close a value must come with its own time, not the page-load time; saves "Saved: stop <direction> <level>" or "Already set: stop ..."; warnings are the server's warning_text as sent; the reason next to Save is the server's; tracking-panel data line "Data: live" / "Data: stale" / "Data: paused" / "Data: not known": after the close with the feed stopped it must read "Data: paused" or "Data: stale", never "Data: live". Must not show: an index level with no time or with the load time, a stop that reads as armed on live data with "Data: live" after the close, a trigger that fired after the close from a closing price without a data-health word, "undefined" or "null" in the level boxes, a blank index line when the index is not live.
- **Write down:** build head, index line text, data-state line, warning and reason text, time.

---
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### Run LAST
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-07 Zerodha disconnected: the Real total says so and keeps no old figure (run LAST)
- **Proves:** Lane S step 4; ADR-330 (24); Lane D #727, #728.
- **Type:** Functionality
- **27 Nov result:** NOT RUN: "UNKNOWN beyond 'after-close run in progress' (no later verdict seen)."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:**
  1. Run this after everything else. On a weekend there is no Kite login, so there is nothing to disconnect: Zerodha is already not connected. What is possible: reload Positions and read the Real total and the Real part (this is the disconnected state).
  2. "Disconnect Zerodha (or let the session expire), reload Positions." Only if a Kite session exists; on the weekend skip the disconnect itself and write "no Kite login on the weekend".
  3. Lane D #727 / #728, while disconnected: "with prices disconnected (Broker > Disconnect), press Exit on a leg in the Paper P&L panel and on the Orders screen." Press Exit on a leg in the Paper P&L panel and on the Orders screen; do not confirm anything beyond what the dialog needs. On the weekend paper exits are also refused for closed market, so a different refusal than "not connected" may show: write it as seen.
- **Expected:** "the Real total shows a dash and the 'not connected' sentence; no old figure stays." (exact sentence not in the sources: tester writes it as an observation). Exits: "both show the same named 'not connected' line and nothing is stored."
- **Write down:** build head, Real total text, the "not connected" sentence, both Exit texts, time.

---
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### Monday/Tuesday only
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AF-09 Items that need an expiry day
- **Proves:** D-64; D-59; D-12 / D-08.
- **Type:** Functionality
- **27 Nov result:** NOT CHECKED: "No open paper trade expires on 27 Nov 2026; expiries are 1 Dec or 8 Dec."
- **Fix carried first:** none named in the mapping given.
- MONDAY/TUESDAY ONLY: it needs a day on which an open paper trade expires, between 15:30 and 15:45 (D-64: "Market closed. Open legs that expire today settle at 15:45."; D-59: "Stops survive a part settlement at 15:45"). No steps written. NIFTY and SENSEX weekly expiries on the next trading days are expected to fall Monday/Tuesday: confirm a trade expires that day before running.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

### AX-01 Index tick silent for 60 seconds
- **Proves:** the screen says so when the index tick goes silent.
- **Type:** Functionality
- **27 Nov result:** NOT CHECKED: "The index tick never went silent for 60 s."
- **Fix carried first:** none named in the mapping given.
- MONDAY/TUESDAY ONLY: it needs a live index feed that goes silent for 60 s during market hours; on the weekend there is no tick to go silent. No steps written.
- **On FAIL or PARTIAL write:** the sentence seen, the sentence expected, known or new.

## 7. Known open findings F1 to F3: not a round 1 failure; one round 2 check each, ready now

Source: Lane Z's independent Opus review of the joined stop and exit paths (RESULTS-lane-z.md; verdict REVISE). In round 1 write what you see as an observation tagged "known F1/F2/F3". These checks run in round 2 (and again in round 3) once the fix lanes' build carries them. **Market closed limits what can be proven:** an exit that completes needs the market open, so each check says what the weekend can show and what is Monday's.

### R2-F1 After an exit with an unknown outcome, no second exit is sent (finding F1; fix lane FB, with FD's request key)
- **Update (Lane FB, `fix/r2-builder-1128`, 05:10 IST):** F1 is fixed on the page: the unknown-exit unlock now waits `UNKNOWN_EXIT_WINDOW_MS = 120 s` (not 5 s); the server-side request key (`client_request_id` on `POST /paper/strategies/{id}/orders`, also #871) is Lane FD's and was not started at 05:18. The check of R2-FB covers the page half; the key half stays open until Lane FD's RESULTS.
- **Board items:** F1; ADR-017; ADR-330 (59) item 1 (Lane U2). **Type:** Functionality. **First carried:** R2 (Lane FB; not on origin at v2).
- **What the finding says (Lane Z, word for word):** "StrategyBuilderPage.vue `decideUnknownExit`, `EARLY_MS = 5000`: after an UNKNOWN exit outcome the page says "not stored" and unlocks Exit if the trade looks unchanged 5 s after the client gave up; the server can still commit later (client timeout 10 s, statement timeout 30 s, pool wait up to 30 s, no idempotency key): a second per-leg partial Exit commits too (2 of 4 lots twice = 4 lots). Full-leg and Exit all are protected by EXIT_EXCEEDS_OPEN. Against ADR-017."
- **Expected after the fix (Lane U2 text, pending owner read):** "The first exit's outcome is being checked; no second exit is sent until the book has been read."; the Confirm stays grey past 5 s; "The change waiting on <legs> was not sent; it is kept until the exit's outcome is known."
- **Weekend steps:** with the market closed an exit is refused, so the unknown-outcome path cannot be run. Write what the round 2 RESULTS file of Lane FB gives as "PC steps, market CLOSED"; if it gives none: **BLOCKED: needs a completing exit (Monday, optional, Lane U2 item 1 step 2: stop the API right after pressing Confirm for a one-leg Exit; Confirm stays grey past 5 s; start the API and press "Open Orderbook" after 5 s; never two exit orders for one click).**

### R2-F2 An index exit fires when the index price feed is silent (finding F2; fix lane FE)
- **Update (Lane FE, `fix/r2-index-exit-watch-1128`, 05:35 IST): "Fixed, not tested"** (the core test was red on the round 1 commit, then green; 214 DB tests passed; Opus review done, its three major findings fixed). **How:** the worker's own reading of the index crosses to the paper monitor inside the existing monitoring snapshot in Redis (no new key, no migration), so an index exit no longer waits only for feed ticks; if the last price is too old the trade shows **"Monitoring paused"** with **"The last price is too old, so no rule can fire."** instead of "watched". **Lane FE's PC steps, market closed (word for word):** pull the branch and run, one file at a time under the PC's database rules, `tests_app/test_index_exit_watch_fe_1128.py`, `test_leg_exit_watch_fe_1128.py`, `test_review_fixes_fe_1128.py`, `test_paper_monitor.py`, `test_monitoring_state.py` through `scripts/orchestrator/db_run.py`; expect all pass. **Live (Monday, optional):** let the index tick go quiet; the exit still fires from the worker's reading, or the trade shows "Monitoring paused" with the sentence above; the Redis keys `ofo:feed:background:monitoring` (now with a `readings` part) and `ofo:feed:background:index_exits` are rewritten at least every 10 s. Known residual (Lane FE): a trigger armed while the held index quote is already across its level waits for the next tick, bounded by the index age (60 s); an API started without the live market and no report fails open.
- **Board items:** F2; the 23 Nov case (NIFTY tick stops 15:15:18); AX-01. **Type:** Functionality. **First carried:** R2 (Lane FE; not on origin at v2).
- **What the finding says:** "background.py `_read_with_either_spot` vs paper_monitor.py `on_quote`: the REST index stand-in makes the worker read FRESH and publish "watched" while the feed's index tick is silent; the paper monitor's index exits fire only on feed ticks and have no REST fallback: a crossed index exit never fires, no "exit not run" line, monitoring says watched."
- **Weekend steps:** a silent feed can be shown without a market: stop the feed process, arm an index exit on a paper trade (Positions > Paper > Stops > Conditional exit), and read the Stops panel and Plan watch. **Expected after the fix:** the trade is NOT shown as "watched" for that index exit while the index tick is silent (the Stops panel says the exit is not being checked, with a reason). The firing itself (a crossing) is Monday. Lane FE's RESULTS "PC steps" replace this text when it exists.

### R2-F3 The moved-leg stop: the user is told (finding F3; fix lanes FD and FA)
- **Board items:** F3; ADR-330 (48); issue #774. **Type:** Screen / Functionality. **First carried:** R2 (FD for the 201 reply, FA for the dialog).
- **What the finding says:** "routes/paper.py:1458-1460 with PaperConfirmDialog.vue:186-198: the stop cancel when a leg is moved is correct (same transaction, only closed contracts, never an open leg's stop) but the user is told through two failable reads; the 201 reply names no cancelled stop: on a slow or failed read the new leg has no stop, no offer and no line."
- **Weekend steps:** the review line is W-32 (**"The stop on <leg> will be removed; set a new one after the move."**). The move itself needs a completing order (Monday). **After the fix:** the 201 reply names the cancelled stop, so the line appears even when the two reads fail (Lane FD's RESULTS gives the exact text; write it when it exists).

## 8. Two data pulls for the PC (words and counts only)

The coordinator's pull comment (28 Nov 04:20 IST): "the saved rows for the 27 Nov 13:28 stop case (issue #876) and for the 2028 date seen on a 1 Dec 2026 contract, as words and counts only." **What to copy:** words, ids, counts, rule ids, kinds, outcomes, times (hh:mm:ss), column names, row counts, skip-reason words. **What NEVER to copy:** any price value (including the `price` column of `paper_orders` and any Rs amount), any address (host name, URL host), any login or user name, any port, any key or token. When unsure, copy less and say what you left out. All steps are read only; they place nothing.

### D-1 The 27 Nov 13:28 stop case: strategy A-G #207 (issue #876)
- **Question it answers:** which hold kept #207 from raising an alert (T1-06 FAIL on 27 Nov: "A-G's loss reached 10 % against a 5 % rule for 14 minutes with no alert row"; Lane Q3 could not reproduce case (h)). Issue #876 asks for "the saved plan body and style of that case".
- **Known already (do not pull):** plan accepted 13:13:33; rupee stop 80 plus T-06 weekly [50, 5, 40]; 0 suggestion rows seen; the loss was Rs 250.47 at 13:35.
- **Items (Lane J3's RESULTS, "For the PC"; the documents give table and column names, no SQL, for 1 to 4):**
  1. The plan body of strategy 207 as stored (the playbook plan row: `body`, and its accepted-at time) and the strategy's alert style pin (`strategy_alert_style`): copy the structure in words (which stage values were typed; weekly or monthly), no amounts.
  2. `public.paper_orders` of strategy 207: `created_at`, `side`, `quantity` of the first basket (the entry time that starts the 5-minute period, ADR-330 (47)); whether the trade is paper or real (the strategy's `mode`). **Do not copy `price`.**
  3. `public.adjustment_suggestions` of strategy 207 for 27 Nov: `rule_id`, `kind`, `shown_at`, `outcome`, `answer`, including dismissed ones (a dismissed or answered earlier row of the same rule silences it, ADR-236). Copy counts and words.
  4. The gate rows of strategy 207 (the table `playbook_store.load_gate_rows` reads: the last record per rule and today's count) and the worker log lines `strategy 207 check skipped: <reason>` between 13:14 and 13:36 (reasons: interval, not_ticked, unchanged, prices_*, no_preset, no_gate_read): copy the reason words and counts.
  5. Lane J's one verbatim query (tells hold (a) from (b)): `SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id WHERE s.name ILIKE '%#207%' ORDER BY 1, 2;`
- **Where it goes:** a comment on issue #876 by the owner or the coordinator (the PC does not post it); words and counts only. If strategy 207 or a table is not there: write that.

### D-2 The year 2028 shown for a 1 Dec 2026 contract (B-N1 #194, Lane M)
- **Question it answers:** is the stored expiry of the sold NIFTY 25750 PE really 2028-12-01 (wrong at the source) or did the "2028" come from the warning's own wording. Already known from PR #722: the five contracts of #194 read 2026-12-01 or 2026-12-08 at the source; 781 of 14,474 catalogue rows are more than 400 days ahead; "2028" appears only in builder and chain expiry drop-downs ("27 Jun 2028", "26 Dec 2028"). The name is "NOT EXPLAINED YET" (RESULTS-lane-m.md). The 27 Nov stop warning "... Sold option with less protection: NIFTY 25750 PE 2028-12-01." (UX-B01) was fixed by Lane M and passed on the PC on 27 Nov (T1-03).
- **Steps (RESULTS-lane-m.md, SQL verbatim):**
  1. `SELECT DISTINCT o.contract_id, c.expiry FROM public.paper_orders o JOIN public.catalogue_contracts c ON c.id = o.contract_id WHERE o.strategy_id = 194;`
  2. `SELECT id, expiry FROM public.catalogue_contracts WHERE name = 'NIFTY' AND strike = 25750 AND instrument_type = 'PE';` then say whether any of those ids appears in (1) or in `paper_triggers` of strategy 194.
  3. `SELECT id, name, instrument_type, strike, expiry, exchange_token, first_seen_at, last_seen_at, currently_listed FROM public.catalogue_contracts WHERE id IN (SELECT DISTINCT contract_id FROM public.paper_orders WHERE strategy_id = 194);` Copy ids, expiry dates and the yes/no "a 2028 id appears". **Do not copy `exchange_token`** if it identifies a broker session; it is a contract id, so copy it only if the owner agrees.
  4. From the browser, the path (not the host or port) and the `contract_id` and `level` words of `GET /paper/strategies/194/leg-stop-risk` and the status code. No price value.
  5. If an expiry reads 2028-12-01 the next question is the row's revision history and the loader run that wrote it: the documents give no SQL for it; **do not invent one**; write "2028 found in row <id>" and stop.
  6. Screen re-test (paper only): Positions > Paper > B-N1 > Stops, on NIFTY 1 Dec 25650 PE type a stop "Above 102.55". Expected exactly: **"If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25). Sold option with less protection: NIFTY 1 Dec 25750 PE."** (this is W-20; the figures are the check's own text, do not copy them anywhere else).

## 9. Round 2 (Saturday 21:00): one check per fix, from the fix lanes' own result files

**Update (coordinator, 28 Nov afternoon): migrations 0060 then 0061 are applied in one step** (section 2, R2-2). Where a check below says "BLOCKED: 0061" or "NOT in the build", it holds only until the final round 2 commit (expected about 16:30 IST) carries the files; the next version names the commit and re-marks each lane with `git merge-base --is-ancestor`.

**What round 2 builds.** The build is `integration/weekend-r2-1128` at `829ff65f26716f1efbcbac98ea3ba6aefdc350d9` (frozen by the coordinator 28 Nov 17:15 IST; Lane Z2's final RESULTS: sixth review SHIP, READY yes). The PC runs `git rev-parse HEAD` after checkout and writes the commit; no tag. Keep `test/weekend-r1` (and `test/screen-2026-11-27` at `bdb0d126`) untouched; never reset them.

**In the frozen commit (checked 28 Nov with `git merge-base --is-ancestor <branch tip> 829ff65f2`):** FB `fix/r2-builder-1128`, FC `fix/r2-small-screens-1128`, FC3 `fix/r2-plan-screens-1128`, FD2 `fix/r2-backend-2-1128`, FE `fix/r2-index-exit-watch-1128`, FA2 `fix/r2-exit-stops-2-1128`, FE2 `fix/r2-worker-issues-1128`, FE3 `fix/r3-worker-3-1128`, FR `fix/r3-readers-1128`, FD3 `fix/r3-backend-3-1128`, FD4 `fix/r3-backend-4-1128`, FK `fix/r3-chart-teardown-1128`; tests `test/r2-backend-1128` (TA), `test/r2-frontend-1128` (TB), `test/r2-named-green-1128` (TE), `test/r2-walk-builder-1128`, `test/r2-walk-close-1128`.
**Partly in (the branch has commits the frozen commit lacks):** FA `fix/r2-exit-stops-1128` (1 commit not in), FB2 `fix/r2-builder-2-1128` (1), FC2 `fix/r2-pages-1128` (1), FD `fix/r2-backend-1128-fd` (1), FJ `fix/r3-frontend-joins-1128` (2; the Exit fix `8d4355df2` IS in, merged at `92a8c74c1`), test lane `test/r2-gaps-1128` (TF, 2).
**NOT in (BASELINE):** `fix/r3-backend-5-1128` (FD5, 28 commits ahead), `fix/r3-leftovers-1128` (47), `fix/r4-worker-4-1128` (3), `test/r2-plan-walk-1128` (TG, the cloud walk: tests and screenshots only). **A check for a lane that is not in the commit, or only partly, is run as BASELINE for the later commits: write "BASELINE" in the row and expect the old behaviour. Where a check below says a lane is "NOT in the build" for FA2, FE3, FR, FD3, FD4, FK or 0061, that is out of date: they ARE in this commit.** A BASELINE row is never a failure of the build.

**Migrations (the DB also serves production: backup first, owner's typed yes before any apply).**
- **`0060_plan_stamp_only_on_switch`** (down revision `0059_last_close`) is in the build (the plan acceptance change of Lane FC3 item 1). It replaces ONE function (`strategy_adjustment_plans_guard`); no table, no column, no row changes. `accepted_at` is stamped on UPDATE only when the transaction-local setting `ofo.plan_acceptance` is `on` (first save, accept via POST/PUT `accept:true`, Reset). Proven in the container: 0059 up, 0060 up, 0060 down, 0057 down, up to head.
- **Old code is NOT safe on a 0060 database** (Z2: "Not safely"): round 1 code does not stamp `accepted_at` on accept, and a plan with a NULL playbook pointer loses its stops on edit. New code on a 0059 database works. So: migrate, then restart the new code in the same session. **Rollback of the code must also run `alembic downgrade 0059_last_close`.**
- Apply: `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`; `alembic heads` must show one head, `0061_order_request_keys`. No new seed (round 1's 17-row last-close seed stays).
- **`0061_order_request_keys`** (Lane FD3, down revision 0060; one additive table `public.order_request_keys`, grants SELECT, INSERT, UPDATE(state, result, finished_at), no DELETE) **IS in the frozen commit.** 0060 then 0061 are applied in ONE step, [OWNER APPROVAL], after a verified backup (section 2, R2-2). The lane's claim that old code is safe on 0061 is reasoning only (no run of old code on a 0061 database is recorded), so the rule stands: migrate and restart the new code in one sitting; a code rollback also runs `alembic downgrade 0059_last_close`. The order request key needs Redis.
- No other lane has a migration (FE2 keeps the paused state in Redis; FD2 only asks for the table that became 0061).

**Services.** Restart order: API, then worker, then feed; **Redis must be up: an order with a request key is refused with 503 `request_key_store_unavailable` when the key store is down** (the order is then not stored: that is the correct answer, not a failure). After the API restart open Positions with no Zerodha session: 200, "not connected", the stored close. **Restart the vite server after checkout** (round 1 lost three routes to a stale vite). Vite proxies every `/api/...` path to the API and strips `/api` for routes the API serves without it; the one new route, `GET /real/strategies/{id}/triggers`, needs no vite change, but call it through the vite address (`/api/real/strategies/<id>/triggers`), not only `:8000`.

**Merge-order warning.** FB2 sends `client_request_id` on every Add to Paper and every Exit from the builder; `PaperOrdersIn` is `extra="forbid"`, so a server without FD2 answers **422 on every Add to Paper and Exit**. FD2 is in this build, so 422 is NOT expected; if the PC sees one, write the exact text and whether the commit contains FD2. FB2's other dependencies: UX-C3 regresses until FC3 (in) is merged; the dialog prints no cancelled-stop lines until FA2 (in the frozen commit) is merged.

**How to read each check.** Branch and "in build" first; then the board items (UX-nn, I-nn, OBS-nn, D-nn, issue #nnn, F1/F2/F3, R1 to R9); then the PC steps with the market CLOSED, word for word from the lane's own file, numbered; then the expected texts word for word; sentences marked **pending owner read** are new and the owner has not read them (the PC reports whether they read plainly, never rewrites them). "Decided for the owner" is the lane's own decision, shortened to one clause each. Live-market parts are listed as Monday and optional. Paper only, market closed, unless a step says otherwise. Where a lane has no PC steps the check says "no PC steps in its result file". Every check ends: **On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.**

---

### R2-FA Exit dialog and Stops panel (`fix/r2-exit-stops-1128`, Lane FA, tip `45ec4c94`) and FA2 (`fix/r2-exit-stops-2-1128`, tip `d8addf262`)
- **In build: NO for both (FA: 5 ahead, FA2: 8 ahead). Run BASELINE; NOT IN BUILD: check with `git merge-base --is-ancestor`.** Checkout-by-branch is not needed: if the coordinator adds them, the rows become real.
- **Board items FA:** I-17 (price age line), I-18 ("Placing exit..."), I-29 (index exit rule after the close), D2 (ISO date on a stop row), #872, #874. **FA2:** F3 dialog half (cancelled stops), not-live tick (UX-A13, UX-A24), request key and "first exit" wording, UX-A02 (leg cost), D-12, #870 (dialog half), #872, #873, D-4 / I-147 (Add to Paper after the close), TD O-6 (level format). **Not done:** FA: UX-A01 (done in FC2), F3 (waits for FD2), #870, #873; FA2: page halves (F3 page half is FB2/FJ), UX-A01, browser check (not run in the cloud: "Do it on the PC").
- **PC steps, market CLOSED (FA, word for word):** 1. Positions: open Exit on a strategy with "no price" rows: the dialog opens, shows the age line ("No price for ..."), the market-closed line and Confirm greyed. 2. Stops panel of a paper strategy: type a level above NIFTY, Save. Expect "Saved: exit above ...", the reference line under the index line, no "Index values unavailable.". Repeat with SENSEX. If refused, copy the refusal text (it goes to Lane FD). 3. (D2) A stop on a leg that is not among the open legs: the date reads "NIFTY 22300 PE 3 Nov", never "2026-12-01".
- **PC steps, market CLOSED (FA2, word for word):** 4. Positions: tick a leg and press Exit (before FJ `8d4355df2` Exit was disabled there while paper prices were paused; the frozen commit has it: expect the dialog; if Exit is disabled write it and use the builder, where the dialog is the same). The dialog lists the leg and shows the server's sentence "The market is closed. Exits can be placed from 09:15 on <next trading day>."; Confirm is greyed. If the risk line says "The app could not check ...", it must NOT say "You can still confirm." 5. Open Stops on a strategy: each leg row shows "Costs now <price>" or "Costs now: not priced" beside the Stop price box (needs owner-lane change 3). 6. Leave the dialog open across 09:15: within 15 s Confirm turns on without reopening (needs a live open; skip on a Sunday).
- **Expected texts (FA):** "No price for N of M legs; the server prices the exit when you confirm."; "The time of the price is not available."; "Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago."; Stops panel with no close: "NIFTY: the last close is not available."; reference line: "The market is closed. A level you save is checked from the next market open; the last close is shown for reference."; "Placing exit..." (status slot while busy).
- **New sentences waiting for the owner's read (FA2):** "The stop on <leg> (level <level>) was removed with the move; set a new one on the new leg." (level part dropped when the reply has none); "The stop on the old leg may have been cancelled, and the new leg has no stop until you set one."; "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known."; "Two minutes have passed and the outcome of the first exit is still not known. Open the Orderbook to see whether it was placed; no second exit is sent until the answer is known."; "The app could not check whether this exit leaves a sold option without protection."; "Costs now <price>" / "Costs now: not priced". Gap the lane names: the entry dialog shows the server's "Exits can be placed ..." sentence (the word "Exits" is wrong for an entry; FD4/FC3 serve `entries_sentence`).
- **Decided for the owner (FA):** 1 age lines and reference line are new wording, pending owner read; 2 the age is told against the browser clock, not the server's; 3 whole seconds use a remainder helper, not Math.floor (these are times, not money); 4 D2 keeps the server's contract text but its date reads through the one date rule; 5 #872 asks the market state again on every Confirm press (fail closed). **(FA2):** 6 ADR-330 (60) applied to Add to Paper: the entry dialog asks the same answer, greys Confirm, fails closed, re-asks every 15 s only while open; 7 cancelled-stop wording is past tense and carries the level; 8 the not-live tick resets on opening, not on the line's text; 9 #870: the dialog never clears the lock; after 120 s its line says the 120-second sentence; 10 the key is a UUID from `crypto.randomUUID()`.
- **Monday (optional, live):** "Price as of HH:MM:SS IST, N seconds ago."; Confirm shows "Placing exit..." then "Exit placed on paper (order N)." in view; stop the server before Confirm: the unknown line shows in view and Confirm stays locked until the re-read; FA2: prices pausing every 60 s (UX-A13): the not-live tick holds; move a leg's expiry: one line per cancelled stop; exit whose answer times out: Confirm off, after two minutes the dialog says the outcome is not known + Orderbook. FA2's Opus review did not cover items A, B, C (about 20 files): a short review is recommended before the owner relies on item A.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FB Builder page, finding F1 (`fix/r2-builder-1128`, Lane FB) and FB2 (`fix/r2-builder-2-1128`, tip `3b9b1b930`)
- **In build: FB YES. FB2 PARTLY (merged at `3a26d3a8`: items 1 to 4 and I-71; the later F3 page half and `outcomeLoading` are NOT in).** Rows for what is not in are BASELINE.
- **Board items FB:** F1 (the unknown-exit unlock now waits `UNKNOWN_EXIT_WINDOW_MS = 120 s`), I-30 (contract-list line), I-50 (one loading state per leg), UX-B25, UX-AF1, UX-C3 (two of three lines), UX-A03 (proven already). Not fixed: I-49 (slow first prices), I-68 (no code change; two steps are spec decisions ADR-330 (19), (28)). **FB2:** F1 second path (exit lock restored from sessionStorage), double order on the save-bar path (Opus F2, F4), `client_request_id` on every builder post, I-49 (leg shown at once), UX-B25, UX-C3, D-10 (1366x768 layout), I-71 (Pick from Option Chain), F3 page half + `outcomeLoading`. TD ids: I-21 not mine, I-41 nothing in my files, I-66 blocked, I-86 not mine, I-88 nothing in my files.
- **PC steps, market CLOSED (FB, word for word):** 1. `git fetch && git checkout fix/r2-builder-1128`, start the app, open the builder with no legs. If the instrument list is yesterday's (before the load), expect the server's line above the legs. Run `cd frontend && npx vitest run tests/contract-list-line-r2-fb.test.js tests/leg-working-r2-fb.test.js tests/builder-first-prices-r2-fb.test.js tests/add-to-paper-r2-fb.test.js`. 2. Pick two legs: while the outcome is out, every leg row says "Working out the outcome..." and shows no capture time; the figures return when it answers. (On the PC use the build's commit, not the checkout of the branch.)
- **PC steps, market CLOSED (FB2, word for word):** 3. `cd frontend && npx vitest run tests/save-bar-add-lock-r2-fb2.test.js tests/leg-show-at-once-r2-fb2.test.js tests/builder-ux-r2-fb2.test.js tests/add-to-paper-r2-fb.test.js`. 4. Builder with two legs of a strategy that has no fixed maximum loss (TC strategy #5) at 1366x768 and 1280x800: "No fixed maximum" stays inside its tile, nothing overlaps "Intrinsic value". 5. Pick a leg and press Done: the leg is in the list at once with "Working out the outcome...", the price fills in a moment later.
- **Expected texts:** after an unknown add ("Review and add", also under the save bar): "The last paper order got no answer and may be stored. It is not sent again until the Paper book has been read: open the strategy again to check."; "Working out the outcome..."; "Updating the numbers..." (now on four summary figures); the server's "Contract list of <date>. Today's list loads at about <hh:mm>." (not new, e.g. "Contract list of 26 Nov. Today's list loads at about 08:35.").
- **New sentences waiting for the owner's read:** the unknown-add sentence above; suggested, not built: "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known." FB2: none new (reuses the above).
- **Decided for the owner:** FB: 1 fail-closed lock after an unknown add (reopen the strategy to clear it); 2 I-30 a failed re-read keeps the line already shown; 3 I-68 no change (one press, one order already holds; a one-press name step is a SPEC CHANGE to (19), (28)). FB2: 4 after an unknown add the Add to Paper button is off until the Paper book has been read; 5 the key goes on every builder post, adds and exits; 6 "no order in the book" frees the add only for a read sent 130 s after the client gave up; 7 UX-B25 figures hold "Updating the numbers..."; 8 UX-C3 Plan watch loses its own loading line while the page's line shows; 9 D-10 the four figure boxes may wrap rather than spill.
- **Monday (optional, live):** 08:30 to about 08:35 the contract-list line on the builder (also with no legs), gone within about a minute after the list loads, no reload; time Done to first prices for one leg (T2-11: 14 s before; FB expects the same, I-49 not fixed in FB); Add to Paper on a new strategy: Confirm not greyed with live prices; press Confirm twice quickly: one paper order only; FB2: cut the network after Confirm, Cancel, press again: stays off with a plain line, nothing sent; restore the network: the line ends when the book shows the order (or 130 s after when none).
- **Not fixed (known):** I-49 (cause in `LegPicker.vue`), `EARLY_MS = 5000` is NOT in FB/FB2 heads (it exists only on branches cut before Lane FB's fix, e.g. FA2), lock is per tab only, F6/F8/F9 add-lock minors.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FC Small screens, pages, plan screens (`fix/r2-small-screens-1128` FC; `fix/r2-pages-1128` FC2, tip `8f3310625`; `fix/r2-plan-screens-1128` FC3, tip `45a936453`)
- **In build: FC YES; FC3 YES; FC2 NO (6 ahead, left out, Lane FJ): its rows run as BASELINE, NOT IN BUILD.**
- **Board items FC:** I-122, I-69 (UX-05, UX-06; already in), I-70 (UX-B06 not confirmed by FC), I-24 (page half), F7 (`stop_kind_reason`), I-61 ("Now" value), I-62 (take-profit wording), far-month badge (no page change); TB defect D1. **FC2:** Alerts > History loading line, D-6, D-7, D-8, D-11, D-13, UX-B04 step 4 words, UX-A09, ADR-330 (61) list line, UX-A01, UX-A19, UX-A05 (Plan door on the Live card), D-TD-2 / I-86 (Retry on six list pages, `ListLoadFailed.vue`), O-1 / I-157, UX-A02 (current price), chart teardown; UX-B06 closed by FC. **FC3:** plan acceptance ADR-330 (45) (the 0060 migration), real exits read wired to `/real/strategies/{id}/triggers`, UX-SW6, UX-B13, UX-A06, UX-A12, UX-A09, `stop_fired_at/on` "seen by the check at ...", #880, #875, UX-A03 keys, four monitoring "Not being watched" sentences, `expiry_kind_unknown`; UX-A18 cause found (`routes/paper.py` ~1625, fixed by FD3, NOT in build).
- **PC steps, market CLOSED (FC, word for word):** 1. `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_d36_adjustment_counts.py` (the new take-profit sentence in `approaches.json`; Lane FD notes two failures of this file on the unmodified build, `test_approaches_counts_and_reply` and `test_check_counts_and_reply`, expected strategy_id 1, got 123: write them as known). 2. Positions > Adjustment opportunities: every open record says "Now: not read yet" until Lane FD adds the fields (FD2 adds them: see R2-FD). 3. Open a plan sheet of a trade whose expiry kind is not known: the stop box shows the server's reason (`plan-stop-kind-reason`). [FC's worktree cleanup step is its own container's: not a PC step.]
- **PC steps (FC2, word for word):** 4. Alerts > History: reload; "Loading..." while it reads, never "No stops or expiry settlements yet." first. 5. Positions with two or more open paper strategies and the feed down: the paused sentence appears once at the top with its date and time; "NIFTY" and "Running" have a gap; Show closed positions: a closed row has "—" in Unbooked and P&L. 6. Create Strategy: step 4, click Show strategies: below "Loading…" a line names what is read and says up to 20 seconds. Step 3 shows the "Contract list of ..." line only while yesterday's list is in use (08:30 to about 08:35). 7. Positions > Real: with a session, end the session; within about 30 s the Real P&L is a dash with the not-connected message, no reload. 8. Live Strategies: a running trade's card has a Plan button; it opens the same plan sheet as the Positions row. 9. Stop the API and open Live Strategies, Alerts (Active, History), Positions, Adjustment opportunities, Home, Option Chain: each says one failed-load sentence and has Retry; start the API, press Retry: the page loads. 10. Positions: tick a leg, then make the read fail (stop the API): the tick stays; Exit (1) is off with the not-live sentence and "Last prices: <time> IST."
- **PC steps (FC3, word for word):** 11. Market closed: open a saved paper trade on the builder; with 2 or more unchecked rules the rules line is one line with a count and an expand; open a settled trade: no "Checked at Time not available". Also `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_d36_adjustment_counts.py`.
- **Expected texts:** "Now <value> as of <time> IST" / "Now: not read yet" (open records only); "This approach is not built because the whole trade would not be in profit with every open leg closed at its planned price."; "Exits of a real-mode trade cannot be read here yet." (until FC3's read shows the exits); "Delete 14 strategies? 3 of them are running." (FC2/FB wording "Delete 3 strategies? 1 of them is running."); "N rules not checked: <reason>" (a group with no reason says "no reason was given"); "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value."; "Every exit rule is not checked because whether this trade expires weekly or monthly is not known."; "This trade is closed; nothing is watched."; "The plan watch is paused while the feed has no live prices. It resumes with them."; "Since 10:12, 20 Nov 2026"; "{line}; seen by the check at {time} IST" / "{line}; seen by the check on {date} at {time} IST"; "Stop fired: <leg> reached <level>; max loss at that point Rs <figure>" (also "...; there was no fixed maximum loss at that point", "...; the maximum loss at that point was not worked out"). FC2: "Reading the strategy list. This can take up to 20 seconds." / "Reading the planned entry prices of N contracts. This can take up to 20 seconds." / "Pricing N strategies: D of N done. This can take up to 20 seconds."; "The real P&L figure is more than 90 seconds old and is hidden until the next read."; "Could not load this list. Nothing was changed." with "Retry"; "Last prices: 15:27:00 IST." and "Tick a leg to exit.".
- **New sentences waiting for the owner's read:** every sentence in the list above except the existing ones ("Contract list of ...", "Plan", the paused sentence with ", as of <date>, <time> IST", "Monitoring paused"). FC3's four "Not being watched: ..." sentences are written out in R2-FE.
- **Decided for the owner:** FC: 1 I-61 "Now" is the worker's stored reading with its as-of time, open records only; 2 the badge for an unknown expiry kind is the existing "Monitoring paused"; 3 (8) stays as decided: running paper strategies are deleted in bulk. FC2: 4 D-8 a closed leg shows its booked figure and "—" in Unbooked and P&L; 5 D-13 Real part re-read every 30 s, hidden when older than 90 s; 6 UX-A09 one paused sentence when two or more are paused; 7 D-TD-2 one failed-load rule: no server message = one sentence + Retry (Option Chain keeps its own sentence); 8 UX-A05 the Plan door on every running Live card. FC3: 9 grouping key is the server's reason sentence; 10 the date is appended after the server's "Since hh:mm"; 11 a real trade shows the "cannot be read here yet" line until the real read exists.
- **Monday (optional, live):** a far-month trade with every rule not checked shows "Monitoring paused" with its reason; pause the feed: the Plan watch sentence once; "Monitoring paused" for a worker stopped on an earlier day shows the date; Positions > Real open more than 90 s with Zerodha unreachable: the figure disappears and returns; leave the page 2 minutes: no more `GET /api/positions`.
- **Open:** FC2 not done: D-4 (built in FA2, not in), O-3, O-4, O-6, #870 proof, UX-AF2, UX-B03, D-13 socket trigger; FC3 not done: F5 (move wording after an unknown outcome), item 6 opportunity-row names, d36 (no PostgreSQL there), screenshots; D-5 ("Checked at" in `PaperBookPanel.vue`) found, not changed.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FD Backend: totals, key, reads, durable key (FD `fix/r2-backend-1128-fd`; FD2 `fix/r2-backend-2-1128`, tip `87ca3b39f`; FD3 `fix/r3-backend-3-1128`, tip `3f63b160b`; FD4 `fix/r3-backend-4-1128`, tip `f64ba4587`)
- **In build: FD PARTLY (merged at `417ed2ec`, 1 later commit not in); FD2 YES; FD3 NO; FD4 NO** (FD4 is built on FD3's pushed head `e6b48eb57`, not on FD3's tip, so it lacks FD3 round 2: R9, R6 not-applicable stops, UX-A18). FD3 and FD4 rows run as BASELINE, NOT IN BUILD.
- **Board items FD:** B1 (ADR-330 (62) booked result in the header total; the `place_paper_orders` connection hold fixed), B3 (already in), B4 (found, not changed), B2 (plan acceptance: arrives as FC3 / migration 0060), B5 not started. **FD2:** F3 `cancelled_stops`, `client_request_id` (paper and real door), D-1 stored close with no session, D-2 Positions with no session, D-3 (migration 0059 tests: CHECK right, tests wrong), `server_time`, `now_value` / `now_as_of`, `GET /real/strategies/{id}/triggers`, #877, #855, #857, #858, #859, F4. **FD3:** I-158 (R5), durable request key (R8, migration 0061), `kinds_of` raises, connection held across waits, pool-release scan, ten failing DB test files, plan acceptance F5/F7, R9, R6 route half, UX-A18. **FD4:** `entries_sentence`, monitoring reason map, last_close seed (name = trading symbol), UX-A08 measured (~83 ms warm), F7 half 1.
- **PC steps, market CLOSED:** FD (word for word): "Market closed: none for B1. Live: none." The PC re-checks the totals of W-06 (header total shows the booked result of closed trades) and the connection count of set-up step 0 (no growth while the screens are open). **FD2 (word for word):** 1. Market closed: restart the API with LIVE_MARKET on and no Zerodha login. GET /api/market/indices should answer the 27 Nov close with its own date and time; Home and the Option Chain show the stored closes. 2. GET /positions (on the API's own address, for example http://127.0.0.1:8000/positions; NOT through the vite address, where that path is the page) answers 200 with `broker_connected: false` (with `real_pnl.state: "not_connected"`). 3. `GET /api/real/strategies/<id>/triggers` through the vite address: empty list when none. "Live: no step for items 1 to 3."
- **PC steps FD4 (BASELINE unless in build):** 4. One file at a time: `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py` for test_exit_market_adr330_60, test_monitoring_status_route, test_last_close_seed_symbol_name, test_order_routes_fd4, test_plan_read_cost_fd4. 5. The seed, once the PC has the real snapshot: `python -m ofo_app.last_close_store seed <file> --check`, expect 17 rows accepted and no `why:` line. **FD3 (BASELINE; step 1 is NOT run, see intro):** 6. lane's step 1 word for word: "back up, `alembic upgrade head` (0061, additive: old code runs against the migrated database, it never touches the table)": not run, no proof. 7. `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_order_request_key_durable_fd3.py` (one file; it commits a strategy row, run on a clone). 8. Press Confirm twice on a paper order with one `client_request_id` (the page sends it): one set of orders.
- **Expected texts (new, pending owner read; FD2 key refusals, four parts each):** `request_key_other_strategy`: "This request key was already used for another strategy." / "No order was stored; one request key belongs to one set of orders on one strategy." / "Placing these paper orders." / "Press Confirm again to place the orders with a new request key."; `request_key_different_body`: "This request key was already used for a different order set." / "No order was stored; a repeat of a request must carry the same orders as the first." / "Placing these paper orders." / "Read the strategy's orders, then press Confirm again if you still want them."; `request_key_in_progress`: "The first request with this key is still being placed." / "No order was stored by this repeat; the first request decides what is stored." / "Placing these paper orders again." / "Wait a moment and read the strategy's orders before you try again."; `request_key_store_unavailable`: "The app could not check whether these orders were already placed." / "No order was stored; with the check down, a second copy of the same order could be stored." / "Placing these paper orders." / "Read the strategy's orders to see what was stored, then try again."; `request_key_already_prepared` (real door): "A basket was already prepared for this press." / "No new basket was prepared, so the same orders cannot be sent to Zerodha twice from one press." / "Preparing this basket again." / "Open this strategy's plan to see the basket that was prepared."; `real_position_exit_refused`: "Real position: exit and protect it in Kite." / "Stops and alerts here cover paper trades only." / "Exiting or protecting a real position here." / "Use Kite to exit or protect this position." FD3: "This strategy is busy with another action, so nothing was changed." (`store_busy`, 409). FD4: "Orders can be placed from 09:15 on {day}." / "Orders can be placed when it opens." (null until the templates exist). FD: fired stop "{line}; seen by the check at {time} IST" (done in FC3).
- **Decided for the owner:** FD: 1 B1 cherry-pick skipped (already in); 2 the real first fill still holds a connection (ADR-330 (58) gap). FD2: 3 #877 "real position" = `position_kind.kind_of` real, and an unknown kind is refused too (409 `real_position_exit_refused`, fail closed); 4 #855 real door lots refusal is 409, paper keeps 422; 5 #859 batch budget 15 s, a cut row reads `not_read`; 6 `now_value` is the worker's stored reading, null until FE publishes; 7 D-1 no stored session: the market keeps a socket-less book with the stored close and its own date/time; 8 a repeat of a paper key answers 201 with the book as it is now; a repeat on the real door is refused (409) and prepares nothing; 9 key store is Redis, TTL 600 s, scoped by user. FD3: 10 an old armed stop of a real position is kept, shown as not applicable, never cancelled; 11 Redis down still refuses a keyed request (the table does not replace that check). FD4: 12 `entries_sentence` is null until the catalogue has its templates.
- **Monday (optional, live):** none for FD/FD2 items 1 to 3. FD3: repeat with the feed on; flush the Redis key (`redis-cli flushdb`) between presses: the second still answers 201 with the same order ids; try an exit on a held (real) strategy: 409 with "Real position: exit and protect it in Kite."
- **Open in the lanes (known):** FD2: `routes/tracking.py::exit_tracking` stores paper exits for a real position (Opus F1 MAJOR, fixed only by FD3, NOT in build; R5); UX-A08 not measured by FD2; F6 refused order shows no sentence; 19 routes not proven to release the connection; `kinds_of` swallows a DB error (FD3 fixes). FD3: F2 minor (record_plan after release does not re-check adopted holdings or the W-151 revision), `record_basket_facts` holds the strategy lock + a connection ~3 s (question to the owner, listed not decided), R9 deadline not on the real door, `cancelled_stops` from returned ids not done, plan-watch half of R6 has no new test.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FE Worker exits and the monitoring sentences (`fix/r2-index-exit-watch-1128` FE, tip `dc25e9fe`; `fix/r2-worker-issues-1128` FE2, tip `c17496293`; `fix/r3-worker-3-1128` FE3, tip `3cb9a841b`)
- **In build: FE YES; FE2 PARTLY (merged at `6b409ab9`, newer head not in); FE3 NO.** FE3 rows are BASELINE, NOT IN BUILD. FE3 reads its base as FE2 + FC3.
- **Board items FE:** F2 (index exit with a silent feed; "Fixed, not tested"), queue item 2 (leg-price exits when a leg tick is silent), Opus review F1 to F3 and minors 1 to 4 and 6. **FE2:** items 1 to 9 = one `index_exits` slot per monitor, #863, #862 (no code change), #868 (paused state in Redis), #865, #867, #864 (worker half), #878, #879 (worker half), #860, #861, #866, F7, coordinator (a) "no report = paused/stale, why `exits_not_checked_yet`", (b) `paper_monitor.py` no longer fires old armed stops on a real/unreadable position (ADR-330 (64)). **FE3:** failed check stays failed, failed book read keeps the watch 120 s, atomic exit report (Redis hash `index_exit_slots`), pause "since" kept over restarts (#880 worker half), three new sentences, fired leg stop in the past tense, R6, R7; #876 NOT reproduced.
- **PC steps, market closed (FE, word for word):** 1. Pull the branch and run, one file at a time under the PC's database rules, `tests_app/test_index_exit_watch_fe_1128.py`, `test_leg_exit_watch_fe_1128.py`, `test_review_fixes_fe_1128.py`, `test_paper_monitor.py`, `test_monitoring_state.py` through `scripts/orchestrator/db_run.py`; expect all pass. 2. With the feed process stopped and a paper trade with an armed index exit: the trade must NOT read "watched"; it reads "Monitoring paused" with "The last price is too old, so no rule can fire."
- **PC steps (FE2, word for word):** 3. Market closed (paper only): pull the branch; one file at a time through `scripts/orchestrator/db_run.py`: `tests_app/test_monitor_reports_fe2_1128.py`, `test_worker_expiry_fe2_1128.py`, `test_worker_saved_plan_fe2_1128.py`, `test_pause_restart_fe2_1128.py`, `test_unknown_kind_style_fe2_1128.py`, `test_checked_body_fe2_1128.py`, `test_kind_cache_fe2_1128.py`, `test_dropped_and_skew_fe2_1128.py`, plus Lane FE's three files and `test_monitoring_state.py`; and `python -m pytest tests/adjustment/test_stop_lines_fe2_1128.py`; expect all pass. **(FE3, word for word):** 4. One file at a time through `scripts/orchestrator/db_run.py`: `tests_app/test_check_failed_fe3_1128.py`, `test_pause_since_fe3_1128.py`, `test_report_atomic_fe3_1128.py` (needs Redis), `test_kinds_unread_fe3_1128.py`, `test_stop_fired_line_fe3_1128.py`, `test_stop_fired_message.py`; and `python -m pytest tests/errors/test_template_pins.py`; expect all pass.
- **Expected texts:** FE: "Monitoring paused" with "The last price is too old, so no rule can fire." FC3's four (in the build; written to `explanations.py`, quoted by FE3): "Not being watched: the index price is not live, so the index exit cannot run." / "...a leg's price is not live, so its stop cannot run." / "...an exit has no price to compare with, so it cannot run." / "...the index exits are not running right now." **FE3 (BASELINE):** "Not being watched: the exits have not been checked yet." / "Not being watched: the book could not be read, so the exits cannot run." / "Not being watched: this is a real position, and stops here cover paper trades only." FE2 proposed: "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value."
- **New sentences waiting for the owner's read:** FE: none. FE2 and FE3: the sentences above marked BASELINE or proposed (pending owner read). FR, FD4, FC3 give them their codes (`monitoring_why_<code>`).
- **Decided for the owner:** FE: 1 the reason of an unwatched exit is the existing `stale` with a why, not a new sentence; 2 the worker's reading crosses the process boundary inside the monitoring snapshot in Redis (no second REST read in the API process); 3 when no monitor ever wrote a report the worker's answer stands; 4 a trigger armed while the held quote is already across its level waits for the next tick. FE2: 5 **(a) REPLACES FE decision 3: no report = not watched** (cost: a trade with no armed index exit also reads paused while no monitor has ever written a report); 6 a real/unreadable kind = no stop here, the old armed stop is left unfired and untouched, told once in the log; 7 unknown expiry kind = `intraday` timing style (owner choice still open, J3 F4); 8 a strategy that left the list reads "not listed", paused. FE3: 9 a failed check stays failed until a check that ran has passed (cost: up to the 30 s interval of extra pause); 10 a kept watch list stands 120 s after a failed book read; 11 the exit report is a Redis hash with a new key; 12 a book left in profit by a leg stop writes no loss line, not "Rs 0".
- **Monday (optional, live):** index tick goes quiet: the exit still fires from the worker's reading, or the trade shows "Monitoring paused" with "The last price is too old, so no rule can fire."; Redis keys `ofo:feed:background:monitoring` (with a `readings` part) and `ofo:feed:background:index_exits` rewritten at least every 10 s; FE2: two API workers show two `owners` slots; restart the worker with a paused trade: it reads "Monitoring paused" and "Since" is kept; exit a trade: its entry leaves the monitoring key within 10 s; FE3: `HGETALL ofo:feed:background:index_exit_slots` shows two fields.
- **Contradiction to read first:** FE (in build) says "no monitor ever wrote a report: the worker's answer stands"; FE2 (a) says the opposite. With FE only, the PC may see no "paused" for a trade with no report; with FE2 (a) it does. Write which commit the PC has. FE and FE2 file to-be-filed items: several API workers each running a paper monitor overwrite one `index_exits` key (FE2 item 1 fixes it); a trigger armed across its level fires only on the next tick.
- **Issues #860 to #868, #878, #879 (market-closed view, in the build only as far as FE2 is):** #860 plain "15:20" time exit with an unknown expiry kind reads "not checked" (known gap; the dated form runs); #861 worker reason for an unknown-kind percent stop; #863 two legs of different expiries, farther listed first: which expiry the monitoring entry uses; #866 plan sheet reason says the expiry kind is unknown; #867 delete or settle a paper strategy: no leftover entry in the monitoring list; #868 restart the worker: the "Monitoring paused" badge is not lost; #878 close a paper strategy: its stored monitoring state must not show "watched"; #862, #864, #865, #879 are not visible on a screen; #876 (plan save of 27 Nov 13:28): not reproduced by FE3; its cause is unknown (FE3 asks the PC for the log lines `has no alert preset` / `check skipped` for strategy 207 and the stored plan body of strategy 207: the data pull D-1 of section 8).
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FJ Frontend joins: locks, one key on every page, plan screens (`fix/r3-frontend-joins-1128`, Lane FJ, tip `287c2dfa5`)
- **In build: NO (batch 2). BASELINE, NOT IN BUILD.** Its base is r2 integration + FB2, FA2, FC2, FC3, FD2 merged; it is the lane that brings FA2 and FC2 in. Its STATUS: "item 1 PARTIAL: round 2 re-review REVISE, 4 findings parked, GROUP A NOT READY"; "NOT SAFE TO CLOSE: item 1 parked remainder, item 7 not run."
- **Board items / findings:** item 1 lock + one key on every page (R1; "Fixed, not tested in a browser"), item 2 cancelled-stop lines (page half), item 3 plan screens and fields, item 4 chart after unmount (Lane FK owns PayoffChart), item 5 no price names the contract, item 6 F6 parts, `PriceNotice` one rule; a entries sentence, b book "Prices as of" / "Checked at", c FB2 minors, TF defect (builder `?strategy=1` said "could not be read" with no failed request). Not built: item 6 F5 (stop sentence after an unknown move), F7.
- **PC steps, market closed (word for word):** 1. Open a paper strategy, Exit with the server stopped mid-reply, confirm a second Confirm (same tab, new tab) sends nothing; reopen builder and Positions: the lock holds; the Orderbook link re-reads. [**Do NOT double-Confirm on a real account (R1 open).**]
- **Expected texts (new, pending owner read):** "The plan watch has not been read for this trade."; "No broker is connected, so no real positions are shown." (only when the server sends no reason; otherwise the server's `real_pnl.reason`); "No price for <contract>" / "No price for <contract>, <contract>" (e.g. "No price for NIFTY 9 Nov 23500 CE"); "The market is closed." (entry dialog when `entries_sentence` is absent); "Prices as of <time>" and "Checked at <time>"; "The stop on a leg was removed with the move; set a new one on the new leg." (and the "(level 120.00)" form); refusals print every part of the server's reply. TF builder-open (paper position, four parts): "This strategy's paper position was read, but its contracts are not in the catalogue for today, so it is not shown." / "The numbers on this page are not shown, so none of them can be mistaken for current values." / "Nothing was changed and no order was placed." / "Trying again will not help until the catalogue lists these contracts."
- **Decided for the owner:** 1 lock and key live in localStorage (storage event for a second tab), in-memory fallback; 2 a Confirm sends nothing while any lock is undecided, in any tab; 3 the lock ends only by a good re-read (book moved toward the expected book, or unchanged for a read sent more than 130 s after the client gave up; `out` locks are never decided by an unchanged book); 4 only STRATEGY_VALIDATION_582 means "still being placed", 580/581/583 and every other 409 are refusals; 5 unreadable stored lock content locks every strategy until site data is cleared (fail closed, no escape button); 6 a real trade in the builder = status_word Running + no paper book + saved id equals open id; 7 a settled trade's Plan watch box shows the closed sentence; 8 Save As is blocked while the add lock stands; 9 a nameless cancelled-stop entry prints "a leg".
- **Questions the lane left to the owner:** 1 F5 stop sentence after a move of unknown outcome (Text A, decision 48: "The stop on the old leg may have been cancelled, and the new leg has no stop until you set one."; Text B pinned by test 774; recommendation: A); 2 is a permanent block on unreadable lock storage acceptable; 3 TD O-4 should the table total follow the "Add booked P&L" switch; 4 Execute page (real basket): what should a repeat press do after an unknown outcome (not built).
- **Monday (optional, live):** repeat with a real unknown reply; check "Prices as of" / "Checked at" on the book panel; builder opened for the first time after a Real exit.
- **PARKED by the lane (critical, count in the open table):** (1) CRITICAL `decideLock` verdict `changed` (`unknownLocks.js` ~102-110) ends the lock and drops the key inside the 130 s window when ANY other leg moved: **a second exit goes out with a NEW key while the first can still commit (the 27 Nov case, 2 of 4 lots twice)**; (2) CRITICAL another tab decides while the first POST is still out (`adopted()` ~143-148; `PaperStrategies.vue` ~515 `readSeq: seq-1`; removing `lock.out === true ||` leaves all 23 tests green); (3) MAJOR the builder checks the lock before `await readStops` (~743), not after, and ~769 overwrites another tab's lock; (4) MAJOR one refused storage write makes later reads ignore storage (fail open); (5) MINOR malformed entry without `before` locks forever, `at` in the future, add lock memory-only, mutations M4 and M6 not caught.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FK Chart teardown (`fix/r3-chart-teardown-1128`, Lane FK, tip `0ebb19108`)
- **In build: NO (batch 2). BASELINE, NOT IN BUILD.** Its STATUS reads "item 1: fixed, not tested; item 2: done | next push: NOT PUSHED, gate cannot pass in this container"; the branch tip ("Lane FK RESULTS: gate status") does exist on origin, so that line is older than the branch. "SAFE TO CLOSE" (its own line).
- **Board items:** none (no UX/OBS/D/I ids). Class: no chart work once the chart is removed or the DOM is gone (`PayoffChart.vue`, `AdjustPayoffChart.vue`, `StrategyPriceChart.vue`). FC2 also carries a PayoffChart createChart guard (in FC2, NOT in build); FJ says "Lane FK owns PayoffChart from here".
- **PC steps:** no PC steps in its result file (only "Next command on a machine with full history": `python scripts/orchestrator/prepush.py`, then `git push -u origin fix/r3-chart-teardown-1128`: not a PC step).
- **What it proved:** `frontend/tests/payoff-chart-teardown.test.js` 6 tests, red on base ("late redraw after teardown", `Cannot read properties of undefined (reading 'documentElement')`), green after; `charges-dialog-drafts-d13-d14.test.js` x20 = 20/20; whole frontend unit suite x3, each 331 files, 3837 tests passed; eslint clean. Gate not TOTAL PASS (3 runs; app_tests, ci_checks and frontend_unit fail on missing base ref / ECONNREFUSED 127.0.0.1:3000, none in changed files).
- **New sentences waiting for the owner's read:** none ("no new on-screen text"). **Decided for the owner:** none section. Not changed (owner lane FJ): `frontend/tests/setup.js` add `enableAutoUnmount(afterEach)`.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-FR Readers: nearest expiry, unknown kind, heartbeat (`fix/r3-readers-1128`, Lane FR, tip `8420e3b9e`, base FE2)
- **In build: NO (batch 2). BASELINE, NOT IN BUILD.** "SAFE TO CLOSE (head 2a96107b plus this docs-only commit; left: the owner-lane items 1 to 7, F3 nit, no item parked)". Paper only.
- **Board items:** #863 (screen read uses the nearest leg's expiry), #864 (reader `kinds=None`, `READER_TAKES_KINDS = True`), #860, #861 / #866, #879 (heartbeat ahead of the reader by more than 5 s reads `unreadable`), K2 F1 (entry facts with the feed down); no UX/OBS/D/I/W/T ids.
- **PC steps, market closed (word for word):** 1. Run the new tests one file at a time through `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py` for `test_screen_expiry_fr_1128`, `test_reader_kinds_fr_1128`, `test_index_one_rule`, `test_worker_heartbeat`, `test_settings_in_force`; and `python -m pytest tests/adjustment/test_playbook_eval.py`.
- **Expected texts:** until FC3's `expiry_kind_unknown` mapping is in the worker, "days left not available" stands; proposed (pending owner read, already in FC3's templates): "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value."
- **Decided for the owner:** 1 unknown-kind stop answer = `stops is None` and `days_left is None`; with a stated `days_left` it stays "stop lines not supplied"; 2 a heartbeat more than 5 s ahead keeps the answer `unreadable`, not `stale`; 3 `entry_facts_now` takes `feed` as an optional keyword so the two old callers keep working; 4 `read_tracked` reads the worker's record only for the nearest leg's key.
- **Monday (optional, live):** a far-leg-first calendar trade: the strategy page market read and the worker monitoring state show the same nearest expiry; worker clock ahead (or feed stopped) and the tick "prices are not live" on a first fill: entry facts stored with the held index value.
- **Open (known, to file):** Opus F1 (#879: a writer whose clock runs ahead and DIES reads fresh for up to 10:01:35 to 10:03:40, stale only 221 s after death; `worker_watch.py:94` sends "worker-recovered" when unreadable turns fresh); F2 (`adjustment_check.py:404` leaves stops None for an unknown kind, so an iron condor 2x-credit stop gets no result); F3 nit; price-read door guard blind spot; time of a not-live starting point not stored (needs `spot_at` on BasketFacts).
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

### R2-TT Tests: TA, TF, TE (and TB, TW): what they proved (no PC steps)
- **In build: TA (`test/r2-backend-1128`, tip `fdd76a13b`) YES; TF (`test/r2-gaps-1128`, tip `6b6263028`) YES; TE (`test/r2-named-green-1128`, tip `a0f6e7d60`) YES; TB (`test/r2-frontend-1128`, `de2f3415`) YES; TW (`test/r2-walk-builder-1128`, `dc817c2a`) YES.** Their results were taken on `70ee16ac` / the round 1 build, not on this commit. **No PC steps in the result files of TA, TF, TE; the PC does not rerun them.** TB's own step: `cd frontend && npx vitest run tests/<file>.r2-1128.test.js` for any of its nine files, or `npm run test:run` (no on-screen sentence is added).
- **TA (15 PASS, 0 FAIL):** I-02, I-03, I-39 (API half), I-44, I-55, I-58, I-59, I-63 (a sold leg's loss stop sits ABOVE the price: correct side), I-64, I-81, I-82, I-90, I-103, I-105, I-107; gate TOTAL PASS on `dcb7bc228` (jobs 2, 1854 s). **Decided for the owner (three leg-stop decisions, spec change, owner's read of the words):** 1 may a leg stop sit on the profit side (recommendation: keep saving it, but say which side); 2 the risk line for a profit-side stop (recommended: "This stop is on the profit side: it fires when this leg gains, not when it loses."); 3 a level saved with the market closed that is already beyond the price (recommended: "At the open this stop may fire at once: the last price is already beyond this level"). Also I-82 order (Active and ideas newest first by raise time; History by end time). Not covered: plan edited while a rupee alert is open; time exit with no own date; I-103 is "named tests pass".
- **TF:** I-51 stops warning PASS (three lines, each at most 80 characters, real longest 59), I-125 PASS (10 s + 4 s slack; the plan-removed direction not tested), I-80 DB half PASS (no expiry on Undo, nothing purged; Dismiss and the 30 s hold are on-screen only: the PC's T2-09); I-74 browser NOT reproduced (side observation: `/strategy/builder?strategy=1` on PATH-90 said "This strategy's paper position could not be read, so it is not shown. Try again." with no failing request: fixed own sentence in FJ, NOT in build); whole `tests_app` once: 29 failed, 8104 passed, 61 min.
- **TE:** 42 named items PASS on `70ee16ac` (I-51 half proven: fixture wording "worst case: NIFTY at zero"; I-125 proven at 15 s, product constant 10 s); full `tests_app` (fresh DB, per-file clones): 27 failed, 8090 passed, 67 min, all 27 reproduce file by file; gate TOTAL PASS on the first push (jobs 1; the earlier "NOT TOTAL PASS" was a shallow-clone failure, superseded). Defect: `tests_app` files leave rows behind and fail in sequence on one database (FD2: `OFO_TEST_DB_PER_FILE=1`; not in every run).
- **TB:** I-40, I-60, I-65, I-69, I-74, I-76, I-80, I-83, I-94, I-98 pass; D1 (Alerts History empty text: FC2 fixes) and D2 (stop-row ISO date: FA / FA2 fix) were pinned `it.fails`; whole frontend 321 files, 3775 tests passed. Decided: "Select all N shown"; the partial-failure sentence "The page could not get an answer from the server."; a Completed paper card shown with "Show closed positions" has neither Exit nor Stops.
- **TW (builder walk of the round 1 commit, called TD in its file):** I-71 FAIL (fixed in FB2 at `3a26d3a8`, in build; `LegPicker.vue:994` should call `showStrikes()`); I-21, I-41, I-66, I-86, I-88 PARTIAL; I-20, I-72, I-78, I-79, I-93 PASS. Defects to expect as known: D-TD-1 (I-71), D-TD-2 (I-86: Retry on 2 of 10 pages; FC2 fixes, NOT in build); O-1 (no "as of" on the paused line; FC2 fixes), O-2 (the Exit dialog sentence mixes plain and lakh grouping: "-20,273.50 before, -29,45,163.00 after"), O-3 ("Prices are not live" although one contract has no price), O-4 (switch OFF shows whole rupees, ON shows paise: the owner says whether intended). BLOCKED for the PC to try: "Keep this level", the re-buy of a closed contract (#725, #741), a tag or status change, D-54 Delete, D-58 quotes and the raw key `day.beforeHoliday.1500.0`. Decided: API ran with `APP_ENV=test` and the catalogue date pin (brief said development).
- **Run the PC's own check for the DB suite:** one file at a time through `scripts/orchestrator/db_run.py`; a full `tests_app` on the shared database hangs on a leaked advisory lock from about the 11th test: per-file clone required.
- On FAIL or PARTIAL write: the sentence seen, the sentence expected, known or new.

---

### Open at the end of round 2 build (known, not a round 2 failure)
Write a row of this table as "known" when the PC meets it; do not write it as a failure of the build. "In build" is for the commit `829ff65f26716f1efbcbac98ea3ba6aefdc350d9`; ask `git merge-base --is-ancestor`.

| Id | What stays open | Where it comes from | Fixed by (in build?) | What the PC may see |
|---|---|---|---|---|
| **R1** (blocks round 2) | Positions and Alerts unlock after an unknown outcome; the lane's own words: a **second exit can go out with a new key while the first can still commit** (the 27 Nov case: 2 of 4 lots, twice); another tab can decide while the first POST is still out | Z2 REVISE; FJ parked findings 1 and 2 (both CRITICAL) | FJ (NOT in build); FB and FB2 locks only on the builder page | **Do NOT double-Confirm an exit on a real account.** On paper: Exit, stop the server mid-reply, Confirm again: a second order may be stored |
| R2, R3, R4 | Majors and minors of Z2's Opus review | `r2-head`: "R2-R9 majors/minors" | not stated in the lane files I was given | the text of R2 to R4 is not in the lane result files: take it from Z2's RESULTS file, do not guess |
| R5 | A user exit on a real or unknown position is stored as a paper exit through `POST /strategies/{id}/tracking/exit` (4 to 5 orders); the paper orders route refuses it (#877) but this route does not | FD2 Opus F1 MAJOR | FD3 item 1 / I-158 (NOT in build) | the exit is accepted (200) for a real position: known |
| R6 | An old armed paper stop on a real or unknown position: FE2 (b) stops the monitor firing it; the routes list it as "not applicable" only in FD3 round 2 | FE2, FE3, FD3 | FE2 (partly in), FD3 (NOT in) | a real position may still show an armed paper stop; it must not fire |
| R7 | A failed book read (`kinds_of`) empties the worker's watch list; keep the last list 120 s, then every exit reads "the book could not be read" | FE3, FD3 item 3 | FE3, FD3 (NOT in) | the trade reads "Monitoring paused" or "not watched" after a DB outage |
| R8 | The request key lives in Redis for 600 s: a crash between the order commit and the key write can let one resend through; the durable table is migration 0061 | FD2, FD3 | FD3 (NOT in); 0061 NO PROOF | one order may be stored twice after a Redis flush |
| R9 | No server commit deadline: a request that reaches its commit after the page's 10 s timeout; FD3's 8 s `store_busy` is not on the real door | FD3 round 2 | FD3 (NOT in) | a slow commit with no sentence |
| FJ parked | Findings 3 to 5 (builder checks the lock before `await readStops`; one refused storage write makes reads ignore storage: fail open; malformed lock locks forever) | FJ | not fixed | see R2-FJ |
| FJ questions | F5 stop sentence after an unknown move (A or B); permanent block on unreadable lock storage; TD O-4; real basket repeat press | FJ | owner decides | see R2-FJ |
| FD3 | F2 minor (adopted holdings and the W-151 revision not re-checked after release); `record_basket_facts` holds a strategy lock and a connection ~3 s; `cancelled_stops` from returned ids not done; FD4's FD3 base lacks round 2 | FD3, FD4 | not fixed | no screen |
| FD2 | Real first fill (`execution_return._return`) holds a connection (ADR-330 (58)); UX-A08 plan read 15 to 60 s (FD4 measured ~83 ms warm); F6 a refused order shows no sentence; 19 routes not proven to release | FD, FD2, FD4 | not fixed | slow plan read |
| FE / FE2 / FE3 | `index_exits` merge is read-merge-write (not atomic); a trigger armed across its level fires on the next tick; FE3 F7 (non-atomic hash cleanup), F8 (kept pause starts of deleted trades); #876 cause unknown; FE2's "no report = paused" vs FE's "worker's answer stands" | FE, FE2, FE3 | partly | see R2-FE |
| FR | #879 a writer ahead and dead reads fresh for 221 s after death; F2 unknown-kind iron condor stop gets no result; guard blind spot | FR | not fixed | no screen |
| FB / FB2 | I-49 slow first prices (cause in `LegPicker.vue`); I-68 two steps are spec decisions; lock is per tab; F6, F8, F9 | FB, FB2 | owner lane | T2-11 14 s again |
| FA / FA2 | UX-A01 greyed Exit (FC2 fixes, NOT in build), #870 page wiring (`StrategyBuilderPage` line 1495, `PaperStrategies` line 169), browser check never run, `PaperConfirmDialog.vue:124` tick reset on line change (likely greyed Confirm) | FA, FA2, FB | FJ (NOT in build) | greyed Confirm |
| FC / FC2 / FC3 | UX-B06 (FC: not confirmed; FC2: "closed by FC"), UX-AF2, UX-B03 re-check not run, D-4 entry dialog wording ("Exits ..." for an entry), O-3, O-4, O-6, D-5 "Checked at" | FC, FC2, FC3 | partly | sentence names the wrong word |
| FK | Gate not TOTAL PASS in its container (missing base ref, ECONNREFUSED); `enableAutoUnmount` in `tests/setup.js` for the owner lane | FK | no | no screen |
| Test suites | 19 DB tests failing in 9 files (Z2); TF 29 failed and TE 27 failed in the full `tests_app` (named: test_alert_routes key set `position_kind`, test_background_worker x2 role CONNECTION LIMIT 5, test_egress_gate_doors x3 and test_migration_0059_last_close (container proxy; the 0059 test sends the time as text: 22000 vs 23514, a test defect), test_execution_return x2 INTERNAL_SYSTEM_002, test_route_latency_budget one statement over, test_pinned_clock, test_pool_not_held_across_market_wait, test_risk_exit_not_gated, test_slow_price_source_live_day x5) | TF, TE, Z2, FD3 item 6 (ten files fixed, NOT in build) | partly | a red test the PC has not caused |
| Set-up | Round 1: a stale vite loses new routes (404); the plan's expected strategies (155 does not exist, B-N1 changed shape, `actionable_alerts` table does not exist, `/strategies/completed` should be `/strategies/completed-strategies`); `seed_scenario.py` needs `APP_ENV=test` and `TEST_CATALOGUE_DATE` for a scenario day in the past | PC round 1, TW D-TD-3 | plan corrections | write as set-up, not product |

**Where the lane files disagree (read before writing a verdict):** (1) FE (in build) vs FE2 (partly in) on "no report": see R2-FE. (2) FD2 says the Positions/tracking exit route bypasses the real-position refusal (R5); FD3 fixes it but is not in the build. (3) FC says UX-B06 is not confirmed closed; FC2 says it is closed by FC. (4) FC3 says UX-A05 is for Lane FJ; FC2 did it and FJ brings it in; neither is in the build. (5) FD (batch 1) says plan acceptance B2 "not done"; it arrives through FC3 (item 1) as migration 0060, which is in the build. (6) FD3's own RESULTS say "(0061, additive: old code runs against the migrated database)": no proof. (7) TE's first file said "gate NOT TOTAL PASS"; its later STATUS says TOTAL PASS on the first push (jobs 1): the later line is used. (8) FK's STATUS says "NOT PUSHED", but its tip commit is on origin.

## 10. Which round runs what (grid)

R1 runs every check of sections 4 to 6 once, on commit 5fc6b102. R2 and R3 re-run the previous round's FAIL and PARTIAL checks FIRST, then the checks that first carry a new fix (sections 7 and 9).

| Checks | First carried | Re-run in |
|---|---|---|
| W-33 (nine screens after the seed), AF-03 to AF-07, SW-0 to SW-9 | R1 (Lane N in the commit) | every round |
| W-01, W-02, W-03, W-30, W-31, W-34 (plans, Plan watch, monitoring badge) | R1 | while FAIL or PARTIAL |
| W-04, W-21, W-22 and the data pulls D-1, D-2 (read-only data) | R1 | only if the data was not read |
| W-05, W-06, W-35 (Lane K, K2, L, N: what a closed market shows) | R1 | while FAIL or PARTIAL |
| W-07 owner decisions (46) to (64) | per its table | each row once; re-walk only a FAIL |
| W-09 scenario-mode try (Lane J) | R1, **[OWNER APPROVAL]** | R2 only if PARTIAL for a reason that was fixed |
| W-10 to W-20, W-23, W-28, W-29, W-32 | R1 | while FAIL or PARTIAL |
| W-25 (exit dialog market closed, (49), (60)), W-26 | R1 (Lane U2 in the commit) | while FAIL or PARTIAL |
| Section 5 reused checks (T1-14 to T4-04) | no fix needed: unrun steps only | R1, then only FAIL or PARTIAL |
| AF-07 (Real total while Zerodha is disconnected) | R1, last of the round | R2, R3 only if FAIL |
| R2-F1, R2-F2, R2-F3 (section 7) | R2 (Lanes FB, FE, FD, FA) | R3 |
| R2-FA to R2-FE, R2-TW, R2-TB, R2-TE, R2-UX (section 9); the second wave when pushed | R2 | R3 |
| TC-1 to TC-5 (the checks Lane TC could not walk) | R1 (PC) | R2 if PARTIAL |
| MONDAY (mostly optional): completing exits, Add to Paper size checks, decision (61) line, the instrument list at 08:35, T1-05 to T1-09 real proof, AF-01 across 15:30 | Monday plan | - |

## 11. The 27 Nov results that can be re-proven now, and where

The PC's final list of 27 Nov 17:44 (head ff0448b3): PASS 33, FAIL 19, PARTIAL 23, NOT_CHECKED 11, DATA 5, of 91 checks, plus 41 usability notes. FAIL: T1-05, T1-06, T1-09, T1-15, T1-20, T1-22, T2-01, T2-02, T2-04, T2-08, T2-10, T2-13, T2-19, T3-13, AF-01, AF-02, AF-08, AX-05, AX-14. No new FAIL or PARTIAL id appeared in the PC's comments of the night (03:11 and 04:20 IST).

| 27 Nov FAIL (condition) | Covered by |
|---|---|
| T1-20 (feed stopped: "as of" missing) | T1-20 (section 5) |
| T2-08 (prices not live in the Exit dialog) | W-25 A to D; the completing exit and two-tab lock: Monday |
| T1-22 (exit sentence without order number) | Monday: no exit completes with the market closed |
| AF-02 (API restart after the close: held 15:30 closes lost) | W-33 (after the seed), SW-0 |
| AF-08 (market closed: Add to Paper without tick box) | W-33 (Lane N: no tick box; market-closed sentence), W-35 |
| AX-05 (no banner on Live Strategies after close) | W-33 |
| AF-01 extra (leg-picker prices change after the close) | W-33 (leg picker line); the freeze across 15:30: Monday |
| T1-15 (totals differ) | W-06 |
| T2-01, T2-02, T2-04, AX-14 (Plan watch "not available") | W-02, W-03, W-31 |
| T2-10 (5000 lots accepted) | W-05 (Settings 100, market-closed sentence); size sentences Monday |
| T2-13 ("Acted on" after Cancel) | W-10, decision (53) |
| T2-19 (Reset markers) | W-28 step 1 (Lane R3 is in the commit), W-30 step 4, W-01 step 4 |
| T1-09 (alerts stay Active after last leg exited) | W-13 (history part); exit part Monday |
| T1-05 to T1-08 (plan-stop alert) | W-09 (scenario-mode try); Lane Q3's worker-chain test (cloud); Monday T1-05 is the real proof |
| T3-13 (wording: D-52, D-54, D-58) | T3-13 (section 5) |
| N-07 to N-11 (instrument list before 08:30) | Monday (decision (61) and the 08:35 refresh) |

## 12. Report at the end of each round

One line to the coordinator: `ROUND N done HH:MM | commit | PASS n FAIL n PARTIAL n BLOCKED n | known F1/F2/F3 seen n | new observations n | next round`. The PR #722 status comment follows rule 6 of section 0.

## 13. The message for each round (the owner sends it to the reused PC session)

The PC session is the same one all weekend: it keeps what it learned in the round before, but it re-reads this plan file at the start of each round and never relies on memory for expected texts. Lines marked **[OWNER APPROVAL]** wait for the owner's typed "yes". The owner starts each round (Saturday 08:00, Saturday 21:00, Sunday 12:00). Replace `N` and the bracketed items for the round.

```
You are still the owner's PC session for OptionsForOptions2; this is round N of the closed-market weekend test.
Paper only: never place, send or confirm a broker order. The market is closed; there is no Kite login and no live feed.
Nothing starts until the owner starts the round and gives each approval himself.
ROUND 2 COMMIT (frozen 28 Nov): 829ff65f26716f1efbcbac98ea3ba6aefdc350d9 on integration/weekend-r2-1128; read the page "Version 6b: READ THIS FIRST" before anything else. CLOUD FIRST (version 6): run ONLY the PC list of the page "Version 6: CLOUD FIRST" (the set-up, the PC ONLY checks, the cross-check sample); do NOT run any other check on the PC: they are proven in the cloud. The steps below apply to the checks on that list.
Read docs/process/test-plan-weekend-2026-11-28.md on branch docs/test-plan-weekend-1127: section 0 (rules), section 2 (set-up),
the checks of this round, section 13.
1. Look at the database link and count the ofo_app connections (limit 10, shared). Keep your old local test branch test/screen-2026-11-27
   (head bdb0d126) exactly as it is; never reset it.
2. Back up ofo_dev on the VPS over SSH (pg_dump -Fc), copy to %USERPROFILE%\ofo-backups, check the size is equal on both machines and
   pg_restore --list shows TABLE DATA entries above 0. If the check fails, stop and report.
3. Pull the commit: git fetch origin integration/weekend-1127; git checkout -b test/weekend-rN [round 1: 5fc6b1023234b9efb948db731d903ad957f341c1;
   rounds 2 and 3: the commit the coordinator sends]; git rev-parse HEAD must equal it. There is no tag.
4. Migration 0059_last_close (round 1 only; rounds 2 and 3: alembic current must end 0059_last_close (head)): [OWNER APPROVAL] then run the
   section 2 step 3 command. Never run alembic downgrade. Restore from the backup only with [OWNER APPROVAL]. A migration without a written
   old-code-safe proof (for example 0060, plan acceptance) is not applied; its checks are BLOCKED.
5. Round 1 only, before any restart: section 2 step 5: the DB tests (5a), the seed dry run with --check (5b: expect "would write 17",
   "skipped 0"), then [OWNER APPROVAL] the real seed (5c: expect "written 17"). Write the lines printed.
6. npm ci and npm run build in the serving checkout; restart the API, then the worker, then the feed, THEN the frontend server (vite): vite reads the API route list once at start. Ctrl+F5; health page healthy. Round 2: section 2 "Round 2 additions" R2-0 to R2-5 (confirm each new route answers through the frontend's address; migration 0060 with [OWNER APPROVAL]; Redis up).
7. Section 2 steps 8 and 9 (confirm the commit, sanity). Then run the checks of section 4 in order (W-33 first), then section 5 and 6.
   [Rounds 2 and 3: FIRST re-run every FAIL and PARTIAL of the previous round; then sections 7 and 9.] Before each block: look at the link
   (a dropped link = "infra, re-run", not FAIL) and count the ofo_app connections (the two-user speed run only when fewer than 6 are in use).
   W-09 only with [OWNER APPROVAL]. Round 1 also: the two data pulls of section 8 (read only; words and counts only; never a price value,
   address, login, port or key).
8. Every result: the commit, state (Fixed, not tested / Passed in cloud / Passed on PC (market closed) / Approved (PC, live)), PASS only if every
   step ran and the expected text was seen; otherwise PARTIAL naming the unrun steps, or BLOCKED naming what blocked it. Never NOT CHECKED for
   lack of time. Look in Alerts Active AND History. F1, F2, F3 seen = "known F1/F2/F3", not a FAIL. New problems are observations (screen,
   exact text, time); awkward things are usability notes (UX-nn).
9. Post a status comment on PR #722 every 60 minutes in the fixed short format (section 0 rule 6).
10. AF-07 last [round 1].
11. Stop at [round 1: Sat 12:00; round 2: Sun 01:00; round 3: Sun 16:00] or when the list is done. Final message: the one-line round report
    (section 12) and the list of FAILs for the next round. Fix nothing; change no code; open no PR.
```

## 14. Intake: AX-01 to AX-14 of 27 Nov (the PC's night list)

AX-08 to AX-12 are features that are **not built, not in this weekend, no check** (AX-09 #433, AX-10 #751, AX-11 and AX-12 #750; AX-08 spec only). The 41 usability notes are in section 9 (R2-UX).

| 27 Nov id | Status | Weekend | Monday |
|---|---|---|---|
| AX-01 index quote older than 60 s is not live | NOT CHECKED | no (needs the relay, not built); R2-F2 shows the silent-feed state | only if the relay exists, else BLOCKED: relay not built |
| AX-02 payoff hover stays through live refreshes | PASS (mouse) | keyboard variant, builder payoff chart, market closed OK: write what you see | - |
| AX-03 no plan, no adjustment limit | PASS | - | - |
| AX-04 bid and ask recorded | DATA | - | optional: last traded price below the bid on the Option Chain |
| AX-05 prices frozen label on Live Strategies | FAIL | W-33 | - |
| AX-06 Delete has no extra read | DATA (about 2 s) | repeat three tries, write the seconds | - |
| AX-07 Pick from Option Chain in the picker | PASS | - | - |
| AX-08 to AX-12 | not built | none | none |
| AX-13 profit-target amount on the Stops panel | PARTIAL | W-03 (Plan watch loaded) then the Stops panel | - |
| AX-14 Plan watch rows | FAIL | W-03, W-31, section 6 AX-14 | - |

## Appendix A. New on-screen sentences waiting for the owner's read

Sentences of the round 1 build, word for word from the lanes' result files (file and line given; the server templates are also pinned `reviewed: "pending owner read"` in `tests/errors/template_pins.json`). Round 2 sentences follow the table.

Server templates are also pinned `reviewed: "pending owner read"` in `tests/errors/template_pins.json`.

| # | Screen | Sentence | Lane | File:line |
|---|---|---|---|---|
| B1 | Builder, contract list (before today's list loads) | "Contract list of {day}. Today's list loads at about {time}." | J2 | RESULTS-lane-j2.md:117, 163 |
| B2 | Paper order door, leg over lot limit | "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)." Next: "Reduce {contract} to {room} more lots or fewer." | K | RESULTS-lane-k.md:44 |
| B3 | Paper exit over order limit | "An exit of {lots} lots on {contract} is above the most one order can carry ({max_lots} lots)." Impact: "Nothing was exited." Next: "Exit {max_lots} lots or fewer now, then exit the rest in further orders." | K | RESULTS-lane-k.md:45 |
| B4 | Paper entry price | "The entry price for {contract} must be above 0." Next: "Type a price above 0 for {contract}, then add it to paper again." | K | RESULTS-lane-k.md:46 |
| B5 | My Strategies / Completed Strategies | "Select all {n} of the {m} shown" | L | RESULTS-lane-l.md:35 |
| B6 | My Strategies | "Loading your strategies..." | L | RESULTS-lane-l.md:75 |
| B7 | Create Strategy | "Choose an expiry first." | L | RESULTS-lane-l.md:75 |
| B8 | Create Strategy | "Waiting for the contracts to load." | L | RESULTS-lane-l.md:75 |
| B9 | Create Strategy | "Waiting for the index price." | L | RESULTS-lane-l.md:75 |
| B10 | Home, Positions totals (item 4) | "Includes N closed strategies." and "N strategies left out: their prices are not live." (also "1 strategy left out: its price is not live.", "{count} strategies left ..." in owner-questions-lane-r.md:148) | L | RESULTS-lane-l.md:75 |
| B11 | Price banner (all price screens) | "Prices are not live. Figures are as of HH:MM:SS IST." / "Prices are not live." | N | RESULTS-lane-n.md:111 |
| B12 | Price banner, mixed times | "Market closed. Prices are from 15:30:00; 1 leg as of 26 Nov, 15:29:59." | N | RESULTS-lane-n.md:112 |
| B13 | Price banner, mixed times | "Market closed. Prices are from 15:33:48; 1 leg as of 15:59:10." / "2 legs as of ..." | N | RESULTS-lane-n.md:113 |
| B14 | Load / check time lines | "Checked at HH:MM:SS IST" | N | RESULTS-lane-n.md:114 |
| B15 | Stops panel, closed market | "NIFTY last 25,607.20 as of 15:58:01" | N | RESULTS-lane-n.md:115 |
| B16 | Paper P&L total | "Paper P&L paused - prices not live" (no ", as of" clause when time unknown) | N | RESULTS-lane-n.md:116 |
| B17 | Plan sheet | "Put back to the playbook's values:" | O | RESULTS-lane-o.md:35 |
| B18 | Plan sheet | "Switched on again:" | O | RESULTS-lane-o.md:35 |
| B19 | Plan sheet | "Nothing differed from the playbook, so nothing was put back." | O | RESULTS-lane-o.md:35 |
| B20 | Alerts, rule line | "<Plan loss stop | Plan profit target | Plan rupee stop | Plan rupee target | Plan time exit | Adjustment rule T-xx>: <value> (rule <threshold>)" | O | RESULTS-lane-o.md:36 |
| B21 | Alerts History headings | "Answered alerts", "Stops and expiry settlements" | O | RESULTS-lane-o.md:37 |
| B22 | Alerts History empty | "No answered alerts yet." | O | RESULTS-lane-o.md:37 |
| B23 | Leg stop alert (new) | "Leg stop on X: fires when the price rises above L" (with live price add "; price now P"; below: "falls below") | O | RESULTS-lane-o.md:38 |
| B24 | Leg stop alert (old) | "Leg stop on X: price above L" | O | RESULTS-lane-o.md:38 |
| B25 | Stops panel labels | "Stop when the price goes", "Stop price" | O | RESULTS-lane-o.md:80 |
| B26 | Leg list, price replaced | "Your price for leg N was replaced by the captured price P, because <you changed the expiry | Shift/Width/Hedge moved the leg to another contract | you moved the strike>." | O | RESULTS-lane-o.md:81 |
| B27 | Leg list, price removed | "Your price for leg N was removed, because <reason> and the new contract has no live price right now." | O | RESULTS-lane-o.md:82 |
| B28 | Plan watch, first read | "Loading the rule check..." | R | RESULTS-lane-r.md:378 |
| B29 | Plan save refusal (percent stop) | "The stop could not be saved: whether this trade expires weekly or monthly could not be read." Next: "Try again when prices update, or save the stop as a rupee amount." (`plan_save_percent_stop_not_read`) | R2 | RESULTS-lane-r2.md:25 |
| B30 | Stops, kind unknown | "Stop not shown: whether this trade expires weekly or monthly is not known right now" | R2 | RESULTS-lane-r2.md:27 |
| B31 | Stops, catalogue unreadable | "Stop not shown: the contract list could not be read, so the expiry type is not known" | R2 | RESULTS-lane-r2.md:27 |
| B32 | Real P&L, no figure | "Zerodha's reply for {contract} lacks a figure needed to check its P&L; no figure is shown." | S | RESULTS-lane-s.md:38 |
| B33 | Real P&L, mismatch | "Zerodha's P&L for {contract} does not match its own trade values; no figure is shown." | S | RESULTS-lane-s.md:39 |
| B34 | Real P&L, shared contract | "This contract is shared (with another strategy or outside lots); Zerodha reports one P&L for the whole contract, so no split is shown." | S | RESULTS-lane-s.md:40 |
| B35 | Real P&L, part closed | "Part of {contract} was closed today on Zerodha and is reported apart, so no figure is shown for it." | S | RESULTS-lane-s.md:41 |
| B36 | Real P&L, pending | "This contract is not yet confirmed, so no P&L is shown." | S | RESULTS-lane-s.md:42 |
| B37 | Real P&L, stale | "Zerodha was last read more than {seconds} seconds ago, so no figure is shown until it is read again." | S | RESULTS-lane-s.md:43 |
| B38 | Real P&L total, empty | "No real positions are open in your strategies." | S | RESULTS-lane-s.md:44 |
| B39 | Real P&L total, partial | "{missing} of {total} contracts have no figure, so no total is shown." | S | RESULTS-lane-s.md:45 |
| B40 | Real P&L total note | "Excludes contracts not in a strategy here and contracts closed today." | S | RESULTS-lane-s.md:46 |
| B41 | Real P&L caption | "Zerodha, as at {time} IST" | S | RESULTS-lane-s.md:37 |
| B42 | Stops panel / fired-stop warning | "If this stop fires, the sold {leg} is left without protection." | V | RESULTS-lane-v.md:47 |
| B43 | same | "If this stop fires, the sold options {legs} are left without protection." (several legs later reads "these sold options are left with less protection: ...", RESULTS-lane-v.md:58) | V | RESULTS-lane-v.md:47 |
| B44 | same | "Max loss now: Rs {amount}." / "Max loss now: none (the book shows a profit of at least Rs {amount})." | V | RESULTS-lane-v.md:47 |
| B45 | same | "Max loss then: Rs {amount} (worst case: {index} at zero)." / "Max loss then: none (the book shows a profit of at least Rs {amount})." | V | RESULTS-lane-v.md:47 |
| B46 | same, sold call | "Max loss then: no upper limit (worst case: {index} keeps rising)." (owner gave no exact text; also "Max loss now: no upper limit.") | V | RESULTS-lane-v.md:47, 58 |
| B47 | same | "Max loss now: could not be worked out." / "Max loss then: could not be worked out." | V | RESULTS-lane-v.md:47 |
| B48 | Closed trade plan line | "stop Rs {amount}", "no stop", "stop not available", "target Rs {amount}", "no target", "target not available", "Plan: {stop}, {target}.", "No plan was set for this trade.", "your exit", "your stop", "expiry settlement", "Closed by {how} at {time}.", "Closed by {how} on {day} at {time}.", "Closed by {how}.", "How this trade ended is not recorded." | V | RESULTS-lane-v.md:47 |
| B49 | Builder, Plan button | "Plan"; "Could not open the plan. Try again." | V | RESULTS-lane-v.md:48 |
| B50 | Stops panel, while working | "Working out max loss for this stop..." | V | RESULTS-lane-v.md:69 |
| B51 | Fired stop, NOT built (proposal) | "The sold <leg> is now without protection. Max loss now: Rs <amount> (worst case: <index> at zero)." | V | RESULTS-lane-v.md:67 |
| B52 | Fired stop, NOT built (proposal M-A) | "If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25): the worst case if NIFTY fell to zero, with NIFTY 1 Dec 25750 PE sold and no bought put protecting it." | M | RESULTS-lane-m.md:166 |
| B53 | Fired stop, NOT built (proposal M-B) | "If this stop fires, NIFTY 1 Dec 25750 PE is left sold with no bought put protecting it. Worst case, if NIFTY fell to zero: a loss of Rs 16,62,316.50 (now Rs 1,732.25)." | M | RESULTS-lane-m.md:167 |
| B54 | Paper exit (builder/Positions) | "An exit is already being sent for this strategy." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:31 |
| B55 | same | "Tick a leg to exit." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:31 |
| B56 | same | "Exit placed on paper (order n)." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:31 |
| B57 | same | "The exit was not stored. You can try again." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:31 |
| B58 | Exit on untouched leg | "This leg has a change waiting; review or discard it first." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:216 |
| B59 | same | "The change waiting on <legs> was not kept because the trade changed; stage it again." | U-hotfix | RESULTS-lane-u-hotfix-1127.md:216 |
| B60 | Exit all dialog | "Exit all closes every open leg. The change waiting on <legs> is not sent and will be discarded." | U2 | RESULTS-lane-u2.md:45 |
| B61 | same | "The change waiting on <legs> was discarded." | U2 | RESULTS-lane-u2.md:45 |
| B62 | same, unknown outcome | "The change waiting on <legs> was not sent; it is kept until the exit's outcome is known." | U2 | RESULTS-lane-u2.md:45 |
| B63 | same, not stored | "The exit was not stored. The change waiting on <legs> is back, unchanged." | U2 | RESULTS-lane-u2.md:45 |
| B64 | Plan sheet gate | "Target and Target (Rs) show different values." / "Stop and Stop (Rs) show different values." (templates 710/711) | W | RESULTS-lane-w.md:51 |
| B65 | Positions/Live row, real position | "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only." (`position_kind_real`) | Y | RESULTS-lane-y.md:48 |
| B66 | same, unknown | "Cannot tell whether this is a real or a paper position, so Exit and Stops are not shown. Check it in Kite." (`position_kind_unknown`) | Y | RESULTS-lane-y.md:48 |
| B67 | Monitoring badge | "Not being watched: no worker has reported in the last 2 minutes." (plus badge words "Monitoring paused", "Health unknown"; every `monitoring_*` catalogue sentence and `lib/monitoringState.js` fallback words are pending read, text in `explanations.py`) | Y | RESULTS-lane-y.md:37, 41 |
| B68 | Alerts (side closed, stop fired) | Pins pending read, text not quoted in RESULTS: `stop_fired_note`, `stop_fired_note_with_line`, `alert_title_unnamed`, `alert_side_closed_text`, `plan_sheet_reset`, `plan_sheet_reset_confirm`, `labels:plan_sheet`, "Deleted" (`change_deleted`), "Restored" (`change_undeleted`) | J | RESULTS-lane-j.md:724-726 |
| B69 | Spec-silent controls (REQ lines) | Sentences listed in the table, e.g. REQ-009 AC-11 'Unknown address shows "Page not found" with one "Go to Home" link' | U | RESULTS-lane-u.md:198-215 |
| B70 | Chain | T-Q10 sentences ("Waiting for live data.", "No strikes match the filters.", "The expiries could not be read, so no chain is shown.", four rows-missing sentences) adopted, pending read | U / T | RESULTS-lane-u.md:144; owner-questions-lane-t.md:17 |

Lane S states table also lists 10 new pins "waiting for the owner's read" (RESULTS-lane-s.md:89). B1-B70 count includes grouped rows.

**Round 2 (pending owner read):** FA: "No price for N of M legs; the server prices the exit when you confirm."; "The time of the price is not available."; "Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago."; "Price as of HH:MM:SS IST, N seconds ago."; "Placing exit..."; "NIFTY: the last close is not available."; "The market is closed. A level you save is checked from the next market open; the last close is shown for reference."; "NIFTY 22300 PE 3 Nov" (stop row date). FB: "The last paper order got no answer and may be stored. It is not sent again until the Paper book has been read: open the strategy again to check."; "Working out the outcome..." on each leg row. FC: "Now <value> as of <time> IST"; "Now: not read yet"; "This approach is not built because the whole trade would not be in profit with every open leg closed at its planned price."; "Exits of a real-mode trade cannot be read here yet.". FD (not built): "{line}; seen by the check at {time} IST" / "{line}; seen by the check on {date} at {time} IST". Lane TC wording defects (for a fix lane): D-6 the doubled OI sentence; D-11 the paused text twice; D-12 "You can still confirm." beside a disabled Confirm.
