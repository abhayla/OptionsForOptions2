# Coordinator handover, 26 Nov 2026 (21:00 IST)

For the session that coordinates the cloud lanes and the owner's PC test. Read with `CLAUDE.md`,
`docs/process/standing-direction.md` (depth freeze lifted 26 Nov), `docs/process/runbook.md` ("Before a push": the fast
pre-check) and `spec/decisions/ADR-330.md` (owner decisions, points (1) to (44)). Times are IST. The append-only
progress log of the coordinating session is `docs/process/.run/GC-ICLIVE-PROGRESS.md` (git-ignored, that container
only). Two private artifact pages exist (issue tracker of 23 Nov; the status page "OFO2 Work Board"): their links are
never written into this repo; the owner has them.

## Role and standing rules from the owner

- The coordinator only asks, splits, routes, verifies and reports; all building, testing and reading of code goes to
  helpers or lanes (lanes on Opus, document lanes and helpers on Sonnet; never the coordinator's own model for code).
- PR #722 (`fix/ic-live-test-1123`, draft): never merge it, never mark it ready. No PR for the lane branches.
- Ask only business and functional questions, one at a time, alone in the message, with the question tool in the day
  (it is closed 22:00 to 08:00 IST: ask in chat then). Technical and architectural choices are the coordinator's.
- Before any question, look the subject up in `docs/process/owner-decisions-by-subject-2026-11-26.md`; search the spec
  by the SUBJECT's words; never ask a subject twice; group questions on one subject; say which earlier answer a new
  sub-case sits beside. Finding: `knowledge/findings/owner-question-asked-without-the-requirement-that-answered-it.json`.
- Every owner answer gets its decision row the same turn (ADR-330 so far). Plain English, IST, lead with the bad news,
  no repeated messages. One-module rule for every capability. Paper only; never call a broker order endpoint.
- Do not hold work for his answers; do not leave an item without an owner lane; close a lane when it is done.
- Lanes do not file GitHub issues: they list them under "To file as deferred issues" in their RESULTS; the coordinator
  files them in one morning batch together with their stage rows in `docs/process/coverage-stages.yaml`.
- Screen tests happen only on the owner's PC in market hours; the highest cloud status is "Fixed, not tested".

## How the sessions work (learned the hard way)

- Lane sessions are children of the coordinating session `session_01QaT8YHmr7R73Wovt3RR8zP` and report to "@parent".
  A NEW coordinator session does not receive those messages: either keep the same session (clear its context, do not
  start a new one), or message each lane its new report address.
- The coordinator cannot read lane transcripts or archive lanes (they are bound to the owner's trusted devices): ask a
  lane for one line per push and for "SAFE TO CLOSE"; the owner archives it in the app.
- A lane's safety check refuses edits to oversight files (review notes in `tests_app/reply_inventory.py`,
  `ROUTE_ORDER_EDGES`, allow-lists, the gate, the standing direction) unless the OWNER types the approval into that
  lane's session: bring him one paste block per lane, early, never after a failed gate.
- Cloud gates run with the container's proxy variables unset (`env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy
  -u http_proxy -u ALL_PROXY -u all_proxy`, plus the database URLs unset for prepush). Run `git add`, `git commit`,
  `git push` as separate calls. A worker restart can reset a session's permission mode to "ask": the owner sets Auto.
- The gate takes about 33 min per push on the fix branch because it compares against `main` (418 code files differ).

## Branches on origin (26 Nov 21:00)

| Branch | Head | What |
|---|---|---|
| `fix/ic-live-test-1123` | e40a5ad on origin; local 9+ commits ahead (ADR-330 (34) line, (36) additions, (37)-(44), runbook correction, this file): being pushed tonight | Decision records; PR #722 |
| `integration/nb-1126` | 3d7aaf7 | THE test branch for 27 Nov: screens line + alerts and plans (migrations 0054, 0055, 0056) + screen-suite fixes + Real P&L |
| `fix/screen-findings-1126` | 71ed990 | Lane R: fixes for the 26 Nov screen-test findings |
| `fix/suite-findings-1126` | 63091d7 | Lane U: defects the browser-test suite found |
| `fix/deferred-1126` | not pushed yet | Lane D: deferred issues #724 to #755 |
| `chore/gate-speed-1126` | b323efd | Lane G: faster gate (1784 s to 713 s measured); equivalence proof running |
| `docs/test-plan-2026-11-27` | not pushed yet | Lane X: `docs/process/test-plan-2026-11-27.md` |
| `feat/nb-plan-alerts-1126` a59f7a9, `feat/nb-real-pnl-1126` d344d82, `test/screen-suite-1126` 2fd3f02, `feat/nb-screens-w2-1126` a9bd41a, `refactor/modular-doors` db57d05 | finished | all merged into `integration/nb-1126` |

## Lanes running (session ids)

- Lane J `session_01QaT8YHR1UstRLMqDUCdR9X` (`integration/nb-1126`): final head by 07:30 on 27 Nov (last merge 07:00),
  then NO push until the coordinator says (15:30 at the earliest). Queue: Step 2 wiring (alerts through the one module
  from the live watcher; Exit on an alert through the one exit door; Plan watch box and max-loss line on screen); merge
  R / U / D heads; S-11 (Customise triggers drops the unsaved plan); ADR-330 (31) with its migration; #753 with its
  migration (leave out if not proven by 07:00). Section (a) of `RESULTS-lane-j.md` must carry the old-code-safe proof
  for every migration.
- Lane R `session_01QaT8YKaCw8SZQBM1sAnXdr`: after-close banner wording (ADR-330 (36)), N-30, D-15, D-50 = (38),
  D-69 = (39); D-27 read step for the PC; then tomorrow's FAIL rows after 15:30.
- Lane U `session_01QaT8YGNpjXw3ExP4oe1Z8B`: remaining screen-suite findings; Lane T's answered questions; D-48 = (42);
  D-51 = (43) (one route for a strategy's actual open legs, nothing paper-only). The owner's paste for one
  broker-name allow-list line may still be owed in its session.
- Lane D `session_01QaT8YHPxDxj8SmMSyU5rGA`: 18+ "fix now" issues, #732 = (44), #733, #741 (one row, ADR-328 (3)).
- Lane G `session_01QaT8YFy2FfpnjREQPoPudN`: equivalence proof on 12 seeded commits; lanes take the new gate only
  after it is proven and reviewed; then replace the runbook's interim paragraph.
- Lane X `session_01QaT8YH5ELuepDxTsGWnuRM` (Sonnet): test plan, first version by 01:00, final by 07:30.
- PC session `session_01QaT8YGvTk8cS2G7qtuoCeb` (owner's computer; the coordinator may message it): rehearsal tonight
  (backup, restore to a scratch database, migrations on the copy, timings; PR #722 comment "Rehearsal for the 27 Nov
  test").
- Closed: Lanes A, B, E, F, P, Q, Q2, S, T.

## Plan for 27 Nov (the owner's instruction)

The whole market day is for testing on the PC: critical checks first, heavy low-risk ones last; nothing is fixed,
re-merged or restarted during market hours (mark pass or fail); failures go to lanes after 15:30. He logs in to Kite by
about 08:45. He approved the PC applying every migration on the joined branch after a verified backup, provided each
has its old-code-safe proof written; one without proof is not applied and he is told.

| Time | What |
|---|---|
| 06:45 | Lane X re-reads the sources and the rehearsal comment |
| 07:00 / 07:30 | Lane J's last merge / final head; Lane X's final plan |
| 07:35 | Coordinator (scheduled wake `trig_01U7o9qLEuw5KgHoZbiJz8Sy`): verify the head and the proofs, list the database changes for the owner, send the PC ONE message (set-up, then the plan tier by tier) |
| 07:35 to 09:00 | PC set-up: fresh backup, migrations, Strategy Chart switch (ADR-203), restart, live prices |
| 09:15 to 15:30 | Testing only; a PR #722 comment after each tier; the coordinator updates the status page |
| After 15:30 | After-close checks; FAIL rows routed to lanes; fixes overnight |

Morning batch on the fix branch (one helper, one gate, one push): the 11 stale texts of
`docs/process/owner-decisions-by-subject-2026-11-26.md` section D; issues from the lanes' "To file" lists with their
stage rows; close the issues the lanes list as ready; `main` itself is red at preflight (2 mypy call-arg mismatches,
`tests_app/test_stored_chain_real.py:144`).

## Open with the owner

- Read-through owed (not decisions): about 30 new on-screen sentences marked "pending owner read" (Real P&L reasons,
  count lines, Option Chain messages, alert wording, `strategy_name_empty`, `strategy_not_found`).
- D-35 notification channels: a short design and one question (which channel first). D-62 waits for his playbook
  videos; so does the standard playbook content.
- Four readings applied without asking (he was told; reverse if he objects): a settled trade counts in the Paper total
  at its booked result, a settling one is left out and counted; Home never adds Real and Paper into one total; the
  "% of max loss" base stays before charges; the 5-minute quiet period delays when an at-entry rule's alert is raised,
  and once raised it stays.
- The `parallel-sessions` skill draft (scratchpad of the coordinating session) is not committed; location to confirm.
- A faster gate beyond 2.5 times needs "test only what changed since the last pass": his decision, after the proof.

## Status page

Files in the coordinating container's scratchpad folder `status-board/` (`index.html`, `overview.json` written by
hand, `status-data.json` compiled by `build.py` from the lanes' RESULTS files). Update `overview.json` at each push or
decision and republish; recompile the items morning and evening and after each PC comment.
