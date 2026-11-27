STATUS 06:40 | version 3 (round 1 = commit 5fc6b102) | covers: the commit above, Lane TC walk (test/r2-walk-close-1128 8bbd6fbb), round 2 branches fix/r2-exit-stops-1128, fix/r2-builder-1128, fix/r2-small-screens-1128, fix/r2-backend-1128-fd, test/r2-frontend-1128, test/r2-named-green-1128; NOT PUSHED at 05:18: fix/r2-index-exit-watch-1128, fix/r2-exit-stops-2-1128, fix/r2-builder-2-1128, fix/r2-pages-1128, fix/r2-plan-screens-1128, fix/r2-backend-2-1128, test/r2-backend-1128, test/r2-walk-builder-1128 | next version when those branches land (before round 2, Sat 21:00)

# Test plan for the closed-market weekend, 28 and 29 Nov 2026 (rounds 1 to 3)

Version 3, Sat 28 Nov 2026, morning IST. Written by Lane X2 (documents only; no product code read or changed).
For the owner's PC session. The market is closed until Mon 30 Nov 09:15. Three rounds, each started by the owner; the **PC session is reused** for all three; the message for each is in section 13. The app on the PC has 9 running paper trades, no Kite
login and no live feed. **Paper only: never place or send a broker order.** Monday's live plan is `docs/process/test-plan-2026-11-30.md`.

Version log: v1b Fri 19:40; v1 Fri 22:30 (all lane result files read); **v2 Sat early morning: round 1 is the commit named in section 1, only checks that commit can pass, every check names its board items, the three open findings F1 to F3 are known and not a round 1 failure, two PC data pulls (section 8), round 2 checks (sections 7 and 9).** Next: the round 2 update when the coordinator sends the round 2 branch list. **v3 (this file): a one-page "What to read before 08:00" for the owner; SW-2, SW-6, T1-20 and the sweep corrected against Lane TC's walk of the round 1 commit; the five checks TC could not walk are PC checks in round 1 (TC-1 to TC-5); the round 2 section is built from the fix lanes' result files (one check per fix).**

## What to read before 08:00 (for the owner; about 10 minutes)

Round 1 starts at 08:00 on the commit `5fc6b102`. Three things need your eyes first; the details are in the sections named at the end of each line.

### 1. The three open review findings (known; not a round 1 failure)
Lane Z's independent Opus review of the stop and exit paths says REVISE. The three findings are open in the round 1 build and are fixed (or being fixed) in round 2:
- **F1** After an exit whose outcome is unknown, the page can unlock Exit after 5 seconds although the server may still commit the first exit, so a second partial exit can double-exit (2 of 4 lots twice = 4 lots). Round 2 fix: Lane FB `fix/r2-builder-1128` (the unlock now waits 120 seconds); the server-side request key is Lane FD's, not done. Section 7, R2-F1.
- **F2** When the index price feed is silent, an index exit may never fire while the trade still reads "watched" (the 23 Nov case: NIFTY ticks stopped at 15:15:18). Round 2 fix: Lane FE `fix/r2-index-exit-watch-1128` (not on origin at 05:18). Section 7, R2-F2.
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
    `| Check | Items proved | Build head | What I did on the screen | What the screen showed (exact text) | Screenshot file(s) | PASS / FAIL / PARTIAL (unrun steps) / BLOCKED (what) | State (one of the four) | Build commit | Time IST |`. Screenshots stay on the PC (never copy images into the repo).

## 1. Round 1 and what the build carries

**Round 1 build: commit `5fc6b1023234b9efb948db731d903ad957f341c1`** (short `5fc6b102`) on branch `integration/weekend-1127`. **There is no tag** (a tag push is refused for build lanes): every result names the commit. The branch tip has moved on (it now holds only Lane Z's documents); the PC takes the commit above, not the tip.

| Round | When (IST) | Build | What it is for |
|---|---|---|---|
| 1 | Sat 28 Nov 08:00 to 12:00, started by the owner | commit 5fc6b102 | the checks of section 4 and section 6 (market closed, paper only), the two data pulls (section 8) |
| 2 | Sat 28 Nov 21:00 to Sun 01:00 | the round 2 build (not on origin yet) | round 1's FAILs again, the three known findings F1 to F3 (section 7), the fix lanes FA to FE (section 9) |
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
   5a. DB tests: `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_migration_0059_last_close.py tests_app/test_basket_facts_unheld_index.py tests_app/test_close_freeze_routes.py tests_app/test_closed_label_route.py` (all pass).
   5b. Dry run: `set PYTHONPATH=backend` then `python -m ofo_app.last_close_store seed <snapshot folder>\\close-2026-11-27.json --check` (the folder where the PC saved Friday night's snapshot). Expected: "would write 17", "skipped 0"; the "database:" line must be the production database; "keys in the first row" and "mapping chosen" show price from the tick price and price_at from the tick's own time; the first row shows a 27 Nov 15:30:00 +05:30 time. If a field is reported twice, re-run with `--map price_at=<key>` (or `price=`).
   5c. **[OWNER APPROVAL]** Real run (the same command without `--check`): "written 17", "unchanged 0", "skipped 0"; a second run prints "written 0", "unchanged 17".
6. **Frontend:** `npm ci` then `npm run build` in the checkout the app serves from (never in a worktree).
7. **Restart order: API, then worker, then feed.** Ctrl+F5 once. No Kite login (weekend). The feed process is started and stopped by the PC for W-25: RESULTS gives no start command ("stop the FEED process"; "FEED_MODE=bus as today"): write the command you use in the log. With the feed stopped the API reads NOT_CONNECTED within about 3 to 5.5 s.
8. **Confirm the build:** `git rev-parse HEAD` equals `5fc6b1023234b9efb948db731d903ad957f341c1`; the health page answers `{"status":"healthy","database":"connected"}`; the health reply names which contract list is in use (decision (61)): write it.
9. **Sanity (2 minutes):** Positions > Paper lists the 9 running paper trades; Alerts > Active opens and its row count equals the bell number; no red error box on Home. If something is red, that is observation O-01.

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


### W-01 Plan save, change and reset, read back in three places
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

### W-02 Plan watch load: one request at a time, never "not available"
- **Board items:** T2-01, T2-02 (FAIL); N-12; OBS-18 (answers 7 to 20 s); issue-list rows 8 and 22 (34 requests a minute)
- **Proves:** Lane R plan-watch load hotfix (27 Nov n=204 requests in about 6 minutes; N-12 "answer takes 15-20 s"; T2-01/T2-02 FAIL).
- **Type:** Functionality / Screen. **27 Nov result:** T2-01 FAIL, T2-02 FAIL (0 of 10 boxes filled within 60 s), AX-14 FAIL. **First carried:** R1 (Lane R 8b45807a; Lane R2 `hotfix/plan-read-1127` 1d0f56e7, Lane R3 3260e094: both in the commit).
- **Steps:** 1. Open Positions > Paper with 5 or more planned rows. Open DevTools > Network, filter `plan-watch`, leave it 3 minutes. 2. Count: requests pending at one moment (expected: at most 1) and in all (expected: about 9 or fewer). Rows keep their numbers and show "Updating the numbers..." and never "not available". 3. Switch to another browser tab for 2 minutes: no plan-watch requests; come back: exactly one starts. 4. Open the builder of a planned strategy: its box reads about every 15 s.
- **Expected texts:** "Updating the numbers..." (never "not available" when the server answered); a box before its first rows reads "Loading the rule check..." and never "Updating the numbers..." first.
- **Write down:** the two counts, time to first rows per box, any "not available".

### W-03 Plan watch box, weekend wording (market closed)
- **Board items:** T2-01, T2-02, T2-04 ("Not applicable" line), AX-14, AX-13
- **Proves:** Lane R box rendering and AX-14; T2-01, T2-02, T2-04 (the "Not applicable" line), AX-14.
- **Type:** Screen. **27 Nov result:** FAIL ("not available right now", no trigger rows). **First carried:** R1 (Lane R).
- **Steps:** 1. Builder of a strategy with a plan: first the box says **"Loading the rule check..."**; the answer then shows its rows with the as-of time. 2. Positions with plan rows: each compact box shows rows, not "not available", after its turn in the queue. 3. With no prices (weekend) the rows show **Paused** or **Not checked** with the server's text, never an empty box. 4. Stop the backend for one minute: the last rows stay, marked **"Could not refresh the rule check..."**, with the as-of time. 5. Open the console: a `plan watch: line N degraded ... field(s): ...` warning, if shown, names the field; write the line and the raw 200 body of `/api/strategies/<id>/plan-watch`. 6. Builder `?strategy=<id>` for A-H #209: Stops panel and plan rows show; **16 rows marked Not checked**. 7. T2-04 part: a trade whose one side is closed: the row, the two answers and the "Not applicable" line (27 Nov: the line could not show because Plan watch was unavailable).
- **Write down:** every box's words, the console line, step 6's row count.

### W-04 Strategy 155: does the server hold the adjustment rows? (D-27, read-only)
- **Board items:** D-27, T2-14
- **Proves:** D-27 / T2-14 (27 Nov PARTIAL: raw JSON not saved, strategy 155 absent). **Type:** Functionality. **First carried:** no fix needed (read-only). Lane R's steps, word for word:
  1. Log in to the app in the PC's browser. Open the builder on trade 155 and open "Adjustment history". DevTools > Network, filter `adjustment-history`.
  2. The request is `GET /api/strategies/155/adjustment-history` (reads only). Or paste that URL in the address bar of the same logged-in browser.
  3. Copy the full JSON reply to `d27-155-adjustment-history.json` (keep the status code).
  4. Write: (a) `rows.length`; (b) per row `step` (entry / adjustment / settle / stop), `number`, `at`, `is_exit`, `orders[].kind/side/quantity`; (c) `totals.adjustments_used` and `totals.adjustments_max`; (d) what the builder's section shows: the "no step recorded" line, the error line, or N rows.
  5. Rows in the JSON but the section empty = a screen defect. A 404 or `rows: []` = the server has none: then open `GET /api/paper/strategies/155`, save it as `d27-155-paper-book.json`, write `orders[]` (count, kind, time) and `status_word`.
  If strategy 155 does not exist on the PC: PARTIAL and write that; repeat with any strategy that has an adjustment.

### W-05 Order limits: what can be seen with the market closed (Lane K)
- **Board items:** T2-10 (FAIL); ADR-330 (50), (51), (52); Lane W item 15; triage C-item 1
- **Proves:** T2-10 (27 Nov FAIL: Add to Paper accepted 5000 lots on one leg with no refusal); decisions (50), (51), (52); Lane W item 15; Lane K. **Type:** Functionality / Screen. **First carried:** R1 (Lane K `fix/order-limits-1127` 8880aa24).
- **Why short:** Lane K's RESULTS: "Add to Paper is refused by the existing market-closed gate before any size check, so the size sentences cannot be seen closed." The size checks (101 lots; 60 then 50; an exit above the freeze) are **MONDAY ONLY** (Monday plan, T2-10). Do these two steps:
- **Step 0 (Lane K, word for word): count the stored freeze quantities for the running indexes.** On the PC database: `SELECT exchange_segment, count(*), max(file_date) FROM public.exchange_freeze_limits GROUP BY 1;` Write the rows. If there are no rows for an index (SENSEX has none: no BSE_FO source), "exit above freeze" for that index is **not testable on the PC (BLOCKED: no stored freeze quantity), not FAIL**; the lots limit is testable on every index (Monday).
- **Step 1:** Settings page: "Most lots in one leg" shows **100** (it was 10,000). If it shows anything else: FAIL, write the number.
- **Step 2 (Add to Paper with the market closed):** put one draft leg in the builder (5000 lots), press Add to Paper, read the answer. Expected today (Lane N's walk, and Lane U's code): the server's market-closed sentence, nothing in the book. Write the sentence word for word. (Lane U's code text, not in its RESULTS: "The market is closed. Orders can be placed once it opens." with "No order can be placed while the market is closed." and "Return during market hours and execute again." If the screen differs, that is an observation.)
- **Expected sentences (for Monday; pending owner read):** "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)."; "An exit of {lots} lots on {contract} is above the most one order can carry ({max_lots} lots)."; "The entry price for {contract} must be above 0."

### W-06 One P&L number in the places (Lane L), prices frozen
- **Board items:** T1-15 (FAIL); D-06, D-07, D-40, D-41, D-56, D-68; ADR-330 (62); UX-32; AF-07 (also AF-05, T1-16)
- **Proves:** D-06, D-07, D-41, D-56, D-68, D-40; T1-15 (27 Nov FAIL: Home total and Positions Paper total differ in the same minute; they cover different trade sets); decision (62); UX-32; AF-07 (Positions with Zerodha disconnected). **Type:** Screen. **First carried:** R1 (Lane L `fix/pnl-totals-1127` d94ca716).
- **Steps (market CLOSED, frozen prices; Lane L, word for word):** 1. Open Home, note "Total P&L" (call it X). Open Positions, note "Paper P&L" with its "(after charges)" label: it must equal X to the paisa. 2. Open Live Strategies and My Strategies: the sum of the rows listed with a figure plus the settled ones equals X unless the line "N strategies left out" says otherwise. 3. Tick "Show closed positions": the number in "Includes N closed strategies" equals the number of closed rows listed; if not, the line is hidden (by design). 4. Completed Strategies: with a held-at-broker row, the label reads "Select all N-1 of the N shown" (27 Nov UX-AF2: "Select all 16 shown" while 17 were listed). 5. (UX-32) Open Home, change a trade in another tab, return to the Home tab: the Total P&L updates within a second without a reload. 6. (AF-07) Positions with Zerodha disconnected shows "-" and the connect sentence under Real P&L. Also, for one running trade X1 and one closed trade Y1, write the figure in the five places (Live card, My Strategies row, Positions, Home, builder) in the same minute.
- **Expected texts:** "Select all {n} of the {m} shown" (for example "Select all 16 of the 17 shown"); "Includes N closed strategies"; "N strategies left out"; "Paper P&L paused - prices not live"; "Paper P&L" with "(after charges)" once, never twice. If it still differs while CLOSED: write both figures and the "Includes/left out" lines of each page. (Monday: reload Home then Positions within 10 seconds; one price tick of difference is allowed.)

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

### W-09 Plan-stop alert in scenario mode (market closed): try it, Monday T1-05 is the real proof
- **Board items:** T1-05 to T1-08; ADR-330 (47)
- **Proves:** T1-05 to T1-08 chain (stop level crossed, one alert row in the plan's rule list). **Type:** Functionality. **First carried:** R1 (Lane J `hotfix/loss-stop-1127` 3e0b9780).
- **Honest limits:** Lane J's RESULTS: "Not proven end to end here: I did not run this chain with a plan stop on a path scenario; whether a PATH fixture reaches a given rupee level mu[st be checked]." There is **no price-replay tool** (cancelled; Lane Q2). The scenario worker exists (`python -m ofo_app.background` with `OFO_SCENARIO`), and ticks only on PATH scenarios. If the try does not give an alert, the result is **PARTIAL: tool limit, Monday T1-05** (not FAIL).
- **[OWNER APPROVAL] before step 1:** scenario mode changes `APP_ENV` for the API and the worker and seeds a trade into `ofo_dev` (the database with the 9 running paper trades; the seed script refuses any other database). Restart the normal app afterwards.
- **Steps (Lane J (b) and (c), word for word):** set `APP_ENV=development` and `OFO_SCENARIO=PATH-<nn>` for both processes (`backend/ofo_app/scenario_mode.py`); seed the trade with `python scripts/orchestrator/dev_run.py <checkout> python scripts/seed_scenario.py PATH-<nn>`; save a plan with a Stop (Rs) on "Scenario PATH-<nn>"; move the market frame by frame with `POST /api/scenario/frame` (the worker reads the shared frame index before every cycle). A frame past the stop must give one alert row within a minute (or at entry + 5 minutes when the stop was already crossed at entry). Do it for: a rupee stop, a % stop (T-06), a profit target (T-07 and rupee), the time exit, a stop already crossed when the plan is saved. For each, the read-only check: `SELECT rule_id, shown_at AT TIME ZONE 'Asia/Kolkata' FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id WHERE s.name = 'Scenario PATH-<nn>' ORDER BY shown_at;` and, if no row appears, the worker log line `background: strategy <id> check skipped: <reason>` (reasons `prices_STALE`, `prices_LEG_MISSING`, `not_ticked`, `no_gate_read`).
- **Expected:** one `adjustment_suggestions` row per crossed rule, and the alert in Alerts > Active (look in History too). The 5-minute period after entry delays an alert and never swallows it.

### W-10 Compare approaches: "Open in builder and prepare basket", Cancel and Confirm (Lane W item 10; T2-13)
- **Board items:** T2-13 (FAIL); UX-22; issue-list rows 13 and 26; REQ-112 AC-2; ADR-330 (53)
- **Type:** Functionality. **27 Nov:** T2-13 FAIL (an opportunity stayed "Acted on" after Cancel with no order placed). **First carried:** R1 (Lane W). Needs an alert with an opportunity row (Alerts has rows from 27 Nov; if none is open: BLOCKED, name it).
- **Steps:** Alert > Compare approaches > "Open in builder and prepare basket" > Cancel. Look at the opportunity. Prepare again, Confirm.
- **Expected:** after Cancel the opportunity still reads **"Open"**; after Confirm it reads **"Acted on - Paper - not sent to Zerodha"**.

### W-11 Full-exit approach stages the held legs (Lane W item 11)
- **Board items:** UX-21 (staged exits show "No legs yet")
- **Type:** Functionality. **First carried:** R1. **Steps:** Alert > Compare > the full-exit approach > "Open in builder and prepare basket" > Cancel on the confirm list.
- **Expected:** the held legs show as exiting with **"N pending changes"**, never "No legs yet"; wording **"Exiting these legs (staged, not placed yet)"**.

### W-12 Home closed-strategies line (Lane W item 1)
- **Board items:** T1-16 / ADR-330 (35), (62) family (no own id found)
- **Type:** Screen. **First carried:** R1. **Steps:** Home with closed strategies; then Positions. **Expected:** the line under "Total P&L (after charges)" reads the same **"Includes N closed strategies."** as on Positions.

### W-13 "Closed by system" in Alerts History (Lane W item 2; T1-09-close)
- **Board items:** T1-09-close; T1-09 (FAIL); ADR-330 (3); triage C-item 12
- **Type:** Screen. **First carried:** R1. **Steps:** Alerts > History: an alert whose trade closed unanswered. **Expected:** **"Closed by system: the trade closed at 10:23"** (your trade's time in place of 10:23). Also check Alerts > Active holds none of them (27 Nov T1-09 FAIL was the same alerts staying Active after the last leg was exited during market hours; that exit step is MONDAY ONLY).

### W-14 Time-exit wording on the plan sheet (Lane W item 3; T1-10)
- **Board items:** T1-10; UX-17
- **Type:** Screen. **First carried:** R1. **Steps:** plan sheet: a time-exit date in the past, Save. Then clear and type values that are not valid in each of Time exit, Target, Stop, Target (Rs), Stop (Rs), Max adjustments. Then type different values in Target and Target (Rs), and in Stop and Stop (Rs). (The alert half "Time exit reached" needs the worker, which computes nothing while the market is closed: MONDAY ONLY, the 09:25 time-exit trade.)
- **Expected:** **"Time exit date is in the past."**; **"Time exit date is not valid."**; **"Time exit is not valid."**; **"Target is not valid."** (same for Stop, Target (Rs), Stop (Rs), Max adjustments); **"Target and Target (Rs) show different values."**; **"Stop and Stop (Rs) show different values."**; Monday: the alert reads **"Time exit reached: the plan's time exit is HH:MM"**.

### W-15 Two legs on one contract: the Save-draft sentences (Lane W item 4)
- **Board items:** issue-list row 2; OBS-03; D-60
- **Type:** Screen. **First carried:** R1. **Steps:** builder: two legs on one strike and expiry; Save draft; once with the same side, once with opposite sides. Check the leg numbers in the sentence equal the numbers on screen.
- **Expected (same side):** **"Legs 1 and 2 are the same contract and side (NIFTY 1 Dec 25900 CE, Sell)."** then **"Join them into one leg with more lots, or change one to a different contract."** **(opposite sides):** **"Legs 1 and 2 are the same contract (NIFTY 1 Dec 25900 CE), one Sell and one Buy."** then **"A strategy holds one leg per contract: remove one of them, or change one to a different contract."** (27 Nov N-03 saw a red box "This strategy definit..." for two identical legs: write the full text seen.)

### W-16 A completed trade opens read-only (Lane W item 8)
- **Board items:** UX-11, UX-23; ADR-330 (14), (57)
- **Type:** Screen. **First carried:** R1. **Steps:** My Strategies > a Completed trade > Open in Builder. Then a running trade, then a fresh builder. **Expected:** the completed trade shows on the right **"This trade is closed. Its legs and result are shown below; it cannot be changed."**; the running trade and the fresh builder keep their own text.

### W-17 Alerts Active on a slow connection (Lane W item 9)
- **Board items:** UX-12, UX-33
- **Type:** User experience. **First carried:** R1. **Steps:** DevTools > Network > Slow 3G; open Alerts > Active. **Expected:** "Loading..." first, then the rows (never an empty page between).

### W-18 Typing at once into Rename and Save (Lane W item 7; T3-09, N-02)
- **Board items:** T3-09; N-02; issue-list row 5; OBS-02
- **Type:** User experience. **First carried:** R1. **Steps:** My Strategies > Rename on a row, type immediately; press Esc. Builder > Save, type immediately. **Expected:** the text goes in; Esc closes (27 Nov N-02: Esc was ignored until the rename box was clicked: write if it still is).

### W-19 Net Positions name on one line at 1366 px (Lane W item 13)
- **Board items:** UX-29
- **Type:** Screen. **First carried:** R1. **Steps:** browser width 1366 px (DevTools device toolbar, Responsive, 1366); a paper strategy with an open position > Net Positions. **Expected:** "NIFTY 1 Dec 25900 CE" (your contract) on one line.

### W-20 Max-loss line when a stop is typed (Lane M; T1-03)
- **Board items:** T1-03; N-01; OBS-01 (issue-list row 4); UX-07 (UX-03, UX-08 not fixed)
- **Proves:** the ISO date "2028-12-01" in the max-loss line (27 Nov T1-03; N-01). **Type:** Screen. **First carried:** R1 (Lane M `hotfix/maxloss-line-1127` 5a718413; passed on the PC on 27 Nov at 14:20 for T1-03).
- **Steps:** Positions > Paper > B-N1 (the trade used on 27 Nov; if it is gone, any paper trade with a sold NIFTY PE) > Stops. On NIFTY 1 Dec 25650 PE type the stop **"Above 102.55"**.
- **Expected, exactly:** **"If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25). Sold option with less protection: NIFTY 1 Dec 25750 PE."** (the figure is unchanged; no ISO date, no year). The "now" figure may need a price: if it differs only in "now", write it and mark PARTIAL; the rest must match. The "fired index exit quotes its own tick" half (T1-11) is MONDAY ONLY.

### W-21 Lane M read-only SQL (data only; send the rows)
- **Board items:** D-2 data pull (2028 date); OBS-01
- Run each on the VPS with `psql -d ofo_dev` over SSH (read only):
  - Item 1: `SELECT id, name, instrument_type, strike, expiry, exchange_token, first_seen_at, last_seen_at, currently_listed FROM public.catalogue_contracts WHERE id IN (SELECT DISTINCT contract_id FROM public.paper_orders WHERE strategy_id = 194);` (if an expiry reads 2028-12-01 the row is wrong at the source).
  - Item 3: `SELECT DISTINCT o.contract_id, c.expiry FROM public.paper_orders o JOIN public.catalogue_contracts c ON c.id = o.contract_id WHERE o.strategy_id = 194;` and `SELECT id, expiry FROM public.catalogue_contracts WHERE name = 'NIFTY' AND strike = 25750 AND instrument_type = 'PE';`; and from the browser the request URL of `GET /paper/strategies/194/leg-stop-risk` with its reply body.
  - Item 4: `SELECT id, rule_id, outcome, answer, created_at FROM public.actionable_alerts WHERE strategy_id = 201 ORDER BY id;`
- **Type:** Functionality (data). No pass rule: PASS = the rows were read and sent. If strategy 194 or 201 does not exist: PARTIAL, say so.

### W-22 Lane J read-only SQL for the stop alerts (data only; send the rows)
- **Board items:** D-1 data pull (#207); T1-05 to T1-08
- **#207:** `SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id WHERE s.name ILIKE '%#207%' ORDER BY 1, 2;` (`held_at_entry = t` and `seen_clear = f` on `plan.rupee_loss` means the stop was held at entry).
- **A-E #202:** `BEGIN READ ONLY; SELECT h.id, h.rule_id, h.trigger_id, h.stage, h.value, h.threshold, h.reason, h.held_at AT TIME ZONE 'Asia/Kolkata' AS held_ist FROM public.adjustment_held_crossings h JOIN public.strategies s ON s.id = h.strategy_id WHERE s.name = 'A-E #202' ORDER BY h.id; SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id WHERE s.name = 'A-E #202' ORDER BY 1, 2; SELECT g.id, g.rule_id, g.trigger_id, g.value, g.threshold FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id WHERE s.name = 'A-E #202' ORDER BY g.id; ROLLBACK;`
- **A-D #200:** `adjustment_held_crossings` should hold a `plan.rupee_loss` row with reason daily limit, value about 162.5, threshold 100, held about 11:00 to 11:05 (use the A-E query with `s.name = 'A-D #200'`).
- Worker log lines to look for at any time the worker runs: `background: strategy 209 check skipped: prices_<state>` (reasons `prices_STALE`, `prices_LEG_MISSING`, `not_ticked`, `no_gate_read`). Type: Functionality (data). PASS = rows read and sent.

### W-23 Route-delay tool (Lane Q2; makes the app slow on purpose, for T2-08-style and slow-answer checks)
- **Board items:** T2-08 (tool check only)
- **Proves:** that Lane Q2's only working tool runs. **Type:** Functionality. **First carried:** R1 (Lane Q2 5bdfdde0).
- **Steps:** 1. Write a rules file (JSON) with times that carry the offset `+05:30` (a naive time is refused), for example:
  `{"delay_routes": [{"prefix": "/api/strategies/", "suffix": "/plan-watch", "seconds": 5, "from": "2026-11-28T10:00:00+05:30", "until": "2026-11-28T10:10:00+05:30"}]}`
  2. Set the environment variable `OFO_HOLDBACK_FILE` to the file's path. 3. Start the API with **`python -m uvicorn --factory holdback.create_app --app-dir tests_app`** instead of the usual start (it wraps the real API). 4. Open a planned strategy's builder inside the window: the plan-watch answer takes about 5 s longer. 5. Restart the API the usual way afterwards.
- **Expected:** the delayed route answers about 5 s late; other routes unchanged. The `withhold_tokens` and `silence` keys need the Kite relay, which is not built: do not try them (T1-23 and AX-01 are MONDAY ONLY, and are "not possible" until the relay exists).

### W-24 Lane U: what is on this plan and what is Monday's
- Lane U (`hotfix/index-quote-1127`) fixes live-price reads and the exit sentences. On this plan: T1-20 and T3-10 (section 5) and W-25 (Exit dialog with the market closed). **Monday only:** every step that needs ticking prices or a completing exit (T1-02, T1-22, T2-08 completing part, the 429 log lines, "not live" flips, Lane U's measurements for Monday's open).

### W-25 The Exit dialog with the market closed (Lane U2, decision (60); Lane U, decision (49))
- **Board items:** T2-08 (FAIL), T1-02c, UX-01, UX-04, UX-09, UX-13, UX-20, UX-25, UX-31, UX-35, issue-list rows 10, 11, 21, 25, OBS-16, OBS-17, ADR-330 (49), (60). **Type:** Functionality / Screen. **In the build:** Lane U2 `a7ccf4a9`, Lane U `f61f7935`.
- **Expected text (all, Lane U2, pending owner read):** **"The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."** (the next trading day in place of "Monday 30 Nov"); Confirm grey; the legs the exit would close are listed.
- **A. Feed running.** Builder, open a paper trade, tick one leg, Exit. Expected: the dialog opens with the leg, the line above, Confirm grey; Cancel; no order in the Orderbook. Repeat with Exit all (one row per open leg, same line).
- **B. Feed stopped** (stop the feed process, API up). Same steps. Expected: the same line (**not** "Prices are not live"), Confirm grey.
- **C.** Positions > Paper > tick a leg, Exit; and Exit all if offered there. Expected: the same line, with the feed running and stopped.
- **D.** Stop the API for 10 s, then press Exit. Expected: **"The market status could not be read. Try again in a moment."** and Confirm grey; start the API and reopen: the market line.
- **E. Decision (49), Lane U step 4:** stage a lots change on leg 2 of a trade with 3 or 4 legs. Expected: leg 2's Exit is grey with **"This leg has a change waiting; review or discard it first."**; legs 1, 3 and 4 have Exit enabled. Exit leg 1: the dialog lists only leg 1's exit (with the market closed the line above and Confirm grey); leg 2's change is still staged after Cancel. After a trade change: **"The change waiting on <legs> was not kept because the trade changed; stage it again."** (pending owner read).
- **Not on this plan:** an exit that completes ("Exit placed on paper (order n).", "Placing exit...", the unknown-outcome lock): Monday, and F1 (section 7). Lane U2's known minor items: the market answer is fixed for one opening of the dialog (opened 15:29:55 keeps Confirm on after 15:30; opened 09:14:50 stays grey after 09:15 until reopened): not a round 1 check.
- **Write down:** the time the feed was stopped and started, the sentence word for word on each screen.

### W-26 Exit all with a staged change (decision (59), Lane U2): the closed-market part
- **Board items:** ADR-330 (59). **Type:** Functionality / Screen. **In the build:** Lane U2 `a7ccf4a9`.
- **What the market closed can show:** with the market closed the Exit all dialog shows the decision (60) line (W-25), and Confirm is grey, so the discard sentences cannot be seen. Do this part: builder, a paper trade of at least 2 legs, raise one leg's lots (do not Review). Press **Exit all**. Expected: the dialog lists every open leg and the market-closed line; **Cancel: the raised lots are back exactly as they were, no exit staged**; Positions shows nothing placed.
- **Monday (optional, market open):** the dialog says "Exit all closes every open leg. The change waiting on <leg> is not sent and will be discarded."; after Confirm "The change waiting on <leg> was discarded."; the Orderbook shows only the exits (Lane U2 item 3, 7 tests pass in the cloud).

### W-27 (merged into W-25)
- Decision (60) is walked by W-25 A to D. This id is kept so that the 27 Nov mapping does not move.

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

### W-29 Plan door, Stops lines and a closed trade (Lane V, decisions (54), (55), (57))
- **Board items:** ADR-330 (54), (55), (57); UX-A02, UX-A03; UX-10, UX-03, UX-08, UX-11, UX-23
- **Proves:** decisions (54), (55), (57); UX-A02, UX-A03. **Type:** Screen / Functionality. **First carried:** R1 (Lane V `feat/plan-door-1127` fb66dfb1). Lane V states none of these needs a feed.
- **(54) Positions page, filter All:** 1. Open Positions with one running paper trade and one running real trade (if no real position is open: write that and use paper only). 2. Each shows a **"Plan"** button (paper: beside Stops and Exit; real: right end of the group header). 3. Press Plan on the paper trade: the plan sheet opens (title, playbook, target, stop). Press Close. 4. Open the same trade in the builder, press its "Edit plan": the SAME sheet. 5. Press Plan on a trade with no plan: the sheet opens to set the first plan. 6. A fully closed trade shows no Plan button. (27 Nov: the plan sheet took 15 to 60 s to load: write the seconds.) Failure text: "Could not open the plan. Try again."
- **(55) Builder, running one-lot NIFTY iron condor:** 1. Stops panel, type a stop level on the bought 25650 PE leg. 2. After the pause, three lines appear, each on its own line: **"If this stop fires, the sold ... is left without protection."** / **"Max loss now: Rs ..."** / **"Max loss then: Rs ... (worst case: NIFTY at zero)."** 3. Type a stop level on the bought call leg: line 3 reads **"no upper limit (worst case: NIFTY keeps rising)"** and shows no amount. 4. Type a stop on the sold short call: the old one sentence appears. 5. Same on a SENSEX trade: the lines say SENSEX. While waiting: **"Working out max loss for this stop..."** shows from the moment a valid level is typed, then the answer replaces it; an invalid level shows none. Lane V's engine figures for the 27 Nov condor: Max loss now -7,800; Max loss then -1,674,725; exposed leg the sold 25850 PE (your trade may differ: write the figures; the three lines are the check).
- **(57) Closed trade:** 1. Open the builder on settled trade 173. 2. It shows **"This trade is closed. Its legs and result are shown below; it cannot be changed."**, the closed legs, the result, and one line **"Plan: stop Rs ..., target Rs .... Closed by expiry settlement at 15:30."** (or "your exit at HH:MM"). 3. No Plan watch box, no Add/Edit button, no "Add a leg to start one" (27 Nov T1-18 FAIL text).
- **UX-A03:** a fired leg stop's pop-up and History row carry NO max-loss line; the message is "Stop-loss: ... exited at ..." (seen only when a stop has fired: if none exists, write that).

### W-30 Stop percent read back in three places, weekly and monthly; Reset to playbook (Lane R3 plan-read-2, Lane R2)
- **Board items:** T1-13 follow-up, UX-34 (plan block keeps the old stop), T2-19 (Reset to playbook), triage C-item 7, Lane R2 monthly stop box showing 50 (27 Nov). **Type:** Functionality. **In the build:** Lane R3 `3260e094`, Lane R2 `1d0f56e7`. Lane R3's RESULTS "PC steps with the market CLOSED", word for word.
- **Set up once:** Settings > Adjustments > the Iron Condor playbook > make a copy named "R2 test" with T-06 weekly 50 / 50 / 40 and monthly 30 / 30 / 20 (the system playbook has equal rows, which would hide the difference), make it your active Iron Condor playbook. Have one running MONTHLY trade and one running WEEKLY trade (both Iron Condors, plan accepted from "R2 test"). The contract list must be loaded (a market day fetched at least once). [X2: if the PC has no such pair, that is BLOCKED: no monthly Iron Condor trade.] Expected stop box values (first stage): monthly trade 30, weekly trade 50.
- **Steps:** 1. Monthly trade: type stop 45 > Save > read on Positions, the builder and Plan watch: 45 everywhere. Weekly trade: the same, 45. 2. Monthly trade: change only the Target > Save: stop stays 30 on the answer, and 30 after closing and reopening, on Positions, builder and Plan watch. Weekly trade: stays 50. 3. Which row the live check used: open Plan watch for each trade, read the stop line: the monthly trade's stop line is the 30 % of its stored max loss (not 50 %); the weekly trade's the 50 %. In the worker log look for the line "adjustment check:" of the strategy. 4. Press "Reset to playbook" on each trade, confirm: the sheet shows **"Put back to the playbook's values: ..."** and **"Switched on again: ..."** (or **"Nothing differed from the playbook, so nothing was put back."**). Change T-02 first and switch T-05 off so you have something to see. The typed target, stop and time exit stay. 5. A trade whose expiry is 30 Mar 2027 (if you have one): the sheet shows no stop number and says why; a rupee stop saves. 6. Save a plan and, in the same moment, switch the PC network off or kill the backend request after the click (timeout); then reload: the plan is there complete. 7. If the contract list is not loaded: percent stop Save is refused with **"The stop could not be saved: whether this trade expires weekly or monthly could not be read."**; a rupee stop saves.
- Report any step where the stop number differs between Positions, builder and Plan watch for the same trade.

### W-31 Plan watch: one batch request per cycle (Lane Y item 2, Lane H)
- **Board items:** T2-01 / T2-02 cause (n=204 requests in about 6 minutes); issue-list rows 8 and 22 (34 requests a minute); OBS-18. **Type:** Functionality. **In the build:** Lane Y `546d653f` (the Positions page change Lane H did not build) and Lane H `90c4fed5`.
- **Step (Lane Y, "PC step (market closed)"):** Positions with at least 5 open rows (with a plan): browser network tab filtered on `plan-watch`: ONE `/api/plan-watch?strategy_ids=...` per cycle, and none of `/api/strategies/<id>/plan-watch`. Also `grep -c "request GET /api/plan-watch" <api log>` after one minute: 1 (not N).
- If you still see one request per row: FAIL (the page change should be in the build), write the commit.

### W-32 Change expiry on a leg with a stop: the review line (decision (48), #774)
- **Board items:** ADR-330 (48); issue #774; UX-16, UX-24; finding F3 (the after-move half)
- **Proves:** decision (48). **Type:** Screen. **First carried:** R1 (`fix/stop-follows-leg-1127` 6bd22cb6; no RESULTS file, no PC steps: steps written from its design note and commit text).
- **Steps:** 1. Open a running paper trade that has a leg stop. 2. Change expiry on that leg. 3. Read the review step **before** confirming. 4. Do NOT confirm (confirming a move needs prices; with the market closed the server refuses): press Cancel.
- **Expected:** **"The stop on <leg> will be removed; set a new one after the move."** (the leg named as the screens name it, e.g. "NIFTY 13 Oct 22800 CE"). After a move (Monday): the app offers "Set a stop on <new leg>" (pending owner read); no offer on a refused move, an unknown answer or a leg without a stop.

### W-34 "Monitoring paused" badge when the worker stops (Lane Y item 1)
- **Board items:** REQ-165 AC-6 / issue #868 family; UX-10. **Type:** Functionality / Screen. **In the build:** Lane Y `546d653f`.
- **Steps (Lane Y, "Owner test (market CLOSED, Saturday)"):** stop the worker process, wait 2 minutes, reload Live Strategies, Positions, and the builder of a running trade. Expected: each shows **"⏸ Monitoring paused"**, **"Health unknown"**, **"Not being watched: no worker has reported in the last 2 minutes."** Start the worker: within 30 s the badge goes. Restart the worker supervisor again at the end.

### W-35 Add to Paper with "prices are not live" ticked: the entry facts survive (Lane K2, order-door-2)
- **Board items:** the "entry spot was not stored" family (ADR-330 (28)); Lane K2 item 1. **Type:** Functionality. **In the build:** Lane K2 code `5ee104a5` (its RESULTS' PC steps are on the branch tip `f3e75bc7`, not in the build copy).
- **Steps (Lane K2, "market CLOSED, Saturday 08:00", word for word):** 1. Stop the feed process; open the app; the closed banner shows. 2. Open a fresh strategy in the builder, tick "prices are not live", type an entry price on each leg, press Add to Paper. 3. Read the strategy's entry facts: the Adjust page "Entry distance" line for that strategy (it names the entry spot and the call/put distance). **Expected: it shows the spot and distances, not "the entry spot was not stored".** Same step without the tick: the save is refused with its sentence and nothing is stored. (With the market closed Add to Paper may be refused by the market-closed sentence before this: write the sentence; then the result is PARTIAL: Monday.)
- The real order door (a leg above 100 lots refused) is Monday.

### TC-1 The charges tap on Positions > Paper (SW-3; Lane TC could not walk it)
- **Board items:** SW-3, T1-14 (charges basis). **Type:** Screen. **First carried:** R1 (baseline).
- **Steps:** Positions > Paper: read the totals strip, then open its charges tap. **Expected labels:** "Before charges", "Charges paid", "Estimated charges to close", "After charges". Seen elsewhere by TC: the totals strip `Charges paid ₹311.73`, `Booked P&L (after charges)`, `Unbooked P&L (after charges)`. Write what you see.

### TC-2 SENSEX and a far expiry on the Option Chain (SW-7; not walked)
- **Board items:** SW-7. **Type:** Screen. **Steps:** 1. Option Chain: hover a blank cell and write its title text. 2. Switch to SENSEX and to a far expiry; tick two contracts and read the Add controls. 3. Look for rows marked "Currently unavailable on Zerodha". **Expected:** the banner "Market closed. Prices are from <time>."; a blank cell "-"; "Currently unavailable on Zerodha" and "Some contracts are currently unavailable on Zerodha and cannot be added."; as applicable "This expiry is not in the catalogue." / "The catalogue lists no options for this expiry." / "No strikes match the filters."; on a Saturday the broker status says "market closed", never "reconnecting"; no "Stale", "Delayed" or "Unhealthy" word on closed cells.

### TC-3 Notification settings and a "side closed" alert (SW-8; not walked)
- **Board items:** SW-8. **Type:** Screen. **Steps:** 1. Alerts: open notification settings and read the empty line. 2. If a "side closed" alert exists, open its "Add the legs again" confirm and read it; do not confirm. **Expected:** "No notification channels are set up yet."; the "Add the legs again" confirm text is not in the sources: write it as an observation. If no side-closed alert exists: write "none exists" (TC could not create one).

### TC-4 The stop warning text on the Stops panel (SW-9; not typed by TC)
- **Board items:** SW-9, ADR-330 (55). **Type:** Screen. **Steps:** Stops panel (Positions > Stops): type a level in one leg stop and read its warning text; do not click Save unless a rule under test needs it; read the reason line next to Save. **Expected:** the three lines of W-29 (decision (55)) when a bought leg protects a sold leg; otherwise the server's warning text as sent; "Saved: stop <direction> <level>" / "Already set: stop ..." only after Save. Write what you see.

### TC-5 A settled strategy (not seedable by TC)
- **Board items:** T1-18, ADR-330 (57). **Type:** Screen. **Steps:** the settled SENSEX trade 173 (or any real settled row): Completed Strategies, the builder (W-29 (57)), Alerts > Records. **Expected:** Records row "Paper - settled at expiry"; Completed "closed <time>" or "closed: time not available"; "Charges not available: <reason>" where charges are missing. TC could not seed a settlement (it needs an expiry day).

## 5. Reused 27 Nov checks that can be proven with the market closed

Only the steps not run on 27 Nov are listed for a PARTIAL. Expected text that the old plan did not hold is marked: write what you see as an observation.

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

### T1-14 The builder's money figures: charges basis, booked P&L, closed legs, the average exit
- **Proves:** the 0DTE max/profit-left figures (D-14) and the re-buy of a closed contract (#725, #741 follow-up) show the right rows and totals.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "Most steps pass; D-11 table total not visibly changing." Not run: D-14 and re-buy steps.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** MONDAY ONLY: the unrun steps need a trade expiring today (D-14) and closing a leg then buying the same contract again (#725, #741 follow-up); after hours the server refuses exits.
- **Steps:** none (MONDAY ONLY).
- **Expected:** none (MONDAY ONLY).
- **Write down:** build head, screen text, time.

### T1-16 The Paper total line: "Includes N closed strategies." and the left-out line
- **Proves:** the Paper total line names its closed strategies and, when a trade has no price, says it was left out.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "'Includes N closed strategies.' confirmed; the left-out line never arose." Not run: left-out line wording.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** market closed OK (look for a trade with no live price; after a weekend or a restart some trades may read "no price"; if none does, write that no trade was left out)
- **Steps:**
  1. Positions > Paper with at least one closed paper trade. Look under the total for the left-out line (shown only if a trade has no live price). Add up the rows shown and compare with the total.
- **Expected:** "If a trade has no live price, the left-out line '1 strategy left out: its price is not live.' is shown too, and the total adds up to the rows it shows."
- **Write down:** build head, screen text, time.

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

### T2-17 Lists: the status word, current legs, and the figures of a closed row
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

### T2-21 The Strategy Chart on a running paper trade (D-51, ADR-203, ADR-330 (43))
- **Proves:** with no open legs the chart tab says so, and with the switch off it answers 409.
- **Type:** Functionality
- **27 Nov result:** PARTIAL: "Chart line drawn with HTTP 200." Not run: no-open-legs sentence, switch-off 409 text.
- **Fix carried first:** no fix needed: unrun steps only (R1)
- **Needs:** MONDAY ONLY: the no-open-legs sentence needs the remaining legs exited one by one (after hours the server refuses exits), and the 409 text needs the switch lines turned off after that.
- **Steps:** none (MONDAY ONLY).
- **Expected:** none (MONDAY ONLY).
- **Write down:** build head, screen text, time.

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

### T3-09 Rename can be cancelled with Esc; a dismissed outcome reads as two words
- **Proves:** a dismissed opportunity reads "You dismissed this" and its reason as separate words.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Rename Esc passes." Not run: dismissed-outcome part (no dismissed opportunity exists).
- **Fix carried first:** R1 (base; Lane W fix/live-test-small-1127 head bcbff804 where it touches it)
- **Needs:** market closed OK (if no dismissed opportunity exists, dismiss one first if an opportunity is listed; otherwise write that none exists)
- **Steps:**
  1. Positions > Adjustment opportunities: find a dismissed opportunity and read it.
- **Expected:** "a dismissed opportunity reads 'You dismissed this' and its reason as separate words (a screen reader pauses between them)."
- **Write down:** build head, screen text, time.

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

### T4-03 Strategy name width (compact paper list, builder card)
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

### Sweep: pre-open-data sweep (feed absent; judged against ADR-212 and REQ-049 AC-4)

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

### SW-1 Home (`/home/overview`)
- **Proves:** index strip, banner and the three figures are honest after the close.
- **Type:** Screen
- **27 Nov result:** FAIL: Home banner "Market closed. Prices are from 27 Nov 2026, 15:58:01 IST." with Total P&L "—" and "Paper P&L paused - prices not live".
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Home and wait about 10 s. 2. Read the index strip (NIFTY 50, SENSEX): the banner line, each value, the small time beside it. 3. Read the three figures "Running strategies", "Unread alerts", "Total P&L". 4. Reload once and read again.
- **Expected:** banner "Market closed. Prices are from <HH:MM:SS>." with the time about 15:29 to 15:30 IST (the price's own time); with no usable time "Market closed." alone, never "Prices are from Time not available."; a missing index value "Not available"; socket dropped "Reconnecting - prices as of <time>" or "Live prices are reconnecting"; labels "Running strategies" / "Unread alerts" / "Total P&L"; Total P&L is the server's after-charges text with "(after charges)", or a "—" dash with "Paper P&L paused - prices not live" or "Paper P&L is not available right now."; a failed read of one figure "Could not be read right now." in that figure only. Also must not show: an index value with no banner and no time, a value labelled live, "Index values are live." after the close, Total P&L as "0", "-0" or "undefined", the page-load time in the banner.
- **Write down:** build head, banner text, index values and times, the three figures, time.

### SW-2 Positions, Real part (filter "Real", then "All")
- **Proves:** no invented Real number (ADR-016); empty state wording.
- **Type:** Screen
- **27 Nov result:** PARTIAL: Positions Real "No open Zerodha positions." with no banner.
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Positions; click "Real", then "All". 2. Read the "Real P&L" total and each Zerodha position row (Contract, "Your units", P&L). 3. With no Zerodha position open, read the empty state. 4. Reload.
- **Expected (corrected by Lane TC):** with a Zerodha session: "Real P&L" shows the server's figure with its read time ("Zerodha, as at HH:MM:SS IST", for example `+650.00`), never added to Paper P&L (two separate cards). With no session (the weekend): `—` with **"Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, check margin and prepare/execute your strategy."**; the old line "Real P&L is not shown yet: the server does not price Zerodha positions." must be GONE. "No open Zerodha positions." is expected only with a session and no open position. The "Market closed. Prices are from <time>." banner IS mounted on Positions (if absent, record a finding). A red 409 `gate_broker_not_connected` console error on Positions load with no session is known defect D-2: write it as known. Must not show: a Real P&L number the server did not send, Real and Paper totals added together.
- **Write down:** build head, total text, empty state text, banner present or not, time.

### SW-3 Positions, Paper part (filter "Paper")
- **Proves:** paper screens show the last close with its banner; no fill after hours.
- **Type:** Screen
- **27 Nov result:** FAIL: Positions Paper all 9 trades "no price", Exit dialog opens with enabled Confirm.
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Positions > "Paper". 2. Read the totals strip ("Paper P&L" and its charges tap). 3. On one open paper strategy read its card: Total P&L, Booked, Unbooked, Total Decay, Greeks, each leg row (LTP, unbooked, or "no price"). 4. Tick "Show closed positions" and read the closed legs. 5. Open the charges tap. 6. Try Exit on an open strategy and read the refusal; do not confirm anything. 7. Reload.
- **Expected:** banner "Market closed. Prices are from <time>." (not mounted in PaperStrategies by the source read: record if missing); a leg with no held close: cell "no price" and "No price for: {legs}." or "Expired contracts have no price: {legs}.", totals "—" with the reason; paused totals only if a leg is unpriced or the list read failed: "Paper P&L paused - prices not live" and "No paper total yet: prices are not live"; a leg expiring today still open after 15:30: "Market closed. Open legs that expire today settle at HH:MM."; missing Greeks or decay "—" with the reason; Exit refusal "Prices are not live; try again when they update"; charges labels "Before charges", "Charges paid", "Estimated charges to close", "After charges". Must not show: a dash for LTP, Unbooked or Total when the legs did have a close, "Paper P&L paused - prices not live" instead of close figures for legs that have a close, a leg price with no banner or time, an unpriced leg as "0" or blank, an Exit that places a fill (27 Nov: Exit dialog Confirm stayed enabled).
- **Write down:** build head, banner text, card figures, leg cell texts, Exit dialog text and whether Confirm was enabled, time.

### SW-4 Live Strategies
- **Proves:** one banner, honest paused state, fixed time while no feed.
- **Type:** Screen
- **27 Nov result:** FAIL: "Live Strategies 'Checked at 27 Nov 2026, 16:07:45 IST' moves while banner is fixed."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Live Strategies. 2. Read the one banner at the top and confirm there is exactly one, not one per card. 3. For each running paper card read the "P&L" line, the "Checked at" time, the badge "⏸ Monitoring paused" and the dot "Health unknown" (if shown), the status label, the spot line, Max Profit / Max Loss, each leg's LTP. 4. Open the "Stops" and "Exit" links on a card; they only open pages. 5. Wait 60 s for a socket drop or reconnect line.
- **Expected:** page banner "Market closed. Prices are from <time>."; card P&L "P&L <figure> (after charges)", paused "P&L —" with "Paper P&L paused - prices not live", read failed "P&L —" with "Paper P&L is not available right now."; "⏸ Monitoring paused", "Health unknown"; no live answer "Draft — Live data not connected"; a leg no longer live "This leg is no longer a live contract (expired, delisted, or its exchange token now belongs to another contract). It is not priced."; under a paused card "No numbers are shown as live for this strategy."; status "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused."; reconnect "Reconnecting - prices as of <HH:MM:SS>"; nothing running "Nothing is running."; "Waiting for the first answer..."; "Loading next..."; the spot line has no "at <time>" after the close; per-leg health words are not shown while the market is closed. Must not show: several banners, "Prices are from" with the load time, figures shown as live while the badge says paused, LTP "0", "-" with no reason on a leg that has a close, a blank card, "Loading this strategy..." that never ends, the legs' health words after the close.
- **Write down:** build head, banner text and count, "Checked at" time on two reads a minute apart, badge and dot text, time.

### SW-5 My Strategies (and the Completed tab)
- **Proves:** row P&L is the close figure or a dash with a reason, never 0.
- **Type:** Screen
- **27 Nov result:** PARTIAL: My Strategies running rows "P&L — · Paper P&L paused - prices not live".
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open My Strategies and the Completed tab. 2. For each running row read the P&L line and the "last saved <time>" text. 3. On Completed read "Final P&L", "Charges", "Net after charges", "Adjustments made", "Adjustment cost" and "closed <time>". 4. Reload.
- **Expected:** "P&L <figure> (after charges)", or "P&L —" with "Paper P&L paused - prices not live" or "Paper P&L is not available right now."; Completed "closed <time>" or "closed: time not available"; "Charges not available: <reason>" and "not available: <reason>" for net; read failed "Could not load your strategies. Nothing was changed." with Retry; status words only "Draft", "Running", "Completed" or "Status not available". Must not show: "Final P&L undefined", "Charges 0" for an unreadable charge, a Running row with a number and no label, "last saved Time not available" (report it as a defect).
- **Write down:** build head, each row's P&L line and saved time, Completed figures, time.

### SW-6 Builder of a running paper trade (My Strategies or Live Strategies > the trade)
- **Proves:** the builder works from the last close under the banner with the entry labelled.
- **Type:** Screen
- **27 Nov result:** FAIL: Builder #209 "Rule not checked: No adjustment opportunity checked: prices stale or missing." x17 (and 15:55 observation: paper panel "as of Time not available" beside "As of 15:55:37 IST").
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open the builder of a Running paper strategy. 2. Read the banner under the header, the index level card, the paper panel (Total, per-leg figures, Booked/Unbooked), the legs table LTP column, the "As of HH:MM:SS IST" line and the Orderbook. 3. Read At Expiry / Estimated Now, Greeks and IV tiles. 4. Try "Add to Paper", then cancel without confirming. 5. Read the Exit control's reason.
- **Expected:** banner "Market closed. Prices are from <time>." or for legs priced only after the close "Market closed. Prices are from {frozen}; 1 leg as of {later}." / "...; {count} legs as of {later}."; paper panel "As of HH:MM:SS IST"; leg expiring today "Market closed. Open legs that expire today settle at HH:MM."; unpriced leg "Paper P&L paused - prices not live, as of <time>" and "no price"; money-time labels "at the last close prices, as of {time}" or "at the last close prices", never the live forms; Add to Paper (corrected by Lane TC; cancel, do not Confirm): **no tick box**; the Price box is empty for a draft with no planned entry (hint "Enter a price in steps of 0.05"); the server refuses a Confirm with "The market is closed. Orders can be placed once it opens." (MARKET_DATA_102); targets "not shown while prices are not live" beside "-"; level card with no index price "—"; Exit "Prices are not live; try again when they update". Must not show: the live form of a money-time label after the close, an entry price without a close label and time, a "price has moved" marker driven by a closing price, a live-looking Estimated Now, a made-up number for an unpriced leg, a successful paper fill.
- **Write down:** build head, banner text, panel "As of" text, Add to Paper dialog text, Exit reason, time.

### SW-7 Option Chain
- **Proves:** chain shows the closed-market banner and last prices, no live wording.
- **Type:** Screen
- **27 Nov result:** FAIL: "Option Chain every strike LTP '- not available'."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Option Chain; NIFTY, nearest expiry. 2. Read the spot, "as of <time>", the banner, any health text, a strip of rows around the ATM, the IV and Greeks columns. 3. Hover a blank cell for its title text. 4. Switch to SENSEX and to a far expiry; tick two contracts and read the Add controls. 5. Look for rows marked "Currently unavailable on Zerodha".
- **Expected:** ADR-177 example: on a Saturday the chain reads "Market closed. Prices are from 15:29:58." and the broker status reads market closed, never "reconnecting". Banner "Market closed. Prices are from <time>."; spot with "as of <time>", no spot-health sentence while closed; no "live" word on the socket status; no data yet "Waiting for live data."; "Option chain unavailable: not connected to live data."; "The underlying price is missing, so no strikes can be chosen yet." or "The underlying price is missing right now: option prices are shown, but the ATM strike, moneyness, IV and Greeks are not."; "This expiry is not in the catalogue.", "The catalogue lists no options for this expiry.", "The catalogue could not be read.", "The expiries could not be read, so no chain is shown.", "No strikes match the filters."; missing cell "-", Change / OI Change missing "not available"; "Currently unavailable on Zerodha" and "Some contracts are currently unavailable on Zerodha and cannot be added." Must not show: a "Stale" / "Delayed" / "Unhealthy" word on every closed cell, "live" socket text, an empty chain with no sentence, bid/ask 0 as "₹0", a different time per row in place of the banner time, "undefined" or "NaN" in IV/Greeks.
- **Write down:** build head, banner text, spot and "as of" time, cell texts seen, time.

### SW-8 Alerts (Active, History, Records)
- **Proves:** no alert fires silently from a closing price; honest empty and paused lines.
- **Type:** Screen
- **27 Nov result:** PARTIAL: "Alerts History 'The page could not get an answer from the server.' above 11 records."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Alerts; read Active, History and the Records view ("stops or expiry settlements"). 2. For each fired row read the "fired" line and the "no longer true" line and any data-health text. 3. Open notification settings and read the empty line. 4. If a "side closed" alert exists open its "Add the legs again" confirm and read it; do not confirm. 5. Confirm no new alert fired at or after 15:30 because of the closing prices.
- **Expected:** empty Active/History "No alerts yet. Alerts start when strategy monitoring rules are added."; empty Records "No stops or expiry settlements yet."; notification settings "No notification channels are set up yet."; paused "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused."; market-closed variant "Market closed. Prices are from {time}." with "Prices on screen are the last ones before the close; none are arriving, as expected." (line from a grep context in the source: verify); expiry settlement record "Paper - settled at expiry"; alert rows show the server's fired and "no longer true" lines and answer buttons as sent. Must not show: a stop or target alert that fired from the closing price after 15:30 with no data-health text, a fired alert with no data-health line, "Live data: live" on a closed market, a blank Records list with no empty line, "undefined" in a row title.
- **Write down:** build head, History/Records texts, any error text, time.

### SW-9 Stops panel (Live Strategies > "Stops", or Positions > Stops)
- **Proves:** index level on the Stops panel carries its own time; no "Data: live" after the close.
- **Type:** Screen
- **27 Nov result:** FAIL: "Stops panel 'Index values unavailable.' while other screens show 25607.20."
- **Fix carried first:** no fix named: baseline run in R1, re-run each round
- **Steps:** 1. Open Stops for a Running paper strategy. 2. Read the label line, the index line below it, the "Conditional exit" Above/Below boxes, the leg stop rows and the triggers list. 3. Type a level in one leg stop and read its warning text; do not click Save unless a rule under test needs it. 4. Read the reason line next to Save. 5. Look at any trigger row for a data-health word.
- **Expected:** label "Paper - exits are recorded in the app, not sent to Zerodha"; index line live "<NIFTY> now <value> as of <HH:MM:SS>", not live "Index values unavailable."; after the close a value must come with its own time, not the page-load time; saves "Saved: stop <direction> <level>" or "Already set: stop ..."; warnings are the server's warning_text as sent; the reason next to Save is the server's; tracking-panel data line "Data: live" / "Data: stale" / "Data: paused" / "Data: not known": after the close with the feed stopped it must read "Data: paused" or "Data: stale", never "Data: live". Must not show: an index level with no time or with the load time, a stop that reads as armed on live data with "Data: live" after the close, a trigger that fired after the close from a closing price without a data-health word, "undefined" or "null" in the level boxes, a blank index line when the index is not live.
- **Write down:** build head, index line text, data-state line, warning and reason text, time.

---

### Run LAST

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

### Monday/Tuesday only

### AF-09 Items that need an expiry day
- **Proves:** D-64; D-59; D-12 / D-08.
- **Type:** Functionality
- **27 Nov result:** NOT CHECKED: "No open paper trade expires on 27 Nov 2026; expiries are 1 Dec or 8 Dec."
- **Fix carried first:** none named in the mapping given.
- MONDAY/TUESDAY ONLY: it needs a day on which an open paper trade expires, between 15:30 and 15:45 (D-64: "Market closed. Open legs that expire today settle at 15:45."; D-59: "Stops survive a part settlement at 15:45"). No steps written. NIFTY and SENSEX weekly expiries on the next trading days are expected to fall Monday/Tuesday: confirm a trade expires that day before running.

### AX-01 Index tick silent for 60 seconds
- **Proves:** the screen says so when the index tick goes silent.
- **Type:** Functionality
- **27 Nov result:** NOT CHECKED: "The index tick never went silent for 60 s."
- **Fix carried first:** none named in the mapping given.
- MONDAY/TUESDAY ONLY: it needs a live index feed that goes silent for 60 s during market hours; on the weekend there is no tick to go silent. No steps written.

## 7. Known open findings F1 to F3: not a round 1 failure; one round 2 check each, ready now

Source: Lane Z's independent Opus review of the joined stop and exit paths (RESULTS-lane-z.md; verdict REVISE). In round 1 write what you see as an observation tagged "known F1/F2/F3". These checks run in round 2 (and again in round 3) once the fix lanes' build carries them. **Market closed limits what can be proven:** an exit that completes needs the market open, so each check says what the weekend can show and what is Monday's.

### R2-F1 After an exit with an unknown outcome, no second exit is sent (finding F1; fix lane FB, with FD's request key)
- **Update (Lane FB, `fix/r2-builder-1128`, 05:10 IST):** F1 is fixed on the page: the unknown-exit unlock now waits `UNKNOWN_EXIT_WINDOW_MS = 120 s` (not 5 s); the server-side request key (`client_request_id` on `POST /paper/strategies/{id}/orders`, also #871) is Lane FD's and was not started at 05:18. The check of R2-FB covers the page half; the key half stays open until Lane FD's RESULTS.
- **Board items:** F1; ADR-017; ADR-330 (59) item 1 (Lane U2). **Type:** Functionality. **First carried:** R2 (Lane FB; not on origin at v2).
- **What the finding says (Lane Z, word for word):** "StrategyBuilderPage.vue `decideUnknownExit`, `EARLY_MS = 5000`: after an UNKNOWN exit outcome the page says "not stored" and unlocks Exit if the trade looks unchanged 5 s after the client gave up; the server can still commit later (client timeout 10 s, statement timeout 30 s, pool wait up to 30 s, no idempotency key): a second per-leg partial Exit commits too (2 of 4 lots twice = 4 lots). Full-leg and Exit all are protected by EXIT_EXCEEDS_OPEN. Against ADR-017."
- **Expected after the fix (Lane U2 text, pending owner read):** "The first exit's outcome is being checked; no second exit is sent until the book has been read."; the Confirm stays grey past 5 s; "The change waiting on <legs> was not sent; it is kept until the exit's outcome is known."
- **Weekend steps:** with the market closed an exit is refused, so the unknown-outcome path cannot be run. Write what the round 2 RESULTS file of Lane FB gives as "PC steps, market CLOSED"; if it gives none: **BLOCKED: needs a completing exit (Monday, optional, Lane U2 item 1 step 2: stop the API right after pressing Confirm for a one-leg Exit; Confirm stays grey past 5 s; start the API and press "Open Orderbook" after 5 s; never two exit orders for one click).**

### R2-F2 An index exit fires when the index price feed is silent (finding F2; fix lane FE)
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

**How this section is built:** each lane's `RESULTS-lane-*.md` ("PC steps", "New wording for the owner to read", "Decided for the owner") was read on its branch at about 05:18 IST on 28 Nov. Branches are named, not commits (heads move); the PC takes the commit the coordinator sends for round 2 and checks `git merge-base --is-ancestor` for each branch head it relies on. **Not on origin at 05:18:** `fix/r2-index-exit-watch-1128` (Lane FE), `fix/r2-exit-stops-2-1128`, `fix/r2-builder-2-1128`, `fix/r2-pages-1128`, `fix/r2-plan-screens-1128`, `fix/r2-backend-2-1128`, `test/r2-backend-1128`, `test/r2-walk-builder-1128`: their checks are written as "NOT PUSHED at 05:18" and the next version fills them. No lane reports a migration; the plan-acceptance database change (0058, renumbered 0060, Lane FD item B2) is **not done** and has no old-code-safe proof: **it is not applied; any check that needs it is BLOCKED (name 0060).** All steps below are market closed, paper only; live-market parts are listed and are Monday's (optional).

### R2-FA Exit dialog and Stops panel (`fix/r2-exit-stops-1128`, Lane FA, "SAFE TO CLOSE: yes")
- **Board items:** I-17 (price age line), I-18 ("Placing exit..."), I-29 (index exit rule after the close), D2 (the ISO date on a stop row), #872 (the dialog follows the market state), #874 (closed-market Exit tests). **Not done by FA:** UX-A01 (not its file), UX-A02 (needs a cost value), F3 (waits for FD's field `cancelled_stops`), #870, #873. **Type:** Screen / Functionality.
- **Steps (Lane FA, word for word):** 1. Positions: open Exit on a strategy with "no price" rows: the dialog opens, shows the age line ("No price for ..."), the market-closed line and Confirm greyed. 2. Stops panel of a paper strategy: type a level above NIFTY, Save. Expect **"Saved: exit above ..."**, the reference line under the index line, no "Index values unavailable.". Repeat with SENSEX. If refused, copy the refusal text (it goes to Lane FD). 3. A stop on a leg that is not among the open legs: the date reads **"NIFTY 22300 PE 3 Nov"** (the one date rule), never "2026-12-01".
- **Expected texts (new, pending owner read):** "No price for N of M legs; the server prices the exit when you confirm."; "The time of the price is not available."; "Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago."; Stops panel with no close: **"NIFTY: the last close is not available."**; reference line: **"The market is closed. A level you save is checked from the next market open; the last close is shown for reference."**
- **Monday (optional, live):** "Price as of HH:MM:SS IST, N seconds ago."; Confirm shows "Placing exit..." then "Exit placed on paper (order N)." in view; stop the server before Confirm: the unknown line shows in view and Confirm stays locked until the re-read.

### R2-FB Builder page, finding F1 (`fix/r2-builder-1128`, Lane FB)
- **Board items:** F1 (fixed; the unknown-exit unlock now waits `UNKNOWN_EXIT_WINDOW_MS = 120 s`), I-30 (contract-list line), I-50 (one loading state per leg), UX-B25, UX-AF1, UX-C3 (two of three lines), UX-A03 (proven already). **Not fixed:** I-49 (slow first prices: cause found in `LegPicker.vue`, fix for the owner lane), I-68 (no code change: Add to Paper one press already holds; two steps are spec decisions ADR-330 (19), (28)). **Type:** Screen / Functionality.
- **Steps (Lane FB, "PC steps, market CLOSED", word for word):** 1. `git fetch && git checkout fix/r2-builder-1128`, start the app, open the builder with no legs. If the instrument list is yesterday's (before the load), expect the server's line above the legs. Run `cd frontend && npx vitest run tests/contract-list-line-r2-fb.test.js tests/leg-working-r2-fb.test.js tests/builder-first-prices-r2-fb.test.js tests/add-to-paper-r2-fb.test.js`. 2. Pick two legs: while the outcome is out, every leg row says **"Working out the outcome..."** and shows no capture time; the figures return when it answers.
- **Expected texts (new, pending owner read):** after an unknown add ("Review and add"): **"The last paper order got no answer and may be stored. It is not sent again until the Paper book has been read: open the strategy again to check."**; the server's `contract_list_earlier` line "Contract list of <date>. Today's list loads at about <hh:mm>." (not new); suggested (not built): "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known."
- **R2-F1 (finding F1):** see section 7: the market-closed part is these steps; the completing part is Monday (optional).
- **Monday (optional, live):** 08:30 to about 08:35 the contract-list line on the builder (also with no legs) and it disappears within about a minute after the list loads, no reload; time from Done to first prices for one leg (T2-11, 14 s before: expect the same, I-49 is not fixed); Add to Paper on a new strategy: Confirm not greyed with live prices; press Confirm twice quickly: one paper order only.

### R2-FC Small screens and wording (`fix/r2-small-screens-1128`, Lane FC, "SAFE TO CLOSE: yes")
- **Board items:** I-122, I-69 (UX-05, UX-06; already in the build), I-70 (bulk delete count: UX-B06 NOT confirmed closed), I-24 (exits read for a real trade: page half only), F7 (`stop_kind_reason`), I-61 ("Now" value), I-62 (take-profit wording), the far-month badge (no page change). TB defect D1 (Alerts History empty text while loading). **Not taken up:** UX-B04, UX-A05, UX-A06, UX-A12, UX-A09, UX-SW6, UX-B13, #875, #880. **Type:** Screen.
- **Steps (Lane FC, word for word):** 2. `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_d36_adjustment_counts.py` (the new take-profit sentence in `approaches.json`; Lane FD notes two failures of this file on the unmodified build: `test_approaches_counts_and_reply` and `test_check_counts_and_reply`, expected strategy_id 1, got 123: write them as "known"). 3. Positions > Adjustment opportunities: every open record says **"Now: not read yet"** until Lane FD adds the fields. 4. Open a plan sheet of a trade whose expiry kind is not known: the stop box shows the server's reason (`plan-stop-kind-reason`). 5. Alerts > History while its reads are pending (TB D1): a loading line, not "No stops or expiry settlements yet." until both reads have answered. [X2: FC's step 1 is its own container's worktree cleanup: not a PC step.]
- **Expected texts (new, pending owner read):** "Now <value> as of <time> IST" / "Now: not read yet" (open records only); **"This approach is not built because the whole trade would not be in profit with every open leg closed at its planned price."**; **"Exits of a real-mode trade cannot be read here yet."** (shows only after `TrackingPanel` passes `exitsMode`); "Delete 14 strategies? 3 of them are running."
- **Needs Lane FD's fields (not yet):** `now_value`, `now_as_of`; a `GET /monitoring-state` entry `watch_state: "paused"`, `reason: "expiry_kind_unknown"`, `badge_text: "Monitoring paused"`, `reason_text` (suggested: "Every exit rule is not checked because whether this trade expires weekly or monthly is not known.").

### R2-FD Backend totals, connection holds, plan acceptance (`fix/r2-backend-1128-fd`, Lane FD, "NOT SAFE TO CLOSE: B2 and B5 remain")
- **Board items:** B1 (ADR-330 (62) booked result in the header total: already in the build; the `place_paper_orders` connection hold fixed, 2 tests), B3 (read-path holds: already done, proven), B4 (fired-exit wording: found, not changed), B2 (plan acceptance 0058 to 0060: NOT DONE), B5 (served field: not started); not started: UX-A08, UX-A18, F3 (R2-F3), F4, #869, #871, #877, #855, #857, #858, #859, a possible migration for #868. **Type:** Functionality.
- **PC steps:** Lane FD: "Market closed: none for B1. Live: none." So the PC check is the totals of W-06 again (header total shows the booked result of closed trades) and the connection count of set-up step 0 (no growth while the screens are open).
- **New sentences (not built):** fired stop: "{line}; seen by the check at {time} IST" / "{line}; seen by the check on {date} at {time} IST" (replaces "{line}; reached at {time} IST").
- **Migration 0060:** none in this lane; apply nothing (no proof). Real first fill `execution_return._return` still holds a connection: a gap, ADR-330 (58).

### R2-FE Index exit with a silent feed, worker issues (`fix/r2-index-exit-watch-1128`, Lane FE): NOT PUSHED at 05:18
- **Board items:** F2 (R2-F2), #860 to #868, #878, #879 (table below). Lane FE's RESULTS will give the PC steps; until then the table is the check list.

| Issue | Meaning | What a market-closed PC check can look at |
|---|---|---|
| #860 | A time exit typed as plain HH:MM (no date) reads "not checked" even on expiry day (fails closed) | Plan sheet with a plain "15:20" time exit and an unknown expiry kind: it says not checked (known gap); the dated form runs |
| #861 | The worker's reason for an unknown-kind percent stop is generic | Plan sheet / monitoring state of such a trade: read the reason text |
| #862 | A stop typed and crossed within one minute is first checked with the old plan (up to 10 s) | not checkable with the market closed |
| #863 | The worker prices a trade's market from the first-listed leg's expiry, not the nearest leg's | A paper trade with two legs of different expiries, the farther listed first: which expiry's market the monitoring entry uses |
| #864 | `_tracked_on` reads the whole live catalogue per strategy on every re-read | performance only; worker log timing |
| #865 | The unknown-kind timing style (intraday) is fixed by no test | a test gap; no screen |
| #866 | The T-06 not-checked reason for an unknown expiry kind says days left are missing | Plan sheet of such a trade: the reason must say the expiry kind is unknown |
| #867 | `Worker._checked_body` never removes an entry | delete or settle a paper strategy, then look for a leftover entry in the monitoring state list |
| #868 | The paused state lives only in the worker's memory (REQ-165 AC-6) | the badge of W-34; restart the worker and see whether the badge is lost |
| #876 | Plan-save case of 27 Nov 13:28 not reproduced | the data pull D-1 (section 8) |
| #878 | A strategy dropped from the worker's list can stay ACTIVE in its stored state | close a paper strategy, then read its stored monitoring state / Stops panel: it must not show "watched" |
| #879 | Clock skew widens the 2-minute window of the plan check | not visible on a screen |

### R2-TB Frontend tests (`test/r2-frontend-1128`, Lane TB, "SAFE TO CLOSE")
- **Items:** I-40, I-60, I-65, I-69, I-74 (could not reproduce "no legs"), I-76, I-80 (the DB half `tests_app/test_strategy_bulk_delete.py` not covered), I-83, I-94, I-98. Defects: D1 (FC) and D2 (FA, above). **PC step (Lane TB):** `cd frontend && npx vitest run tests/<file>.r2-1128.test.js` for any of the nine files, or `npm run test:run`. No on-screen sentence is added.

### R2-TE Named tests green (`test/r2-named-green-1128`, Lane TE)
- **Items:** 42 named items pass on the build (I-01, I-04 ... I-125; I-51 only half proven: the screen prints the server's three lines in order, the "theoretical worst case" wording is a fixture; I-125 proven at 15 s, not 10 s). The gate was NOT TOTAL PASS on its push (shallow clone; two frontend timeouts); the full `tests_app` section is empty at 05:18. Defect: `tests_app` files leave rows behind and fail in sequence on one database (not a product defect). **No PC steps.** The PC does not rerun these.

### R2-NOT-PUSHED Second wave and remaining lanes (NOT PUSHED at 05:18)
- `fix/r2-exit-stops-2-1128`, `fix/r2-builder-2-1128`, `fix/r2-pages-1128`, `fix/r2-plan-screens-1128`, `fix/r2-backend-2-1128`, `test/r2-backend-1128`, `test/r2-walk-builder-1128`, `fix/r2-index-exit-watch-1128`. Each gets its section in the next version: "PC steps (market closed)", "New wording for the owner to read", the board items or issue numbers.

### R2-UX The PC's 41 usability notes (PC's comment of 03:11 IST on PR #722, id 7228671479)
Each note is covered by a check (the PC writes whether the note is still there); board ids are from the triage (UX-nn).

| PC note | Check or board item |
|---|---|
| UX-B01, UX-A18 (ISO date in the stops and exit warning) | W-20 (Lane M), R2-FA step 3 (D2) |
| UX-B02, UX-A01, UX-B05, UX-A04, UX-B10, UX-A11, UX-A32, UX-A13, UX-A24 (Exit dialog; prices flapping) | W-25; R2-FA (I-17, I-18); Monday for the completing parts |
| UX-A02, UX-A03 (Stops lines, fired-stop toast) | W-29; R2-FB (UX-A03 proven); UX-A02 not done by FA |
| UX-A05, UX-A06, UX-A12, UX-A33 (plan sheet; settled-trade wording) | W-29 (decisions (54), (57)); not taken up by FC |
| UX-A07, UX-A29, UX-A31 (Alerts empty text; rows with only the strategy name) | W-28, W-17, R2-FC step 5 (D1) |
| UX-B08, UX-B13, UX-B23 (typed-price replaced sentence names a strike) | W-28 step 10; UX-B13 not taken up |
| UX-A08, UX-A10 (refusal names "time_exit" and "playbook"; 15 to 60 s) | W-14, W-29; R2-FD (not started) |
| UX-B11, UX-B12 (basket and "Acted on") | W-10, W-11 |
| UX-B07, UX-B09, UX-C3, UX-SW6 | W-03; R2-FB (I-50, UX-C3 two of three lines); UX-SW6 not taken up |
| UX-A30 (Plan block keeps the old stop) | W-01 |
| UX-A09, UX-AF1, UX-AF02 | W-33; R2-FB (UX-AF1 fixed) |
| UX-AF2 (Select all 16 shown while 17 listed) | W-06; R2-FC (I-70); TB I-40 test |
| UX-B03, UX-B06 (Undo; running trade selectable for delete) | T2-09 (section 5); R2-FC (UX-B06 not confirmed closed) |
| UX-B25 (locked builder keeps old numbers) | R2-FB (fixed) |
| UX-B04, UX-A19 | UX-B04 not taken up; UX-A19 no check: usability note |

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
| R2-FA to R2-FD, R2-TB, R2-TE, R2-UX (section 9); R2-FE and the second wave when pushed | R2 | R3 |
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
6. npm ci and npm run build in the serving checkout; restart the API, then the worker, then the feed; Ctrl+F5; health page healthy.
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
