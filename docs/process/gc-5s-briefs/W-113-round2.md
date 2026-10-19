# W-113 round 2 brief (GC-5S item 1): start cards one at a time; group by status

Common brief: docs/process/builder-brief.md
Core: the Live Strategies page with 13 saved strategies must not burst the database: at most ONE card is loading (its `GET /strategies/{id}` + first socket answer) at any moment.
Proof: a Vitest with 13 fake strategies shows the second card's `GET` is not sent until the first card got its first answer (or failed, or 8 s passed), and the page ends with 13 cards live.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (frontend only).
Copy from: none - fix round on this repo's own W-113 files.
Design basis: docs/design/screens-research-2026-10-19.md sections `Live Strategies` and `Orchestrator decisions on this note`.

## Finding (from the orchestrator's live run, 10:33-10:40 IST, ofo_dev)
Registry `db-role-limit-below-pool-size` (F-45): the page loaded 13 strategies at once (13 `GET /strategies/{id}` plus 13
sockets). The database role allows 5 connections in total, so the API logged `TooManyConnectionsError: too many
connections for role ofo_app` 11 times and `GET /strategies/11` failed with an unhandled error.

## Changes
1. A small start queue in `LiveStrategiesPage.vue` (or a tiny module next to it): cards start in the shown order (newest
   first), one at a time. A card starts (its `GET` and its socket) only when the previous card reported its first answer
   (any server state), an error, or 8 s passed. Cards waiting show `Waiting to start...` (data-testid
   `live-queued`). Unmount stops the queue and every socket.
2. Two groups, each with a heading: `Executed` (strategies whose status is not `draft`) and `Saved drafts (live
   prices)` (status `draft`). An empty group is not shown. Order inside a group: newest first. Keep the 20 cap over the
   whole list.
3. Keep every round-1 behaviour and test. Grep `frontend/tests/` and `frontend/e2e/` for every testid you rename (rename
   none if you can).

## Tests
- `frontend/tests/live-strategies.test.js`: (a) 13 strategies -> exactly one `GET /strategies/{id}` in flight before the
  first card answers; after it answers, the second starts; (b) a card whose GET fails releases the queue; (c) a card with
  no answer releases the queue after 8 s (fake timers); (d) unmount mid-queue opens no further sockets; (e) groups: two
  drafts + one `executed` status -> two headings with the right cards.
- Mutation: remove the queue (start all at once) -> test (a) red; remove the 8 s release -> (c) red. Name them.
- Run: `npm run lint`, `npx vitest run tests/live-strategies.test.js tests/strategy-live.test.js`, `npm run build`.

## Isolation (hard rules)
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s` on branch `build/W-113-live-strategies` (HEAD ad727bb).
Never run git or npm in `D:\Abhay\Ventures\OptionsForOptions2`; start NO server and run NO database test (the database
role is shared with a live order run); never touch backend/ or any execute/order file. Commit, push; no PR.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.
