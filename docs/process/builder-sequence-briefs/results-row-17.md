# Row 17 (W-145) check results - UX levels removed (recorded by the orchestrator from the checkers' reports)

Checked against ADR-168 (4)(5); REQ-006 and REQ-007 are Superseded, so no AC evidence files are written for them.

## Round 1 - fresh Opus checker, chunk head 412b56c6 (brief `verify-row-17.md`)
| # | Verdict | Screen / route | Exercised there | Result line |
|---|---|---|---|---|
| 1 spec | pass | spec | n/a | 75 level-word hits in 27 files, all difficulty labels / guided path / "Standard deviation" / superseded / superseded-notes; safety clauses intact |
| 2 one column set | pass | POST /api/strategies/outcome | yes (ASGI, recorded replay) | `order equal: True all visible new: True` (44 columns = the old Advanced list) |
| 3 request handling | pass | same route | yes | `ux_level` guided/list -> 200 same body; unknown key -> 422; no `ux_level` in the response |
| 4 leg_quotes | partial | same route | yes | session ended -> NOT_CONNECTED still carried stale Bid/Ask (MAJOR) |
| 5 builder screen | pass | /strategy/builder | yes (vitest mount) | 131 passed |
| 6 Create Strategy | pass | /strategy/create | yes (vitest) | guided link carries only `draft`; manual path opens an empty builder |
| 7 Execute / live card | pass (code), untested | Execute page, live card | code read | MINOR: no test pinned it |
| 8 mutation | 4 of 4 killed (+1 extra survivor = finding 2) | scratch copies | yes | see report |
| 9 gates | pass | gates | yes | tables/outcome 141, guard 1409, repo_scan 1242, reach_check exit 0, app (no DB) 274, vitest 131 |

## Fix round 1 - 90d3a2bc
`leg_quotes` only when the outcome state is COMPUTED (also closed a REFUSED leak); failing test first; mutation gate 3/3
killed; frontend tests that the Execute page and the live card send no level key.

## Round 2 - findings-only Sonnet checker, 90d3a2bc
Finding 1 PASS (session-ended test passes; own probe: REFUSED with no data -> `leg_quotes present: False`); finding 2
PASS (level key re-added in a scratch copy -> `Failed Tests 2`). `tests_app/test_outcome_route.py`: 8 passed.

## Deferred (issue #532)
RD-130/131/141 text still describes Advanced-only gates (refresh at rows 19-20); the brief's "Q264 still open" was
written from memory (Q264 was decided before chunk 2).
