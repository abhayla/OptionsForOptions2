# Lane M results: the leg-stop max-loss line (27 Nov 2026)

Coordinator lines (send_message to "@parent" was refused: `elevated_session_untrusted_device`; written here instead):

- LANE M ALIVE (09:46 IST)
- LANE M ITEM 4 ANSWER (13:30 IST, side_closed for B-P2; from the 206a9f0 code, not yet run on the PC data):
  - What raises it: `background.Worker.rebuild` -> `_raise_side_closed_all(monitors)` ->
    `DbGateStore.raise_side_closed` -> `side_closed.raise_if_closed` (one alert module, kind side_closed), every
    REBUILD_SECONDS, ONLY for the strategies in `monitors`, the list `owner_lister` returns.
  - Why B-P2 got none: `owner_lister` drops every strategy whose plan resolves to nothing
    (`if resolved.body is None: ... _lapse_exited(..., "not_monitored"); continue`, ADR-330 (11)). A trade with no
    plan is never in `monitors`, so the side-closed check never runs for it. Not the cause: a leg stop vs Exit (the
    check reads the position only: `side_scope.closed_sides(entry.legs, now.legs)`), a quiet period (none), one row
    per strategy (the rule is per side and episode).
  - Other conditions under which no row is raised even with a plan: the entry is not exactly 4 legs of a SHORT iron
    condor with put BUY < put SELL < call SELL < call BUY (`_is_condor`); both sides closed at once; an open or
    answered row for the same side in this episode; the strategy's tracked read failed (unread) that rebuild.
  - Spec: a DEFECT, in my reading [Likely]. ADR-330 (11) withholds from a no-plan trade "adjustment suggestions and
    ... target or stop alerts" and nothing else; ADR-330 (2)(b) "When a side closes, the user is told so and asked"
    and (33) "every time a side of the trade closes the user is told and asked again" carry no plan condition, and the
    question is about the trade's shape name, not about a plan rule. I see no conflict between the two rows, so this is
    not an owner question; if the coordinator reads (2)(a)'s heading "the plan after one side exits" as limiting (b),
    it becomes one.
  - The fix must also stop the no-plan path closing the row it raises: `_lapse_exited(..., "not_monitored")` calls
    `actionable_alerts.close_by_system` for the strategy's open records on every rebuild; a system-closed side_closed
    row does not stop a new raise, so a plain "also raise for no-plan trades" would raise, close and raise again each
    rebuild. Fix shape: `owner_lister` hands the no-plan tracked strategies to the side-closed check too, and the
    not_monitored lapse leaves side_closed rows open (they are not plan records).
  - Not the loss-stop guard path (Lane J): the side-closed raise is a separate call in `rebuild`.
  - PC check that settles B-P2: did it have a plan at 13:03 (`SELECT ... FROM strategy plans` for B-P2), and
    `SELECT id, kind, rule_id, outcome, answer, created_at FROM public.actionable_alerts WHERE strategy_id = <B-P2>`
    (a side_closed row closed by the system would show the raise/close path already ran).
- LANE M RCA (10:25 IST, after the 09:50 correction): the figure is right (bought 25650 PE stopped at 102.55 leaves
  the sold 25750 PE bare: 11,433.50 - 25,750 x 65 = -16,62,316.50, pinned through the engine). The date is printed by
  `routes/paper.py::names_and_terms`, which named every leg of the line with `describe_contract`, the ISO record form
  "NIFTY 25750 PE <catalogue expiry>", where every screen uses `display_contract` ("NIFTY 1 Dec 25750 PE", REQ-151).
  The YEAR is the catalogue row's own stored expiry (`catalogue_contracts.expiry`), printed as is: no code on this head
  builds 2028 (the refresh refuses an expiry move of more than 6 days, ADR-059; the test seeder runs on CI only), so the
  PC's row for that contract must read 2028-12-01: SQL below. It is not used in the figure (at-expiry payoff; the
  expiry only groups legs), but it would be used by anything time-based (Greeks, days to expiry, settlement).
- LANE M PUSH 1: head ffeb6dd, prepush TOTAL PASS (marker written; 10,308 domain + 5,109 app tests, frontend build,
  lint, unit). PC re-tests: B-N1 stop "Above 102.55" on the 25650 PE reads "... Rs 16,62,316.50 (now Rs 1,732.25).
  Sold option with less protection: NIFTY 1 Dec 25750 PE."; then run the catalogue SQL (deferred item 1).
- LANE M ITEM 2 RCA CONFIRMED: `paper_monitor._index_at_fire` quoted the provider's HELD index reading first; the exit
  is decided on the arriving crossing tick (`on_quote` -> `stops.crossed`). Two readings: the quoted one can sit on
  the wrong side of the level (#196: "above 25,800.00; NIFTY was at 25,796.75").
- LANE M PUSH 2: see "Item 2" below.
- LANE M ITEM 3 (12:40 brief; my date RCA withdrawn: the PC reads contract 9111 at 2026-12-01): the server path
  named in the brief does NOT look a leg up by strike and type. Every read on it is by the order's own contract id:
  `names_and_terms` -> `tracked_contracts.resolve(ids)` -> `catalogue_store.load_contracts` (`WHERE c.id = ANY(:ids)`),
  names keyed by that id; `exit_risk.exposed` holds ids of the book's open positions. Proof:
  `tests_app/test_leg_stop_risk.py::test_m3_*` puts a 2028-12-01 twin of the bare short put (same name, strike, type)
  in the catalogue: the line names the book's own contract, the figure is unchanged (one expiry), and the twin is in no
  name or term. It passes on this head; on 206a9f0 the name would be the ISO form of the RIGHT contract. So a 2028 name
  on this line means a 2028 contract id was in the request's book. NOT EXPLAINED YET; needs from the PC:
  (1) `SELECT DISTINCT o.contract_id, c.expiry FROM public.paper_orders o JOIN public.catalogue_contracts c ON c.id =
  o.contract_id WHERE o.strategy_id = 194;` (paper_orders, not the strategy's saved legs);
  (2) `SELECT id, expiry FROM public.catalogue_contracts WHERE name = 'NIFTY' AND strike = 25750 AND instrument_type =
  'PE';` and whether any of those ids appears in (1) or in `paper_triggers` of 194;
  (3) the browser's request URL of `GET /paper/strategies/194/leg-stop-risk` (its contract_id) and the reply body.
  Class (resolving a contract by strike + type): `ready_made.py:177` (one expiry's catalogue, exactly-one match or
  refused), `routes/leg_edit.py:455` and `ofo/strategy/leg_edit.py:159` (expiry in the match), `background._leg_quote`
  (the chain of the leg's own expiry), `outcome/service.py:639` (one expiry's chain), `adjustment/approaches.py:397`
  (expiry or tradingsymbol), frontend `legPicker.js:53` `selectedContract` and `guided.js:138` (match on type + strike
  in the `contracts` list the page loaded: safe only if that list is one expiry; NOT verified this session, the first
  thing to check if (1) shows a 2028 id). No fix made: no lookup on the line's path to fix.

Spec basis: ADR-008, ADR-003, ADR-330 (6), REQ-151 (contracts named as the screens print them), REQ-100.

## Scope change (coordinator 09:50 IST, PR #722 comment 7209682005)

The stop was on the BOUGHT 25650 PE ("Above 102.55"), not the short call. The figure stays. Only the date is fixed;
the wording is a proposal below (not built). The first commit of this branch (3389c83, a new sentence instead of the
figure) was reverted in the next commit, before any push.

## Core proof (failing first)

- Engine, B-N1's numbers: `tests/tracking/test_leg_stop_bn1.py` (no DB): before -1,732.25, after -16,62,316.50,
  exposed = the 25750 PE; a 2028 year on every leg gives the same figure; one leg on another year gives no figure.
- Route, real PostgreSQL: `tests_app/test_leg_stop_risk.py::test_m1_...` on the app's 25 Nov iron condor, stop on the
  long 22200 PE at 5.00. Before the fix the route answered (read back from the run):
  `If this stop fires, max loss becomes Rs 14,45,535.00 (now Rs 2,860.00). Sold option with less protection: NIFTY 22400 PE 2026-10-13.`
  After: `... Sold option with less protection: NIFTY 13 Oct 22400 PE.` (same figure). With the route change stashed
  the test fails again (mutation check).
- Fired message (same function): `tests_app/test_stop_fired_message.py::test_m1_...`, fill 5.50: Rs 14,45,502.50,
  leg "NIFTY 13 Oct 22400 PE".

## RCA (one sentence)

`names_and_terms` (the one reader of leg names for the leg-stop and index-exit lines) used `describe_contract`, the
ISO record form, so the line printed the catalogue row's raw `YYYY-MM-DD` (on the PC: 2028-12-01) where every screen
prints "1 Dec".

## Class: every place a contract's expiry is printed or derived for a what-if line

| Place | Name / date form before | Date used in the figure? | This branch |
|---|---|---|---|
| `leg_stop_answer` (Stops panel, GET leg-stop-risk) | ISO via `names_and_terms` | no (at-expiry; groups legs) | fixed: screen form |
| `paper_monitor._max_loss_line`, leg stop (fired pop-up, History) | ISO via `names_and_terms` | no | fixed (same reader) |
| `index_exit_answer` (index exit fired) | ISO via `names_and_terms` | no | fixed (same reader) |
| `paper_monitor._contract_text` (fired body "exited ... at") | screen form already | no | none needed |
| `paper_exit_risk` (exit confirm, routes/paper.py ~1523) | ISO, own loop | no | NOT edited (Lane U: exit confirm) |
| `ContractTerms.expiry` -> `book_extremes` / `exit_risk._naked` | not printed | multi-expiry check, cover by later expiry | none: read as stored |

Size: 3 of 4 printed what-if names fixed (one reader); 1 left (exit confirm, Lane U). Old stored fired-stop lines keep
their text (stored text is never rewritten; `paper_exit_less_protected` takes any leg text, so both forms read back).

## Wording proposal (NOT built, pending owner read)

Spec basis: ADR-330 (6) "If this stop fires, max loss becomes Rs X (now Rs Y)". Both keep the engine figure.

- A (recommended): "If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25): the worst case if NIFTY
  fell to zero, with NIFTY 1 Dec 25750 PE sold and no bought put protecting it."
- B: "If this stop fires, NIFTY 1 Dec 25750 PE is left sold with no bought put protecting it. Worst case, if NIFTY fell
  to zero: a loss of Rs 16,62,316.50 (now Rs 1,732.25)."

## To file as deferred issues

1. The 2028 year (data): on the PC run and send back
   `SELECT id, name, instrument_type, strike, expiry, exchange_token, first_seen_at, last_seen_at, currently_listed FROM public.catalogue_contracts WHERE id IN (SELECT DISTINCT contract_id FROM public.paper_orders WHERE strategy_id = 194);`
   If `expiry` reads 2028-12-01 the row is wrong at the source: the next query is the row's revision history and the
   loader run that wrote it. The screen form "1 Dec" now hides the year in this line, so the data issue must not wait.
2. Exit confirm (`paper_exit_risk`, Lane U area) names legs in ISO form: same one-line fix (`display_contract`), or
   have it call `names_and_terms`.
3. Other `describe_contract` uses that reach a reply's `contract_text` (routes/paper.py ~604, 637, 878, 1787, 2024):
   check each is reformatted by the screen before it is shown.
4. The wording proposal above (owner read).
5. Tier A review F1 (MINOR, class open): `display_contract` has no year rule, while the frontend's `expiryText`
   (displayFormat.js, REQ-148 AC-2) prints the year when the expiry is not in `shown_date`'s year. So for a 2028 row
   the Stops label reads "NIFTY 1 Dec 2028 25750 PE" and this line "NIFTY 1 Dec 25750 PE"; two contracts a year apart
   name alike. Fix: the server form takes the same year rule (one helper, used by this line, the fired-stop body and the
   alert titles). Until then the year is visible only in the leg label, so item 1 (the data) comes first.
6. Tier A review (outside this diff): in a two-expiry PE book, a stop on one long put made `exit_risk` report BOTH
   short puts exposed (the engine's cover-by-later-expiry rule). Check it is intended.

## Re-test on the PC (paper only)

1. Pull `hotfix/maxloss-line-1127`, restart the API.
2. Positions > Paper > B-N1 > Stops. On NIFTY 1 Dec 25650 PE type a stop "Above 102.55". Expected, exactly:
   "If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25). Sold option with less protection: NIFTY 1
   Dec 25750 PE." (figure unchanged; no ISO date, no year).
3. Run the SQL in deferred item 1 and send the rows.

## Tier A review (Opus, fresh context, read-only) of `git diff 206a9f0 HEAD`

PASS, no critical or major finding. F1 (no year rule on the server name form) and F2 (exit confirm still ISO) are
deferred items 5 and 2; F3 (engine test pins Decimals; the rendered 7-digit Indian grouping is pinned by the two
tests_app m1 tests) accepted; F4 (an extra blank line) fixed. Hand-checked: 90 + 100 - 60 - 56.65 = 73.35 x 65 =
4,767.75; -1,732.25 now; 11,433.50 - 1,673,750 = -16,62,316.50 after. Callers of `names_and_terms`: the leg-stop route
and `paper_monitor._max_loss_line` only; stored lines written before the change still read back.

## Push

Pre-push gate: `scripts/orchestrator/prepush.py` on the pushed head (result in the commit after the push, or below).

Push 1: ffeb6dd, `scripts/orchestrator/prepush.py` TOTAL PASS 2180 s (the first run, on the same head, failed only
the three frontend steps: `frontend/node_modules` was missing in this container; `npm ci`, then the second run).

## Item 2: a fired index exit quotes the tick it fired on (coordinator 11:10 IST)

Spec basis: REQ-100, ADR-330 (41) (a fired stop's alert uses the real exit price), D-22 / #734 (the reason carries the
index value at that moment, "not available" when unknown).

- RCA (one sentence): `_index_at_fire` returned the provider's held index reading (`_index_now`) before the crossing
  tick, so the decision (the tick in `on_quote`) and the quoted value were two readings; a later tick back across the
  level, already held while the crossing tick waited in the fan-out queue, was quoted.
- Fix (7a168c1, 9f2d810): a conditional exit always quotes its own crossing tick (`price.price`; a missing value is
  "not available", never the held reading). Leg stops: decided on the leg tick, which is already the recorded exit
  price (`_exit_prices`); their "NIFTY was at" stays the held index as context (review F2: can be later than the leg
  tick by the queue delay; it is not a level the decision used).
- Failing first: `tests_app/test_paper_monitor.py::test_m2_*` (two tests: a held reading that differs; the #196 shape,
  ticks 22,849.95 then 22,850.20 queued before one step, no stand-in). Both fail on the 206a9f0 code ("NIFTY was at
  22,850.20"), pass with the fix; the file: 32 passed; `test_exit_door.py` 37 passed.
- Tier A review (Opus, read-only): PASS, three minor; F1 (fallback to the held reading when the price is None) and F3
  (the two-tick test) taken in 9f2d810; F2 recorded above.
- Class, every fired reason and the value it quotes: index exit (fixed); leg stop (exit price = deciding tick, index
  context = held reading); settlement (`paper_settlement.py`: price and reason from the same close); rule alerts
  (`background.raise_actionable`: the confirming sample's numbers); plan stop / time exit (`routes/plan_watch.py`,
  Lane J: not touched, listed).
- To file as deferred issues: (a) store the deciding tick's own time with the value (today the reason holds the value
  and the order's placed_at the fire clock, not the tick's timestamp): needs a column (migration, tonight) or a reason
  wording change (owner read); (b) plan stop / time exit reasons (Lane J) to be checked against the same rule;
  (c) leg stop: whether "NIFTY was at" should be the index reading at the leg tick's time.
- PC re-test: set a conditional exit "NIFTY above <a level just above spot>" on a paper trade; when it fires, every
  exit order's reason reads "NIFTY was at <a value at or above the level>". Paper only.
