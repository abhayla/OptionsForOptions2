# Archived-branch audit, 2026-11-07 (GC-MERGE1 amendment 1)

Question per branch: is its behaviour already in the integrated tip `a4b9b339` (feature/adjustments, landed on main
by PR #665), the same or another way? Read-only audit (git grep and read at the tip, `gh pr view` / `gh issue view`).
Owner decision 2026-11-07: "no new implementation, just merge all the code ... For the parked items, keep them
parked." All 14 PRs below are parked under #605 ("held for the live Kite gate", 2026-10-29; order path out of scope per
ADR-165), so none is merged. Each keeps an archive tag, which is its resume point. Full parked list:
`docs/process/parked-register-2026-11-07.md`.

Verdicts: PRESENT (in the tip), PARTIAL (part missing), MISSING (not in the tip), OBSOLETE (spec changed). No branch
is OBSOLETE: ADR-092, ADR-119, ADR-121, ADR-125, ADR-127, ADR-128 and ADR-083 are all accepted. Conflict counts are
CONFLICT lines from `git merge-tree --write-tree a4b9b339 <branch>`, so treat them as a rough size.

| Branch (PR) | Verdict at a4b9b339 | Evidence | Issues | Value | Conflicts | Resume tag |
|---|---|---|---|---|---|---|
| build/fix-381-257 (#394) | MISSING | `routes/execution_return.py:167` reads orders before trades; branch swaps the order and adds `TradeWithoutOrder` | #381 open | High per line (a race can lose a trade) | 2 | archive/2026-11-07/build/fix-381-257 |
| build/338-353-gate-fixes (#418) | MISSING | `margin_gate._derive` blocks a 0-margin closing basket on a negative balance; `kite_http.py:66` flattens the per-module allow-list | #338, #353 open | High | 19 | archive/2026-11-07/build/338-353-gate-fixes |
| build/255-never-split (#420) | MISSING (its scope) | Complete/Retry/exit still slice with placeholder `DEFAULT_FREEZE_UNITS = 1755` (`execution/sequence.py:85`, `partial.py:715,836`); no `require_within_freeze` | #255, #43, #63 open | High (orders) | 10 | archive/2026-11-07/build/255-never-split |
| gc6/422-freeze-types (#456) | MISSING | `execution/freeze.py:43,61` no TypeError for a non-StoredFreeze; `rules/model.py:101` no naive `as_of` refusal | #422 open | Low-medium | 10 | archive/2026-11-07/gc6/422-freeze-types |
| build/352-1-next-day (#421) | PARTIAL | Migration 0019, `reconciliation_store.py`, `unresolved_from_positions` present; `next_day_resolution.py` absent | #352 open | Medium-high | 3 | archive/2026-11-07/build/352-1-next-day |
| gc6/token-return (#453) | MISSING | no `read_refusal`; `routes/execute.py:175` answers `gate_broker_unconfirmed` for a read failure | — | Low-medium (message only) | 3 | archive/2026-11-07/gc6/token-return |
| gc6/dup-tag (#454) | PARTIAL | `execution_return.py:137` catches only "more filled than planned"; not a cancelled 0-fill twin or a working twin | — | Medium-high (double orders) | 3 | archive/2026-11-07/gc6/dup-tag |
| gc6/mkt-hours (#455) | PARTIAL | Gate present (`market_calendar.py:110,120`, `routes/execute.py:66`, `safety.py:358` MARKET_CLOSED); missing GET `/execute/market-status`, the disabled Execute screen, the clock-read fix | — | Medium | 10 | archive/2026-11-07/gc6/mkt-hours |
| gc6/kill-switch (#463) | MISSING | `broker/flags.py:17` mentions it only; no owner-switch route or Execute gate | — | High (emergency stop) | 12 | archive/2026-11-07/gc6/kill-switch |
| gc6/instr-fresh (#459) | MISSING | no `INSTRUMENT_LIST_PUBLISH_IST` in code (only `spec/findings.md:830`) | — | Medium | 4 | archive/2026-11-07/gc6/instr-fresh |
| gc6/net-roundtrip (#470) | MISSING | no `next_day_resolution.py`; nothing decides earlier-day plans from the next-day net | #352 open | High | 3 | archive/2026-11-07/gc6/net-roundtrip |
| gc6/380-2 (#478) | MISSING (old path live) | `routes/execute.py:535` still calls `ep.strategy_blocked`; `reconcile_attribution.py` used only by `routes/positions.py:108` | #380, #605 open | High (two money routes can disagree) | 6 | archive/2026-11-07/gc6/380-2 |
| build/W-124-a3-chain (#509) | PARTIAL | `engine/chain_values.py` copied from it; missing `user_setting_store.py`, per-user strikes setting, chain preview (REQ-031 AC-14), stale-spot tests; its migration 0022 number is taken | — | Medium (display) | 12 | archive/2026-11-07/build/W-124-a3-chain |
| build/c4-row-31b (#557) | MISSING | REQ-085 exists; no `outcome/warnings.py`, no `unhedged_short`; itself parked (#558, Tier A MAJOR) | #558 open | Medium | 13 | archive/2026-11-07/build/c4-row-31b |
| docs/gclive-2026-10-30 (no PR) | PARTIAL, docs | `goal-contract-GC-LIVE-2026-10-30.md` absent; GC-LIVE2 contract lacks its LAND appendix | #606 open | Low (records) | 1 | archive/2026-11-07/docs/gclive-2026-10-30; **merged** (the two files) in the GC-MERGE1 docs PR |

Stashes: `archive/2026-11-07/stash-2026-10-24` and `stash-2026-10-08` hold 0 changed lines against their base commits
(`git diff <tag>^1 <tag>` is empty). Nothing to keep beyond the tag.

How to resume one (from #605's rebuild order): `git checkout -b <new> <resume tag>`, `git merge origin/main`, resolve,
run the branch's own tests and the guard tests, then the normal gate and a Tier A review (order path).
