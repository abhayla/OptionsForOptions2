STATUS 09:40 | pushed 69d66fe03 (gate TOTAL PASS): all earlier items incl. real exits read and both expiry_kind_unknown sentences | UX-A03 done, committed, gate running: keys paper_leg_stop_fired, paper_leg_stop_fired_unlimited, paper_leg_stop_fired_unknown (wrap with stop_fired_at / stop_fired_on) for Lane FE2 | UX-A18: cause found, not my file (paper.py line 1625) | not done: F5, UX-A05 (lane FJ), d36 (no PostgreSQL), screenshots | blocker: none

# Lane FC3 results

Branch fix/r2-plan-screens-1128 from origin/fix/r2-small-screens-1128. Paper only; no order endpoint touched.

## Item 1: plan acceptance (ADR-330 (45))
- The brief's sha `f963ab6` is a docs-only commit. The frontend change is in `234b3c4` and `eef8fbf` on origin/feat/0058-plan-acceptance-1127. I took the four named paths from that branch (diff of base...tip), merged the one conflict in AdjustPlanSheet.vue (kept our `savedSince(...)` guard and added `picked.value` to `fetchLevels`), kept Lane FC's `stopKindReason` line.
- Core: `npx vitest run tests/adjust-plan.test.js tests/plan-accept-signal.test.js` -> 2 files, 38 tests passed.
- Proof: `plan-accept-signal.test.js` "Use playbook as is sends PUT with the playbook and accept: true" and "a level edit with no pick sends no accept (never stamps)" both pass.
- The sheet only sends a flag; which stops a plan carries is decided by Lane FD's server half. So no Opus review was triggered by this item.

## Item 2: real trade exits
- TrackingPanel has a new prop `tradeMode` ('real' or default 'paper'); it passes `:exits-mode` to PlanEntry and skips `readExits` for 'real'. Tests: "tradeMode real: no GET of the paper triggers route; the card says the exits cannot be read here yet" and the paper default.
- Waiting on FD2: its branch fix/r2-backend-2-1128 is not on origin yet, so the real-mode read is not wired and the "cannot be read" case stays.

## Item 3
- UX-SW6: rules not checked are grouped by reason; 2 or more share a line "N rules not checked: <reason>" with the rules in a `<details>`; a lone rule keeps "Rule not checked: <reason>". Tests: 4 (17 same, mixed, two, one).
- UX-B13: MarginLine prints no "Checked at" when the time cannot be read. 2 tests.
- UX-A06/UX-A12: PlanWatch has a `closed` prop: the calm fact, nothing is read. UX-A09: with `stale` and a failed or unreadable read, it says the watch is paused with the feed and resumes with it. 3 tests.
- UX-A05 (Plan door on Live cards): not done, the card files are not in my list. See "For the owner lane".

## Item 4
- `stop_fired_at` and `stop_fired_on` now read "seen by the check at ..." / "seen by the check on <date> at ...". Updated the tests that carry the old sentence: tests_app/test_limits_now.py, test_fired_state_follows_record.py, test_closed_market_u311_u312.py, frontend/tests/check-refresh-u141.test.js, rules-line-u241.test.js. No golden file carried it (grep of the repo outside docs/design).

## Item 5
- #880: MonitoringBadge prints the date after the server's since text when `since_at` is readable and not today in India. 3 tests.
- #875: `DayLabel` uses an English table. Test sets `time.strftime` to answer in German (no other locale is installed here); red before, green after.

## Coordinator additions (05:25 and 06:15 IST)
- FB hand-over: PlanWatch has a prop `outcomeLoading`; true hides "Loading the rule check..." (1 test). The builder page (FB2) must pass `:outcome-loading="<its outcome is loading>"` to PlanWatch.
- FE hand-over: four plain sentences added in explanations.py: `monitoring_why_index_not_live`, `monitoring_why_leg_not_live`, `monitoring_why_exit_not_priced`, `monitoring_why_index_exits_not_run`; pins added to tests/errors/template_pins.json (also re-pinned stop_fired_at and stop_fired_on), 711 tests in tests/errors pass.
- Item 7 (D-5): PaperBookPanel.vue (line 137-140) already follows ADR-330 (56): the price time reads "As of", and only when the book has no price time does it print the server's answer time as "Checked at". So the "Checked at 03:22:40" is the server answer time (it moves on every read), printed because the book had no `last_price_at` while the banner showed the close time 15:29:58 from another source. Not changed: the fix is for the book read to carry the close time as `last_price_at` (server) or for the panel to take the banner's time; I could not see the banner's source in my files.
- F5 (move wording after an unknown outcome) and UX-A18 (the date in the Exit dialog): the F5 sentences live in usePaperExit.js / StrategyBuilderPage.vue / PaperStrategies.vue (FB2, FC2 files); not done. UX-A18: I found no sold-option date built in explanations.py; waiting for FD2's note.
- tests_app/test_d36_adjustment_counts.py: golden_d36 does not carry the stop sentences (grep). It needs the project's PostgreSQL (limited role, migrated); this container has none running, so it was not run: PC step: `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_d36_adjustment_counts.py`.

## 28 Nov 07:50 additions (coordinator)
- Real exits read wired: TrackingPanel reads `/real/strategies/{id}/triggers` for `tradeMode` 'real' (same reply shape); `exitsViewOf('real', ...)` now gives rows or none; "Exits of a real-mode trade cannot be read here yet." shows only for a failed real read. Note from FD2: that store holds rows only for stops set through the paper route, so a real trade usually answers an empty list; an empty list prints nothing (no claim of "none").
- Catalogue sentence `monitoring_why_expiry_kind_unknown` added and pinned. FD2's skipped test in tests_app/test_fields_r2_fd2.py runs once its branch is merged.

## Item 6
Waiting on FD2. One test already pins the `expiry_kind_unknown` entry through the badge (passes with no code change). The opportunity page's "Now ... as of ..." names were not checked against the served names.

## Item 7 (Lane TC D-5)
Not a file of mine. The "Checked at 03:22:40 IST" beside the banner is printed by PaperBookPanel.vue (no lane's file). By ADR-088 "Checked at" is the server's answer time. The finding for the owner lane: the line must either carry the book's own price time (as the banner does) or say "Answered at" so it is not read as a price time; I did not confirm in that file which source it prints.

## For the owner lane
- UX-A18 (the ISO date in the Exit dialog's sold-option warning): `backend/ofo_app/routes/paper.py` line about 1625 names the legs with `describe_contract` (ISO date, "contract_description"); use `display_contract` there, as line about 1673 already does ("NIFTY 1 Dec 25400 PE"). Nothing to change in explanations.py.
- UX-A03: Lane FE2 stores the figure at firing and renders `paper_leg_stop_fired` (leg, level, figure), `paper_leg_stop_fired_unlimited` or `paper_leg_stop_fired_unknown` (leg, level), wrapped in `stop_fired_at` (line, time) or `stop_fired_on` (line, date, time) for "seen by the check at <time> IST".
- StrategyBuilderPage.vue (FB2): pass `:trade-mode="'real'"` to TrackingPanel for a real trade (line about 1690), and `:closed="paperCompleted"` to PlanWatch (line about 1694) instead of hiding it, if the owner wants the closed sentence there.
- PaperStrategies.vue (FC2): PlanWatch row for a settled trade may pass `closed` instead of `v-if="g.openCount"`. UX-A05: add a "Plan" door on the Live card that opens the plan sheet for that strategy (AdjustPlanSheet takes `strategyId`); the Live card file is not in my list.
- Lane FE: the since time of the Monitoring paused badge resets when the worker restarts (the other half of #880).
- explanations.py: the other `strftime('%b')` uses (TargetValue, ClockHmsOrDated, DayMonth) now use the same English table (coordinator item, 28 Nov).
- PaperBookPanel.vue: see item 7.

## Decided for the owner
- Grouping key is the server's reason sentence; a group of one keeps the old line. Spec basis: ADR-272 (3), ADR-003.
- Date of the badge: appended after the server's "Since hh:mm" as ", 20 Nov 2026"; the server sentence is not recomposed. Spec basis: REQ-115 AC-4.
- A real trade shows the existing "cannot be read here yet" line until FD2's read exists. Spec basis: ADR-330 (58).

## New wording for the owner to read
- "N rules not checked: <reason>" (N is 2 or more); a group with no reason text says "no reason was given".
- The four "Not being watched: ..." sentences listed in the coordinator additions.
- "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value." (trigger reason, templates.py)
- "Stop fired: <leg> reached <level>; max loss at that point Rs <figure>" (also "...; there was no fixed maximum loss at that point" and "...; the maximum loss at that point was not worked out"), followed by "; seen by the check at <time> IST".
- "Every exit rule is not checked because whether this trade expires weekly or monthly is not known."
- "This trade is closed; nothing is watched."
- "The plan watch is paused while the feed has no live prices. It resumes with them."
- "Since 10:12, 20 Nov 2026" (date added to the server's since text when not today).
- "{line}; seen by the check at {time} IST" and "{line}; seen by the check on {date} at {time} IST".

## Not done
- F5, UX-A18, d36 run (see coordinator additions).
- Browser checks and screenshots under docs/design/next-batch-2026-11-26/screens-fc3/ (no harness for the isolated components in this run).
- Item 2 real-mode read, item 6 opportunity-row names: waiting on FD2.
- UX-A05 Plan door.

## PC steps
Market closed: open a saved paper trade on the builder; with 2 or more unchecked rules the rules line is one line with a count and an expand; open a settled trade: no "Checked at Time not available". Live: pause the feed and see the Plan watch sentence; open Monitoring paused for a worker stopped on an earlier day and see the date.

| task | model | minutes |
|---|---|---|
| all items | Sonnet (main) | 50 |

SAFE TO CLOSE after the push and the gate (head <sha>, left: item 2 real read, item 6, UX-A05, browser checks)
