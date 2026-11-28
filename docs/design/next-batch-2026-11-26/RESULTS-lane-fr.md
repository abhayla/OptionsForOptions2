STATUS 08:30 | items 1-6: Fixed, not tested live (tests green; Opus review and pre-push gate pending) | next push: after the review | blocker: none

# Lane FR: readers and evaluators the worker depends on (28 Nov 2026)

Branch `fix/r3-readers-1128`, from `origin/fix/r2-worker-issues-1128`. Spec basis: ADR-330 (44), (47), (58), (66);
ADR-016 to ADR-019; REQ-115 (AC-3, AC-4, AC-6); REQ-165 AC-6; REQ-049. Paper only; no broker order endpoint; money Decimal.

## Core proof (item 1, before any other code)

Compare test `tests_app/test_screen_expiry_fr_1128.py`, a calendar trade listed far-leg-first (28 Dec before 9 Nov):

- Red on the base: `WORKER expiry [datetime.date(2026, 11, 9)] SCREEN expiry [datetime.date(2026, 12, 28)]`
- Green after the fix: the screen's first chain read is 9 Nov, 28 Dec is never asked, and the screen's `vol` and
  `expiry_kind` equal the worker's. (The screen also reads the A-04 later-expiry rows, 17 Nov, by design.)

## Items

| # | Issue | Change | Test (red first) | Result |
|---|---|---|---|---|
| 1 | 863 screen half | `read_market`: `expiry = min(x.expiry for x in position.legs)` | `tests_app/test_screen_expiry_fr_1128.py` | red 28 Dec vs 9 Nov, then green |
| 2 | 864 reader half | `read_tracked(..., kinds=None)`, `_tracked_on`, `_stored_kind_or_empty(..., kinds)`; `READER_TAKES_KINDS = True` | `tests_app/test_reader_kinds_fr_1128.py` (record given: no catalogue read; none / empty / other key: one catalogue read) | green; FE2's `test_kind_cache_fe2_1128.py` updated to the flag's new value, green |
| 3 | 860 | `_t10b`: `_limit` only when `days_left is not None` | `tests/adjustment/test_playbook_eval.py` (unknown kind: fires at 14:31 on expiry day, not due at 14:29, `waits_expiry_day` two days before) | red `no_expiry_values`, then green |
| 4 | 861, 866 | `_stop_answer`: no stops and no days left -> `sl.not_checked_code(sl.EXPIRY_KIND_UNKNOWN)`; `stops_of` line reason `EXPIRY_KIND_UNKNOWN` for an empty kind | `test_playbook_eval.py`, `tests_app/test_settings_in_force.py` | red on base (stash check), green; stated kind unchanged |
| 5 | 879 heartbeat | `judge_heartbeat`: ahead of the reader by more than `HEARTBEAT_SKEW_S` (5 s) -> `unreadable` (never fresh) | `tests_app/test_worker_heartbeat.py`: 3 s and 5 s ahead fresh; 6 s, 100 s, 120 s ahead not fresh; 121 s old stale | red on base, green |
| 6 | K2 F1 | `entry_facts_now`: feed down + `confirmed` uses `_index_value_not_live`; optional `feed` holds an unsubscribed index (`_index_quote_held`, shared with `_index_spot_held`) | `tests_app/test_index_one_rule.py` | F1 confirmed red (ticked, feed down, value held: None), then green |

Neighbour files re-run green: test_adjustment_readers, test_adjust_compare_two_expiry_paper, test_worker_j3,
test_entry_atm_iv, test_monitoring_state, test_monitoring_status_route, test_live_feed_status,
test_dropped_and_skew_fe2_1128, test_monitor_reports_fe2_1128, test_background_cycle, test_background_day_open_margin,
`tests/adjustment` (1285). Ruff ratchet: OK, no rule rose.

## For the owner lane

1. `backend/ofo_app/templates.py` (Lane FC3): add `_trig("expiry_kind_unknown", ...)` with the proposed words under "New
   wording"; `backend/ofo/adjustment/stop_lines.py` (Lane FE2): `NOT_CHECKED[EXPIRY_KIND_UNKNOWN] = f"{_T}expiry_kind_unknown"`
   (currently `f"{_T}missing_days_left"`), pointing at `adjust_trigger_expiry_kind_unknown`. Until then the "days left
   not available" sentence stands. A test in this lane pins the current mapping
   (`tests_app/test_settings_in_force.py`: `not_checked_code(EXPIRY_KIND_UNKNOWN) == "adjust_trigger_missing_days_left"`);
   it changes with the mapping.
2. `backend/ofo_app/monitoring_state.py` (Lane FE2): `CLOCK_SKEW_S: Final = 5` -> `CLOCK_SKEW_S: Final = feed_bus.HEARTBEAT_SKEW_S`
   (one home; `monitoring_state` imports `feed_bus`, so the constant lives there). A test here holds them equal.
3. `backend/ofo_app/routes/paper.py` (Lane FD3), `entry_facts` (line ~1349): add a `feed` argument and pass it:
   `return await entry_facts_now(ctx, underlying, sold, confirmed=confirmed, feed=feed)`; the caller that has the feed
   passes it. `backend/ofo_app/routes/execution_return.py` line ~302: `entry_facts_now(req.market, world.underlying, sold, feed=<the route's feed>)`
   if it has one. Until then the first-fill reader reads the book as it is (as before).
4. Z review minor (the time of a not-live starting point): through `record_basket_facts` the held not-live value from
   `_index_value_not_live` becomes the basket's `spot` without its time. Carrying it needs a field on
   `entry_facts_store.BasketFacts` (e.g. `spot_at`) and `_index_spot_held` returning `(spot, at)`; `entry_facts_store.py`
   is not on this lane's list. Written down as the gap; nothing stored today says the value was old.

## Decided for the owner

- Unknown-kind stop answer: `stops is None` and `days_left is None` is the unknown-kind state (that is how
  `adjustment_check.state_of` builds it); `stops is None` with a stated `days_left` stays "stop lines not supplied".
- A heartbeat more than 5 s ahead keeps the existing answer `unreadable` (not `stale`): not fresh either way; the
  banner that reads it is unchanged.
- `entry_facts_now` takes `feed` as an optional keyword (default no hold) so the two existing callers keep working
  until the route lane passes it.
- `read_tracked` reads the worker's record only for the nearest leg's key `(underlying, min leg expiry)`; an empty
  record entry reads the catalogue (the worker records only a non-empty kind).

## New wording for the owner to read

Proposed by FE2, unchanged here, to be added by FC3 (this lane does not touch `templates.py`):
"Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value."

## Question for the owner

None.

## Not done

- Opus review of the whole diff and the pre-push gate (`PREPUSH_JOBS=1 python scripts/orchestrator/prepush.py --jobs 1`):
  see the STATUS line for their state.
- `tests_app/test_entry_facts.py` was slow on the cloud database; see its result below if listed.

## PC steps

Market closed: run the new tests one file at a time through
`python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py` for
`test_screen_expiry_fr_1128`, `test_reader_kinds_fr_1128`, `test_index_one_rule`, `test_worker_heartbeat`,
`test_settings_in_force`; and `python -m pytest tests/adjustment/test_playbook_eval.py`.
Live: with a far-leg-first calendar trade open, the strategy page's market read and the worker's monitoring state show
the same nearest expiry; stop the worker clock ahead (or the feed) and tick "prices are not live" on a first fill: the
entry facts are stored with the held index value.

## Tasks

| task | model | minutes |
|---|---|---|
| items 1 to 6, tests, RESULTS | Sonnet (this lane) | about 60 |
| review of the whole diff | Opus | pending |

SAFE TO CLOSE: not yet (review and gate pending)
