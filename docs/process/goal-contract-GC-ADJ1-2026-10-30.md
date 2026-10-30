# Goal contract GC-ADJ1: compare every adjustment approach for an iron condor, proved on scenario data (2026-10-30)

Written 2026-10-30 after the owner's go ("Go ahead as per your recommendation"). Run it with `/goal` in a FRESH
session. Scope: the CORE of the adjustments feature, iron condor only, paper strategies first. Playbooks, the plan
sheet, the inbox and the history are the next contract (GC-ADJ2, outline at the end); they are NOT built here.

## Owner decisions behind this contract (all recorded; the run never re-asks them)

- ADR-214 (1)-(3), (2a), (2b): drawer on the strategy card; Strategy Builder adjust mode for Before/After (no second
  page); compare ALL applicable approaches plus "No change"; each criterion marks its leader; NO overall winner, score
  or "better" label (ADR-003, REQ-045 AC-6, REQ-046 AC-3); filters computed from the live strategy's own approaches.
- Scope is suggest-only (ADR-003, ADR-206): the run never places an order; "Prepare basket" hands to the existing
  Execute flow, which the owner drives.
- Requirements: REQ-155 (approach builder + whole-trade After, the core), REQ-156 (compare), REQ-157 (filters),
  REQ-046 (drawer layers 1-3), REQ-045 AC-4/AC-5 (approaches; generic approaches when no user rule).
- Findings to fix as classes: F-74 (booked P&L and adjustment-trade charges missing from the After), F-75 + class
  `knowledge/findings/interpolated-level-finer-than-paise-refused.json` (POP on a level finer than paise), F-76 (no
  spot over REST). F-73 is the baseline (engine 0.27 s for 7 approaches; I/O is the cost).
- **Owner rule (2026-10-30, set at the start of this run): every change stays on `feature/adjustments`. Never open a
  PR to main, never merge or push to main, even when the feature is done. Only the owner's explicit approval allows
  that.**
- Branch (owner, 2026-10-30): ALL adjustment work lives on `feature/adjustments`. This run branches from it and
  merges back into it locally. NO PR to main from this goal; main gets the whole feature once, after GC-ADJ2 is done.
- Test data (owner, 2026-10-30: "Create test data for all scenarios and use it for testing as getting live market data
  for all scenarios is not possible"): every proof below runs on the scenario library
  `tests/fixtures/adjust_scenarios/` (43 synthetic scenarios ADJ-01..ADJ-41, `_playbooks.json`, `INDEX.md`; generator
  `tests/adjust_scenarios_gen.py`; expected values derived without the engine; 132 tests in
  `tests/test_adjust_scenarios.py`). The real-chain anchor already exists (F-73); a live re-check is optional, never a
  blocker. Add a scenario (generator + expected values) when a case is missing; never hand-type numbers.
- Target screens: the published mockup https://claude.ai/artifact/RwzCxhDod7yVCk6TWrQc9e screens 1 and 2 (card +
  drawer; compare + filters). Look and words follow the mockup; numbers come only from the engine.

## §0.1 Where the run works

- Run tree: `~/.claude/tools/wt-new.ps1 -Repo D:\Abhay\Ventures\OptionsForOptions2 -Name gcadj1-run -Branch
  build/gcadj1 -Base feature/adjustments -Purpose "GC-ADJ1 run" -TtlHours 72`. Before starting: `git merge origin/main`
  into `feature/adjustments` (keeps the final merge small). Never work in the main checkout.
- Builder sub-worktrees `wt-new.ps1 -Name gcadj1-<item> -Base build/gcadj1`; `frontend\node_modules` linked as a
  junction (`~/.claude/tools/wt-link-modules.ps1`), never `npm install`; merged locally into `build/gcadj1`.
- Lock: `.run-active.lock` with the session token at the run tree root; removed on any stop. If another session's
  lock is live on a run tree that serves the live feed (e.g. GC-LIVE2), do not start a second feed: use REST quotes.

## §0.2 Preflight (never redo finished work)

- Read the Status column, "Found during the run", "Parked", and `git log --oneline build/gcadj1` for `GC-ADJ1 step N`
  commits; a DONE step with its commit is re-verified from its proof and skipped.
- Read before any code: ADR-214, ADR-003, ADR-008, ADR-206; REQ-155, REQ-156, REQ-157, REQ-046, REQ-045, REQ-078,
  REQ-112; `spec/findings.md` F-71, F-73..F-76; `knowledge/findings/INDEX.md`; `docs/process/runbook.md`;
  `.claude/kit/builder-brief.md`; `docs/research/adjustments-catalogue-2026-10-30.md` Parts 2, 9a;
  code `backend/ofo/strategy/leg_edit.py`, `backend/ofo_app/routes/leg_edit.py` (outcome path ~l.560-600),
  `backend/ofo/outcome/service.py`, `backend/ofo/outcome/target.py` (booked P&L today, l.232-237),
  `backend/ofo_app/routes/outcome.py` (l.240-264), `backend/ofo/engine/metrics.py` (l.210-220),
  `backend/ofo/engine/pop.py`, `backend/ofo_app/held_switches.py`, `backend/ofo/broker/kite_http.py` (l.37),
  `backend/ofo/adjustment/detection.py`, `frontend/src/components/strategy/TrackingPanel.vue`,
  `frontend/src/pages/StrategyBuilderPage.vue`. The core-proof script (throwaway, read-only) that measured F-73 is the
  model for step 1's proof: it called the route's own outcome function with a REST-built snapshot.

## §0.3 Progress log

Each step ends with one line here: `step N DONE <sha> <proof line>` or `PARKED (#issue)`.

- step 0 DONE (2026-10-30 19:5x) overlap: loose grep for `adjustment.approach|adjustment_approaches|approach_builder|?adjust=`
  over backend, frontend/src, tests, tests_app, scripts = 0 hits. Existing adjustment code is detection only:
  `backend/ofo/adjustment/{detection,registry}.py` (201 lines) and the "Why detected" hint in `TrackingPanel.vue:38`.
  Nothing to reuse or retire; step 1 builds new.
- Setup note: `wt-link-modules.ps1` has no `frontend` entry and `link_guard` refuses a junction into main, so the run
  tree ran `npm ci` in `frontend` (exit 0).

## Rules for the run

- Prove the core first: step 1's proof must pass before steps 2-4 start. A failing core STOPS the run (report, park).
- No PR to main (owner branch rule). At the close: `python scripts/orchestrator/prepush.py --repo <run tree> --full`
  must PASS, then `build/gcadj1` merges `--no-ff` into `feature/adjustments`. Pushing `feature/adjustments` to origin is
  only a backup, after market hours (CI runs on push). Never `gh pr merge`.
- Money is Decimal; every P&L/payoff/POP number comes from the one engine (ADR-008). Engine changes get the
  `options-math-review` checklist in the builder brief and an Opus reviewer (Tier A: money numbers users act on).
- Every build brief carries: Core, Proof, Budget, Report: evidence-table, Spec quote, Findings checked, Sensibull line
  (none for adjustments, ADR-214 source; cite screens 051/222 only where mirrored), and the builder-brief standing items.
- Wording: ADR-003 lists; "Leads on", never "best"; the wording CI check must pass.
- At most 2 fix rounds per item, then park (`parked` issue, tracker line) and move on.
- Owner is away during the run: never ask; decide spec-conformant points and record them; anything needing the owner
  goes to `owner-questions/owner-questions-2026-10-3x.md` with a recommendation.
- Browser checks in the owner's visible Chrome only (Claude-in-Chrome), one tab, closed after; never click inside a
  live order panel; no orders.

## Running the app

- As GC-TP "Running the app": check ports 8765 / 5174 first; stop only recorded PIDs; API via
  `scripts/orchestrator/dev_run.py` on ofo_dev (never ofo_test); Vite `OFO_API_TARGET=http://127.0.0.1:8765 npx vite
  --port 5174 --strictPort`. Kite token expires 06:00 IST: the owner logs in once in a PRIVATE window at
  http://127.0.0.1:8765/broker/zerodha/login. Live checks are optional (market hours; after hours the last close per
  ADR-197 / ADR-212, labelled).
- **Scenario mode (dev and test only).** Built in step 1b: with `APP_ENV` = development or test and
  `OFO_SCENARIO=<ADJ-id>`, the API serves that scenario's chain, spot, clock, data state and broker answers through the
  same parsers as Kite (fixture shapes of `tests/fixtures/kite_quotes` / `kite_margins`), so the screens show the
  scenario. Refused at start-up in any other environment (fail closed, like `held_switches.py`); one place reads the
  variable; a banner on every screen says "Scenario ADJ-xx - test data, not the market". No order path in this mode.

## Design decisions (pre-made; the run does not pause on these)

- **API.** `POST /api/strategies/{id}/adjustment-approaches` (body: optional list of approach ids, `view`); answers the
  Before, then one entry per approach: id, name, kind (roll / reduce / close part / convert / exit / none), side
  (call / put / both / none), the exact trades, the After legs, and the engine outcome of the WHOLE trade, the
  adjustment's own charges, Zerodha margin with its state, and a refusal reason per approach when it cannot be built.
  The browser computes nothing (as leg-edit). One request prices all approaches.
- **Approach set for the iron condor (first delivery):** A-36 No change, A-01 roll the untested spread toward spot,
  A-05 roll the tested spread out (same width), A-29 reduce the tested side (half the lots, rounded to whole lots),
  A-28 close the tested spread, A-11 re-centre as an iron fly (only with 3+ days left), A-31 exit. Default step
  sizes: one roll = the strikes needed to bring the moved short back to the playbook's "early" delta (0.30 weekly) or,
  if delta is not available, 200 points for NIFTY / 500 for SENSEX; recorded as admin config, not code constants.
  "Tested side" = the side whose short is nearer spot in percent.
- **Whole-trade After (F-74).** The After includes booked P&L of every leg closed before and by the adjustment
  (entry from the strategy's own records or paper fills, exit at the planned price), in max profit, max loss,
  breakevens and POP, through the existing `breakevens_with_shift` path (metrics.py) rather than a second formula.
  Charges shown in two lines: "This adjustment" (all its orders, round trip of opens excluded) and "Paid so far".
- **POP (F-75), class-level.** Quantise every derived level at the one place it is produced (`_breakevens` /
  `loss_regions_after_charges`) to paise, ROUND_HALF_UP, and state the rule in the docstring; add the property test
  named in the finding (non-round prices and charges -> a POP or a named refusal, never an exception). POP in the
  compare obeys the SAME held switch `probability_of_profit` (`backend/ofo_app/held_switches.py`; held until the
  written legal answer Q211, ADR-156 / ADR-165): ON in development and test (where this run proves it), and in any
  other environment the POP row shows "–" with the held reason, and no leader is marked on it. Never a second switch.
- **Spot (F-76).** Widen `QUOTE_INSTRUMENT` to accept the index symbols the instrument store lists (`NSE:NIFTY 50`,
  `BSE:SENSEX`) by an explicit allow-list of those names, not a looser regex; spot source order: feed, REST quote, last
  close (ADR-212), each labelled with its time.
- **Screens.** Live Strategies card: "Review adjustment" button next to the existing detection line opens a right
  drawer (REQ-046 layers 1-3; approaches with tick boxes; "Compare"). Compare = Strategy Builder in adjust mode
  (`/strategy/builder?adjust=<id>`): Before dashed + one line per approach, legend toggles; criteria table with
  leader cells and "Leads on N of M"; filter panel (chips + ranges from the current approaches); "Approach to prepare"
  + "Open in builder and prepare basket" hands the After legs to the existing builder/Execute path. Phone width: table
  scrolls in its own container.
- **No detection change in this goal** except: F-71's "fires at entry" is out of scope (it belongs to GC-ADJ2's
  playbook triggers); note it in the handover.

## Items

| Step | What | REQ / finding | Proof (scenario data) | Status |
|---|---|---|---|---|
| 0 | Overlap check: grep main for any adjustment-approach code or route already built; list in "Overlap" | — | the grep output | DONE |
| 1 | **CORE**: approach builder + whole-trade After + adjustment charges + POP fix + spot allow-list + API | REQ-155, F-74, F-75, F-76 | A test per scenario ADJ-01..ADJ-29 (iron condor ones): the API answers the 7 approaches; max profit / max loss / breakevens equal the scenario's hand values to the paisa INCLUDING booked P&L (ADJ-13); POP present (ADJ-23 is the F-75 regression); spot sources per ADJ-24a/b; refusals and warnings per ADJ-20a..e while other approaches still show; engine time for 7 approaches <= 1 s (REQ-155 AC-7) | TODO |
| 1b | Scenario mode (dev/test only) | owner test-data instruction | `OFO_SCENARIO=ADJ-02` on dev shows that chain and clock with the banner; the same variable under `APP_ENV=production` refuses start-up (test); no order route answers in this mode (test) | TODO |
| 2 | Compare screen in builder adjust mode + filters | REQ-156, REQ-157 | Component tests on ADJ-02, ADJ-13, ADJ-20c, ADJ-23; then owner's Chrome in scenario mode ADJ-02 and ADJ-13: every criterion shows a leader; "Leads on" counts add up; filters' ranges equal the API's min/max; hiding an approach updates chart, table and picker; wording check passes | TODO |
| 3 | Drawer on the Live Strategies card + "Prepare basket" hand-off | REQ-046, REQ-045 AC-4/AC-5 | Chrome in scenario mode ADJ-02 (fires) and ADJ-01 (quiet, no button): detection line -> drawer -> Compare opens step 2's screen for that strategy; "Open in builder and prepare basket" shows the After legs in the builder; no order is placed | TODO |
| 4 | Close: prepush --full PASS, merge `build/gcadj1` into `feature/adjustments` (no PR to main); handover with DONE / PENDING / BLOCKED / PARKED / NEXT | — | prepush marker + `git log feature/adjustments` showing the merge | TODO |

## Definition of Done

Steps 1-3 DONE with their proof lines recorded in §0.3, or PARKED with an issue; F-74, F-75, F-76 marked fixed in
`spec/findings.md` with the proof, and the POP class file moved to `guarded` naming its test; `build/gcadj1` merged
into `feature/adjustments` after a passing prepush --full (no PR to main); run tree removed with `wt-rm.ps1`; handover written; memory note updated.

## Found during the run

| # | What | Where | Decision |
|---|---|---|---|
| 1 | Catalogue features in no contract (F-05 on the After, F-09..F-16, F-18 effectiveness, F-19, F-20, triggers T-03..T-19, approaches beyond the 7, every strategy type but the iron condor) | catalogue Part 5a / 9a | Owner 2026-10-30 19:5x: run GC-ADJ1 as written; the handover carries a GC-ADJ3+ outline mapping each uncovered feature, for owner approval |
| 2 | Contract said POP levels round ROUND_HALF_UP; the spec says half-even | `spec/business-rules/scenario-calculations.md` section 3 ("rounded half-even to 0.01 points") | Spec wins: half-even at `metrics._to_decimal` (no shown level changes; contract wording was wrong) |
| 3 | Approach rules the contract left open | `backend/ofo/adjustment/approaches.py` | Builder calls (technical, spec-silent): tested-side tie -> call side (same as `leg_edit.width`); monthly target delta 0.25 (playbook Early T-03); A-05 rolls to the first strike past the short with delta <= target, A-01 to the strike nearest spot with delta <= target, wing moves the same distance; A-01 refused if the short would cross the other short; A-29 = half the lots rounded down, refused under 2 lots; A-11 ATM = listed strike nearest spot (tie: higher), refused under 3 days; closing a leg needs only a price; trades BUY first then SELL; planned price = ADR-068 (1) (LTP, else mid) |
| 4 | ADJ-20d's unlisted strike sat where the delta rule never lands | scenario generator | Moved to 23,700 CE (where A-05 lands) through the generator, refusal text regenerated |
| 5 | Whole-trade After needs exit charges of still-open legs (the outcome screen charges a round trip) | `backend/ofo/engine/whole_trade.py` | Third charge input `open_exit_charges`, each line subtracted once (AC-3) |
| 6 | Contract asked for a node_modules junction; the project `link_guard` hook refuses junctions into main | run setup | `npm ci` per tree instead |
| 7 | POP round-2 checker: NaN/Infinity vol, years or forward makes `probability_of_profit` raise (AC-4 "never an exception") | `backend/ofo/engine/pop.py:48` | Severity MINOR: unreachable from the engine's own producers (`black_scholes.py` and `marketdata/forward.py` refuse non-finite values before returning). POP piece merged after round 2 with this finding listed; the structural guard (non-finite -> named reason in `probability_of_profit`) is in the wave-2 route brief |
| 8 | Spot checker: no code builds a quote URL with an index name (`kite_reads.py:313` pre-checks with the plain pattern), so the new allow-list is unreachable; non-finite or future-dated REST/last close accepted | `backend/ofo_app/kite_reads.py`, `spot_source.py` | Domain part PASS and merged; the index-quote fetcher (emits `%20` itself) and both minors are in the wave-2 route brief. A live read of `NSE:NIFTY%2050` from Kite is owed (optional per this contract; in the handover) |
| 9 | Approach checker minors: AC-1 wording loose on A-01 vs A-05; refused A-01 on a non-condor reports side "call"; A-29 rounds down | `approaches.py` | Shipped with findings listed; non-condor side is out of this run's scope (deferred); AC-1 wording note for the spec at close |
| 10 | Scenario checker MAJOR: `tracking/exit` writes paper exit orders but was classed as a non-order route | `backend/ofo_app/routes/tracking.py:425-430` | Fix round 2 of 2: move to the refused list + a structural test that any route reaching `paper_store.place` is refused |
| 11 | DoD says "run tree removed with wt-rm.ps1", but wt-rm refuses unless the branch (or -MergedSha) is on origin/main, and the owner rule keeps this work off main | `~/.claude/tools/wt-rm.ps1` | Conflict between two owner rules; the branch rule wins. The run tree and the merged sub-trees (gcadj1-pop/-spot/-appr/-scen, all ancestors of build/gcadj1 4ea7d050, no node_modules, clean) stay until feature/adjustments lands on main; listed in the handover with this reason |
| 12 | Scenario mode served synthetic tokens (from 900000) while the seed script links real catalogue contracts: seeded strategies would get no scenario price | `scenario_mode.py:104`, `scripts/seed_scenario.py:78` | Technical call: scenario mode reuses the real catalogue token for a tradingsymbol that exists (read-only lookup), synthetic only when absent; a Sonnet builder does it |
| 13 | REQ-156 AC-2 criteria the spec leaves open: "would you open this fresh", strike liquidity, margin change, adjustments vs plan maximum | catalogue P-02, P-12, F-12; REQ-156 | Technical calls: fresh = the After's open legs as a fresh trade at current prices (fresh round-trip charges, no booked P&L), leader = smallest fresh max loss; liquidity = widest (ask-bid)/mid % among the approach's NEW legs, lowest leads, nothing hidden (no threshold in the catalogue); margin change = After minus Before basket margin, both Zerodha-stated; adjustments = used count with "no plan maximum set" until playbooks (GC-ADJ2). Values, leaders and curves computed server-side (ADR-008); filter min/max in the browser (comparison only) |
| 14 | Route builder ran out of budget twice (brief too large: route + 3 carried fixes in one part) | W-196 wave 2 | Split into parts 3 and 4; root cause: a part sized L with carried items added on top. Step-2 work split into 2a (server) and 2b (screen) up front |

## Parked

| # | Issue | What is left |
|---|---|---|

## Next contract (outline): GC-ADJ2, playbooks

REQ-158 (store, one active per type, save as new / in place), REQ-159 (stages, triggers per stage, day-and-date rules,
situations, guards; fixes F-71 by making the distance trigger relative to the playbook), REQ-160 (step editor, plain
summary, test), REQ-161 (plan sheet at Start tracking), REQ-162 (inbox), REQ-163 (history). Needs a DB migration
(Tier A review). Owner input needed BEFORE GC-ADJ2 ships defaults: approval of the iron condor playbook numbers
(catalogue PB-04 / mockup screen 4), which are DRAFT today. GC-ADJ2 also branches from `feature/adjustments`; when it is
done, ONE PR takes the whole feature to main. Open points from the scenario library (`_playbooks.json` "conventions"):
the T-14 gamma-loss formula, a "% of premium paid" trigger for long options (PB-08's +100%), and the meaning of
"tighten every trigger by X%" - each decided in GC-ADJ2 and the scenario expectations regenerated.
