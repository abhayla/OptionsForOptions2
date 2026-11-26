# Lane J results (26-27 Nov 2026): the join of the screens line and the alerts-and-plans line

Branch `integration/nb-1126`, cut from `origin/fix/screen-findings-1126` (7bf64eb). Pushed only there; no PR.
Standing-direction step: step 4 (the journey for iron condor), owner-directed batch of 26 Nov (ADR-330; freeze lifted
for these items by the owner on 26 Nov, see RESULTS-lane-p.md). Highest status claimed for anything here:
**Fixed, not tested** (the owner tests on his PC in market hours, 27 Nov 09:15 IST).

Spec basis: ADR-330 (1) to (27) and its one-module instruction; ADR-002; ADR-003; ADR-008; ADR-016 to ADR-019.

## (a) PC set-up (do these first, in this order)

1. **Back up the database FIRST** (the PC's PostgreSQL is the owner's live one). In a terminal on the PC:
   `pg_dump -Fc -h 127.0.0.1 -U <owner role> -d <app database> -f D:\Abhay\backups\ofo-before-0054-2026-11-27.dump`
   Then check it: `pg_restore --list D:\Abhay\backups\ofo-before-0054-2026-11-27.dump | find /c "TABLE DATA"` must print
   a number above 0, and the file size must be above a few MB. Do not go on if either check fails.
2. `git fetch origin` and `git checkout integration/nb-1126` at the pushed head named in section (c).
3. `pip install -r requirements-app.txt` and `cd frontend && npm ci` (new packages may have come with the merge).
4. Migrate: `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`.
   The PC is at `0053_close_finished_strategies` (the screens line). This runs exactly two migrations, both additive:
   `0054_actionable_alert_answers` (new NULL columns on `adjustment_suggestions`; old rows read as adjustment rules)
   then `0055_plan_stop_base` (`stop_base JSONB NULL` on `strategy_adjustment_plans`). No row is changed or deleted.
   Treat 0054 as one-way: never run `alembic downgrade` (its downgrade refuses once new alerts exist).
5. Post-migration checks: `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini current`
   must print `0055_plan_stop_base (head)`.
6. Restart: stop and start the API, the background worker supervisor (`python scripts/orchestrator/supervise_worker.py`),
   and rebuild the frontend (`cd frontend && npm run build`).
7. In the browser: (a) Positions > Adjustment opportunities still lists the old records; (b) Alerts > Active opens and
   its row count equals the bell number.

## (b) Screen-check list (owner, market hours; live-price checks first)

(written as each step lands; see below)

## (c) What is merged, what is left out

| Head | Commit | Status |
|---|---|---|
| fix/screen-findings-1126 (Lane R, base) | 7bf64eb | base |
| fix/ic-live-test-1123 (ADR-330 answers, docs) | 2ed05a7 | merged |
| feat/nb-plan-alerts-1126 (Lane P first push) | 7bca124 | merged |

### Merge 1: fix/ic-live-test-1123

| File | Conflict | Resolution |
|---|---|---|
| docs/process/coverage-stages.yaml | both added issue rows | union: the base's rows kept (ADR-327 to ADR-329), #742 and #743 added |
| docs/process/coverage-register.md | generated | regenerated (`coverage.py . --write --no-gh`; `--check` OK) |

### Merge 2: feat/nb-plan-alerts-1126

20 files were changed on both lines since they parted (e01f747); 17 merged without a text conflict. Three conflicts:

| File | Conflict | Resolution |
|---|---|---|
| backend/ofo_app/paper_settlement.py | both added a module constant (`_MIDDAY`, `_ZERO`) | both kept |
| tests/orchestrator/test_select_app_tests.py | both added app-test selection pins | both sides' pins kept |
| tests_app/test_order_closure_all_routes.py | both added route edges and the count line | both edge sets kept (level_watch, monitoring_pause, alerts, plan_watch); `PINNED_EDGE_COUNT` = 37 at the fork + 4 + 4 = 45 |

Generated files after the merge: spec digest, coverage register, `docs/api/openapi.json`
(`generate_openapi.py` output byte-identical), `tests_app/reply_inventory.py` (`--check` exit 0, notes unchanged): all
current, none hand-edited.

### Breaks the merge caused (each line passed its own gates; the merged tree did not)

| Gate | What failed | Fix |
|---|---|---|
| ruff ratchet | PLR2004 559 -> 560: each line added one magic number and removed another | `tests_app/test_paper_totals_closed.py` names its expected count |
| G2 `tests/test_paper_orders_one_door.py` (one exit door) | Lane P's `paper_leg_stop_risk` flipped BUY/SELL itself (`routes/paper.py:1523`) | the close's side and quantity come from `open_legs_to_close`, the door's own rule; `test_leg_stop_risk` passes |
| G4 `tests/test_alert_writers_one_caller.py` (one caller per alert writer) | still pinned `open_suggestion` / `record_held` to `background.py`; Lane P moved both into `actionable_alerts.py` | G4's homes follow the move (the plan: "guard G4 replaced (Phase 8)"); Lane P's one-module guard keeps every other caller out |

## Push log

| Push | Head | Contents | Gate |
|---|---|---|---|
| 1 | 7231916 | Step 1 (the two merges and the three breaks above) | `prepush.py --full` TOTAL PASS 2023.6 s (domain, app, vitest, lint, coverage, alembic guard) |

Coordinator message for push 1 could not be sent: the session-message service refused this session (untrusted
device); recorded here instead.
