STATUS 19:00 | item 1 (I-48): PARTLY fixed, committed 14d097334 (9 rows 219 -> 162 statements); item 2 (I-08): covered by item 1's tests; items 3 to 7: not started | next push 22:30 (batch 1) | blocker: send_message to @parent refused (elevated_session_untrusted_device), so this line is the report; the orders and traded-contracts reads per row sit in adjustment_readers.py (not mine), see "For the owner lane"

# Lane B3 results (28 Nov 2026)

Highest status claimed: Fixed, not tested on the PC.

## Item 1 (I-48): plan watch, nine rows
Real case (plan row I-48): "Plan watch answers in 6 seconds or more and the Positions page sends 34 requests a minute".
Core test: `tests_app/test_plan_watch_batch_b3_1128.py::test_nine_rows_statement_ceiling_and_each_row_its_own`.

| Measured (cloud DB test, 9 running rows of scenario ADJ-01) | Before | After |
|---|---|---|
| Statements for one batch of 9 rows | 219 (24 a row) | 162 |
| Single route plan-watch (ceiling in test_route_latency_budget.py) | 27 | 26 |

What is read once for all rows now (`routes/plan_watch.py::prefetch`, used by `routes/plan_watch_batch.py`):
- each row's stored triggers (still one read per row, moved to the prefetch), the contracts those triggers name (ONE
  `tracked_contracts.resolve` for all rows: 2 statements instead of 2 per row), the position kinds (ONE `kinds_of`);
- the expiry kind: the first row reads the stored catalogue, later rows of the same (underlying, nearest expiry)
  reuse it through `read_tracked`'s own `kinds` argument (the worker's #864 path);
- the screen-isolation read ran twice a request (`watch_of` and `run_check`): once now (the single route is one
  statement lighter too).
Fail closed: a prefetch that fails (database or anything else) changes nothing for the rows: each reads for itself, as
before. A key the prefetch did not read is read by the row. Every row's answer equals its single route's answer (the
test compares all 9) and its armed index exit shows its own level (23400 + 10 k): a row never shows another row's figures.

NOT done (honest): the target "orders, contracts and settings read once for all rows" is only partly met. Settings
were already one read per request (app_settings and the user's preferences, 2 statements, not per row). The orders and
the traded contracts of a row are read inside `read_tracked` (`adjustment_readers.py::_tracked_on`), and the plan, facts
and records inside `routes/adjustment_check.py::run_check`; both are not in my May edit list. About 18 statements a row
remain.

## Item 2 (I-08)
Covered by item 1's tests, no separate change: 9 rows come back `ok` with lines in one batch read; a row whose read
fails is `refused` with its catalogue sentence and status while the other 8 stay `ok` and equal their single route
(`test_a_failed_shared_read_fails_no_row_and_a_failed_row_is_its_own_refusal`); a row the one time budget did not reach
stays `not_read` (existing #859 tests, still green). No feed-frame recording was added: the batch route's rows
come from the same `watch_of` the page already reads.

## For the owner lane
- Whoever owns `backend/ofo_app/adjustment_readers.py` and `routes/adjustment_check.py`: give `read_tracked` an optional
  `prefetched` argument (orders by strategy from `paper_book.load_owned_many`, contracts from one
  `tracked_contracts.resolve` of all rows' order contract ids), and let `run_check` take the plan and facts reads for
  many ids. Expected: about 9 statements a row saved on the orders and contracts alone. Then lower `BATCH9_CEILING` in
  `tests_app/test_plan_watch_batch_b3_1128.py`.

## Decided for the owner
- The prefetch failing is never a reason to refuse a row (fail closed per row, same answers as the single route).

## Question for the owner
none

## New wording for the owner to read
none yet

## New test files
- tests_app/test_plan_watch_batch_b3_1128.py (for Lane Z3 to register in PR241_SELECTION)

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 and 2, build and tests | Sonnet (this session) | about 25 |

## Not done
Items 3 to 7 (batch 2).
