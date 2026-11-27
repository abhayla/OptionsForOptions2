# Lane M results: the leg-stop max-loss line (27 Nov 2026)

Coordinator lines (send_message to "@parent" was refused: `elevated_session_untrusted_device`; written here instead):

- LANE M ALIVE (09:46 IST)
- LANE M RCA (10:25 IST, after the 09:50 correction): the figure is right (bought 25650 PE stopped at 102.55 leaves
  the sold 25750 PE bare: 11,433.50 - 25,750 x 65 = -16,62,316.50, pinned through the engine). The date is printed by
  `routes/paper.py::names_and_terms`, which named every leg of the line with `describe_contract`, the ISO record form
  "NIFTY 25750 PE <catalogue expiry>", where every screen uses `display_contract` ("NIFTY 1 Dec 25750 PE", REQ-151).
  The YEAR is the catalogue row's own stored expiry (`catalogue_contracts.expiry`), printed as is: no code on this head
  builds 2028 (the refresh refuses an expiry move of more than 6 days, ADR-059; the test seeder runs on CI only), so the
  PC's row for that contract must read 2028-12-01: SQL below. It is not used in the figure (at-expiry payoff; the
  expiry only groups legs), but it would be used by anything time-based (Greeks, days to expiry, settlement).
- LANE M PUSH 1: see "Push" below.

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

## Re-test on the PC (paper only)

1. Pull `hotfix/maxloss-line-1127`, restart the API.
2. Positions > Paper > B-N1 > Stops. On NIFTY 1 Dec 25650 PE type a stop "Above 102.55". Expected, exactly:
   "If this stop fires, max loss becomes Rs 16,62,316.50 (now Rs 1,732.25). Sold option with less protection: NIFTY 1
   Dec 25750 PE." (figure unchanged; no ISO date, no year).
3. Run the SQL in deferred item 1 and send the rows.

## Push

(filled at push)
