STATUS 06:32 | item 1: PASS pushed @2cad4f3; item 2 (I-125): PASS, push pending gate | next: item 3 (I-80) | blocker: none (parent session refused my message: untrusted device; this line is the report)

# Lane TF results (branch test/r2-gaps-1128, base integration/weekend-1127)

Status wording: highest claim is "Fixed, not tested" for product; these are tests only.

## Items
| # | Item | State | Test / count |
|---|------|-------|--------------|
| 1 | I-51 stops warning | PASS, pushed 2cad4f3 | tests_app/test_leg_stop_lines_tf_1128.py: 9 passed (fresh PostgreSQL 16, ofo_app role). Mutation: removing "(worst case: {index} at zero)" from the template makes 5 of 9 fail; reverted. |
| 2 | I-125 | PASS | tests_app/test_plan_rebuild_tf_1128.py: 2 passed (worker as its own process, PATH-90, private database). Mutation: REBUILD_SECONDS 10 -> 20 makes both fail; reverted. |
| 3 | I-80 DB half | not started | |
| 4 | I-74 browser | not started | |
| 5 | Whole tests_app suite | not started | |

## Defects found
- (item 1, observation, not a defect) ADR-330 (55) F2 case: a bare put whose max loss comes from elsewhere prints
  "Max loss then: Rs 17,65,125.00." with no case named (tests_app/test_leg_stop_risk.py, test_55_review_f2). The loss
  figure is then not labelled "worst case"; this follows the ADR text ("named only when true"). If the owner wants every
  figure labelled, that is a wording decision for a fix lane.

## Decided for the owner
- Item 1: "short" pinned as each line at most 80 characters (real longest is 59), exactly three lines, one fact per line.

- Item 2: the wait window is 10 s + 4 s slack counted in polls (no clock read, tests/test_no_wall_clock_asserts.py). The
  slack covers one re-list's run time; Lane TE's 15 s is outside it. Observable used: the worker's own log line
  "background: N strategies monitored" (written at the end of every rebuild), no product seam added.
- Item 2: the plan-removed direction was not tested (the table that holds a plan was not verified); not claimed.

## For the owner lane
- none yet

## Pending owner read (new on-screen sentences)
- none (tests only)

## To file as deferred issues
- none yet

## Set-up notes
- No scripts/orchestrator/cloud_services.sh in this branch: used `pg_ctlcluster 16 main start`, redis-server, roles as
  app-tests.yml, `pip install -r requirements-app.txt -r requirements-dev.txt` (container had none).

## Models
| task | model | minutes |
|------|-------|---------|
| item 1 | Sonnet | 20 |
| gate runs (3, env fixes) | Sonnet | 60 |
| item 2 | Sonnet | 25 |
