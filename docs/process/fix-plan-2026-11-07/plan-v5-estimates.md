# Fix plan v5 estimates - re-review of v4 under kit 1.21 and the new plugins (7 Nov 2026 ~02:4x IST); NOT approved

Inputs: plan-v4.md + code-checks.md; kit 1.16 -> 1.21 (PR #635: graph.py impact/affected/brief/tier/pin/suspects);
plugins ponytail (smallest complete change) and pstack (manual-only skills). Code has not changed since the checks
(`git diff --stat 514113f1 HEAD -- backend frontend/src tests tests_app` empty), so file:line in code-checks.md holds.

## Findings of the re-review
1. v4 arithmetic: lane B items sum to 890 min (~14.8 h), not ~13 h.
2. Lanes are not file-disjoint (v4 said they were): routes/paper.py (B 80/30/84 and D 40/41/21),
   routes/adjustment_check.py (A 88 and B 79/77), StrategyBuilderPage.vue (B 15/52/84, C 48, D gate :143).
3. Three owner decisions were sized below their text:
   - ADR-262 (83): three placement methods (delta, SD, points) + wing-width setting + Preferences control; v4 sized delta only.
   - ADR-263 (4): after-charges + label on ~10 surfaces (max profit/loss, profit/loss left, payoff graph and table,
     P&L totals, booked/unbooked, history, Completed) + a "before charges" fallback; v4 gave 120 min.
   - ADR-264 lock: lock flag + writers refuse + admin switch + greyed "Set by admin" + optional min/max; v4 gave 60.
     ADR-264 (1) "every number is a setting" stays out of v4/v5 (unmeasured), as v4 recorded.
4. Kit 1.21 tier paths (`**/alembic/**` = Tier A): 65 (re-baseline marker), ADR-270 (entry IV column), 68 (link
   between old and new strategy) add migrations; one combined Tier A review of the migrations (~1 h). No item hits
   the project's money/orders/broker tier paths (paper orders live in routes/paper.py).
5. Kit 1.21 graph: `affected --files` is transitive: templates.py reaches 601 test files, routes/paper.py 230,
   background.py 130, legEdit.js 43. Builders run the changed file's own tests; the full set runs once at the merge gate.
6. Gate: 3 of the 5 failures are already fixed by the kit merge (finding scope, spec digest, coverage rows 5a498300);
   left: test_select_app_tests entry, StrategyBuilderPage.vue maths into lib, openapi.json (~35 min).
7. `graph.py brief` needs a W-item; these issues have none. Lane briefs carry `graph.py affected --files <files>`
   output instead (same blast radius, no 30 new records). 128 unpinned W-items are not touched by this plan.
8. Plugins: ponytail cuts little, because almost every item is an owner decision (ADR-255..274). Candidates it does
   cut are tooling (61, 62) and keeping 20 to reuse existing rules. pstack changes nothing (manual skills only).

## Updated minutes (builder, code + unit tests of the changed code)
| Lane | v4 | v5 | Change |
|---|---|---|---|
| A rule engine, alerts | 685 | 685 | none |
| B Compare, orders, exits, history | 890 (stated 780) | 890 | arithmetic only |
| C builder, data, settings (without 4) | 650 incl. 4 | 850 | 47 90 + lock 150 + 83 200; 4 moved to D |
| D display, tooling, gate (+ 4) | 485 | 640 | gate -25, ponytail -60 (61/62 locate only), 4 (ADR-263) 240 |
| **Builder total** | **~42 h stated (2,710 min)** | **~51 h (3,065 min)** | |

## Elapsed
| Step | v5 |
|---|---|
| Longest lane (B) | ~15 h |
| Tier A review of the 3 migrations | ~1 h |
| Merge 4 lanes (3 shared files) | ~2 h |
| Full gate once + fixes (last full run failed 5 steps) | ~1.5 h |
| One screen test of every fix (test data, Chrome) | ~3 h |
| **Total** | **~22 h (about 3 long sessions)** vs v4 ~16 h |

Options: defer 68 (-4 h builder, longest lane ~14.2 h (C), elapsed ~21 h, and one fewer migration); 68 deferred + split
B or C into a 5th lane: elapsed ~18 h. Risks: 70/17 cause not found (+1-2 h); 65 DB repair size (+1 h); 5/46/13
unlocated; past measured rows ran ~30% over code-read estimates.
