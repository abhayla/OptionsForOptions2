# Goal contract GC-ICTRACK: every iron condor trigger tracks real and paper strategies, on live and test data, on one code path (2026-11-08)

**Status:** APPROVED by the owner 2026-11-08 ~18:00 IST (plan approved after three independent reviews: tester,
senior lead, code-quality lead). **Executor:** `/goal` in a fresh session of this project.
**Branch:** a new worktree from `main` (task 0b), carrying commits 9ab11ac2 (ADR-275), d571fce9 (one-path plan) and this contract
from local branch `docs/adr-275-one-code-path`.

**Mission:** all 27 triggers of the IC system playbook answer correctly, on ONE code path, for real Zerodha AND paper
strategies, on live prices AND test data. Tracking only (alerts and suggestions); no order is sent.

**Core:** one reader returns a strategy's open legs from paper orders OR real Zerodha fills.
**Proof (task 2, before any other code):** strategy 82 (the owner's live IC) netted read-only from its plans, fills and
adopted holdings, legs printed and compared with Kite's positions. Fails after task 3 -> HALT and report; nothing
else in this contract is useful without it.

Read first: this contract; the approved plan `C:\Users\itsab\.claude\plans\dapper-swimming-planet.md` (same content);
`docs/process/ic-e2e-code-audit-2026-11-07.md`; `docs/process/ic-one-path-plan-2026-11-08.md`; ADR-275.

## §0 Run rules
1. **Status page first (task 0).** Load the `artifact-capabilities` skill, publish one private page with the `db`
   capability: one row per task (id, title, estimate min, start, finish, actual min, state
   waiting/running/done/failed/parked, evidence). The page reads the database on open and is never republished.
   Write ONLY at a task boundary: one `ArtifactData` batch that closes the finished task (state, finish, actual
   minutes, evidence line) and opens the next (running, start). Times from `date` run in the same step. Save the link
   in `views/status-page.json` and tell the owner once. A task is done only with its evidence line.
2. **Completeness.** These tasks are the whole work. New work found during the run becomes a new row (with its
   estimate) before it is done; nothing is done off the list. A defect outside a task's done line becomes a
   `deferred` issue (`gh_issue.py app ... --stage`), not new scope.
3. **Minimum code, reuse first.** Follow §2 exactly. Before writing any function, grep for an existing one. Pure
   logic in `backend/ofo` (no DB, web, Kite); plumbing in `backend/ofo_app` calls it; every money and Greek number
   from the one engine, exact Decimal (ADR-008). No second path for anything already in the code.
4. **Tests only for what changed:** each task runs its own tests plus direct importers. Domain:
   `python -m pytest tests/<file>.py -k <name>`. DB: one file at a time per `docs/process/runbook.md`
   (`scripts/orchestrator/db_run.py`). No e2e, browser or mutation runs (Tier A review only in task 32). Long output
   to a log under `D:\Abhay\scratch\gc-ictrack\`; read only the tail. Gates and servers run under Desktop Commander
   `start_process` (the idle reaper killed foreground gates before).
5. **One branch, one gate, one PR.** No push before task 34 passes (`python tools/ci_local.py`, prepush marker for
   HEAD). Merge with `merge.py <pr> --reviewed-sha <full sha>`, chained with `&&`.
6. **Real money safety.** No order is placed, modified or cancelled by this run. Kite calls in tasks 2, 11, 27 and 37
   are reads only. Never click inside a Kite order panel. Stop only PIDs this run started; never select a process
   by its command line.
7. **Park rule.** At most 2 fix rounds per red; a class red twice goes to an independent reviewer (fresh context,
   different model), then a third round on its findings; still red -> park it (`parked` issue + status row
   `parked`) and continue the other tasks.
8. **Owner tasks (21b, 38) and the market task (37).** Owner present: ask with AskUserQuestion, one question,
   recommendation first, `Business call:` + `Spec basis:` lines. Owner away: write the question to
   `docs/process/owner-questions-<date>.md`, mark the row `waiting on owner`, continue other tasks. Task 37 runs in
   the next market session (09:15-15:30 IST, weekday); until then its row waits.
9. **Spec first.** Each product answer becomes a decision row the same turn (spec-first R4). Briefs carry
   `Spec basis:`, `Budget:` and the B4 standing items.

## §1 Owner answers to write as decision rows (task 1)
| # | Answer (owner, 2026-11-08) |
|---|---|
| A1 | Real Zerodha strategies in scope: all 27 triggers track real AND paper, live AND test data |
| A2 | T-11b from the live India VIX quote (token 264969); T-20b ADX(14) on Kite daily NIFTY/SENSEX candles (>= 25 trending, <= 20 range); T-11c = India VIX percentile over 250 days, NIFTY only (SENSEX answers "not available" with its reason); own daily ATM IV stored from day one |
| A3 | T-14 computed on live prices and switched on for live (supersedes ADR-253) |
| A4 | Two checkers on the same code: live always on (real + paper strategies, live prices); a test-data checker started on demand sees only test strategies; no automatic switch; missing live prices -> "not checked: prices not live" |
| A5 | Tracking only; sending real adjustments (audit C1, C3/C14, C4, C5, C6) is the next plan (handover line, not an ADR) |
Recorded with them (strategy delegation): the 12 new triggers keep the playbook's OFF default and work when switched
on; T-11c and T-20b lose their greyed flag.

## §2 Reuse rules (code-quality review, verified at file:line on main da7b6b87)
- Netting: live fills -> `PaperOrder` -> `ofo.engine.orderbook.net_positions` (`orderbook.py:174`); sources
  `order_book_store.fills_for` (`:171`), `adopted_for` (`:166`), `execution_plan_store.plans_for`. No new netter.
- Entry facts: existing writer `entry_facts_store.record_first` (`:30`, called at `paper_store.py:85`); entry spot
  already stored; add only `entry_atm_iv` (field on `EntryFacts`, `ofo/adjustment/approaches.py:168`).
- Available funds: `kite_period_reads.available_margin` (`:65`). Worker token: `history_finalize.stored_credentials`
  (`:49`) if task 11 shows none.
- SD move: `ExpectedMove(...).exact_points` (`ofo/scenario/levels.py:77`). Theta / vega totals:
  `engine.target.greeks_total` (`:69`) with the `adjust_ratios.py:66-79` signing. T-04 / T-06b: `adjust_ratios`
  helpers (`:43-62`). T-14 gates to remove: `background.py:449-454`, `adjustment_check.py:372-383`.
- Level crosses: existing watch rules (`playbook_eval.py:1058`); T-20 answers from them; no second level store.
- VIX up %: the `_t13` shape (`playbook_eval.py:541`). VIX quote: add INDIA VIX to `KiteReads.fetch_index_quote`
  (`kite_reads.py:309`); its limiter is the cache; a 0 or null value = missing. One live VIX source (quote, not the
  feed).
- Candles: widen `KiteHistory.day_close` (`kite_history.py:74`) to a date range; one parser; 250 days in memory, keyed
  on the IST trading day from `ofo/timeutil.py`; no table.
- New code only: T-05 side-value helper; VIX percentile and ADX(14), pure Decimal, standard library.
- Test-data twins: scenarios supply VIX and history through the SAME readers (`scenario_mode` packets / provider).
- Known debt, filed (task 7), not fixed here: `execute_plan.held_units` (`:187`) stays a second netting path for the
  sending side.

## §3 Tasks (each <= 15 min Claude Code time; done line = what the status row's evidence must show)
| # | Task | Min | Done line |
|---|---|---|---|
| 0 | Status page with all rows | 15 | page link + 45 rows listed by an ArtifactData list |
| 0b | Worktree from main (`wt-new.ps1`, purpose GC-ICTRACK, TTL 48h); bring in the 3 commits of `docs/adr-275-one-code-path` | 5 | `git log` shows all 3 on the new branch |
| 1 | Decision rows A1-A4 + A5 handover line; regenerate digest | 15 | ADR files exist; digest lists them |
| 2 | CORE PROOF read-only on strategy 82 | 15 | printed legs = Kite positions (contract, side, qty), or the mismatch |
| 3 | Contingency: id-to-contract mapping fix | 15 | task 2 re-run matches, or HALT |
| 4 | Live fills -> `PaperOrder` -> `net_positions` + test | 15 | test passes; entry = fill-weighted average |
| 5 | `read_tracked` real branch; paid / adjustments used unknown for real + test | 15 | DB test passes for a paper and a real strategy |
| 6 | `owner_lister` lists both sources + test | 15 | worker test lists a real strategy |
| 7 | Deferred issue: `held_units` second netting path | 5 | issue number |
| 8 | Migration `entry_atm_iv` + `EntryFacts` field | 15 | `alembic heads` one head; upgrade runs |
| 9 | Live fill read-back calls `record_first` + test | 15 | test writes entry facts for a real fill |
| 10 | Entry IV read in every mode (drop the test-only branch at `background.py:1199-1202`) + test | 15 | T-11 evaluates on a live-mode state |
| 11 | Probe: worker margin reader has a live token? | 15 | logged margin block for 82, or None |
| 12 | Contingency: `stored_credentials` in the worker + test | 15 | probe re-run returns margin |
| 13 | Remove both T-14 test-only gates + one test | 15 | T-14 evaluates on a live-mode state |
| 14 | New state fields on live (credit, leg entries, available margin, VIX, VIX prev close, VIX percentile, ADX) | 15 | state build test fills each field |
| 15 | T-04 + T-06b from existing helpers + tests | 10 | fire + clear tests pass |
| 16 | T-05 side-value helper + test | 15 | fire + clear tests pass |
| 17 | T-08 + T-12 + tests | 15 | fire + clear tests pass |
| 18 | T-14t + T-14v + tests | 15 | fire + clear tests pass |
| 19 | T-15 + T-20 (from watch rules) + tests | 15 | fire + clear tests pass; no new level store |
| 20 | T-11b, T-11c, T-20b evaluators + tests | 15 | fire + clear tests pass |
| 21 | Playbook file: un-grey, T-20b thresholds, regenerate via the build script | 15 | regenerated file diff only in those keys |
| 21a | New user-facing texts + wording checks (`tests/strategy/test_templates.py`, name guard, ruff ratchet) | 15 | checks pass; text list saved for 21b |
| 21b | Owner reads the new texts (one batch) | 10 | owner answer recorded |
| 22 | INDIA VIX in `fetch_index_quote` + test | 10 | test on a recorded quote body |
| 23 | `day_close` widened to a date range + test | 15 | test on a recorded candle body; `day_close` callers unchanged |
| 24 | 250-day in-memory cache keyed on the IST trading day + test | 10 | one fetch per day in the test |
| 25 | Pure VIX percentile + ADX(14), hand-worked tests | 15 | tests pass on hand-worked numbers |
| 26 | Test-data twins through the same readers + test | 15 | a scenario fires T-11b and T-20b |
| 27 | Probe: one live VIX quote + one 250-day fetch | 10 | logged values and row counts |
| 28 | Own daily ATM IV row (migration + writer) | 15 | test writes one row per underlying per day |
| 29 | One parametrised NOT-CHECKED test over every evaluator | 15 | every evaluator answers not checked on an empty state |
| 30 | Run the adjustment domain tests + changed app tests | 15 | pass counts in the log tail |
| 31 | Live + test-data checkers side by side on dev; start commands written | 15 | both running, test checker lists only test strategies |
| 32 | Tier A review of the 2 migrations (reviewer agent) | 10 | verdict PASS or fixes done |
| 33 | `tools/graph.py build --json`: 0 new logic->plumbing imports, no paper-only reader | 10 | edge count 0 |
| 34 | `python tools/ci_local.py` once | 15 | TOTAL PASS + marker for HEAD |
| 35 | Contingency: gate reds | 30 | re-run passes |
| 36 | Commit, handover, audit decision lines C2/C7/C8, push, one PR (Spec-deviation block) | 15 | PR number |
| 36a | Merge once CI is green; remove the worktree (`wt-rm.ps1`) | 10 | merge sha on main; counts unchanged |
| 37 | Market hours: record VIX, candles, entry IV, margin, T-14 and the new values on strategy 82; no alert raised by the record | 15 | values in the status row |
| 38 | Owner reads the values; A3 switch-ons take effect | 10 | owner answer recorded |
| 39 | Verifier pass over every task's done line | 15 | one evidence block per task; all PASS |
Total 45 tasks, 625 min (~10.4 h; ~13.5 h with the measured 30% overrun); 60 min contingency.

## §4 Done
Every row is `done` with its evidence (or `parked` with an issue, which keeps the contract PARTIAL), the PR is
merged to main, task 37 values are recorded, and task 39 passes. Not in this contract: production deploy; sending
real adjustments; moving `held_units` callers; a true per-expiry IV percentile; audit gaps C9-C13; beta; watching
another index; screen changes. For real strategies, T-18 and inputs needing paid charges answer "not checked" until
the sending plan.

## §5 Final report
DONE / PENDING / BLOCKED / PARKED / NEXT, the status page link, the PR and merge sha, and an evidence table
`| Claim | Evidence (command this turn + result line) |`.
