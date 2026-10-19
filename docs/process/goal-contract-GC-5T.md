# Goal contract GC-5T (written by GC-5S close-out, 2026-10-19): live screens, the pool-budget fix and what GC-5S left

Chain: `goal-chain.md` (rules, scorecard). Source: GC-5S results (`gc-5s-run-log.md`, handover
`session-handover-2026-10-19-gc5s.md`). Runs after GC-3F unless the owner runs it in parallel again; if parallel, the
isolation rules of GC-5S apply PLUS: nothing of GC-5T opens a connection on the `ofo_app` role while another run's API is
up (5-connection role limit, F-45) - DB tests in CI only. Owner needed: NO (screen content/layout by the design role,
ADR-114; ask only business rules, always ask when two business requirements conflict). Cap: lock + 7 h; live checks
09:15-15:30 IST only.

Core: every API process sizes its DB pool from the role's limit, so a second API plus a Live Strategies page with 13+
cards never gets `TooManyConnectionsError`.
Proof: on ofo_dev with GC-5T's API and one more API process up, the Live Strategies page with all saved drafts open for 2
minutes: 0 `TooManyConnectionsError` lines in both API logs and `pg_stat_activity` for `ofo_app` stays <= 5 (read-only
query), recorded as evidence rows. Fails -> STOP, record the output, write the fix as the next contract.

## Items (in order)
1. **POOL-BUDGET (core, Tier A; independent review 2026-10-19).** Pool size + overflow from settings with a default under
   the role's limit (#395 added the settings; CI uses 1 + 0), a startup check that refuses a pool larger than
   `rolconnlimit`, remove the nested connection in the broker token read (`broker_token_store.py:70,90`), single-flight
   on the charge-rates cache (`routes/outcome.py:46-65`). Proof above.
2. **IDX-FLAT check (Tier A, live).** At 15:25-15:26 IST on 2026-10-19 NIFTY 22873.55 and SENSEX 73800.18 stayed flat
   for 6+ pushes with advancing times (they moved every push at 14:29-14:33). In a market session compare the index
   socket's values with Kite's own quote (read-only `probe.py`) for 2 minutes; if they differ, it is the
   `live-subscription-lost-on-release-reacquire` class -> fix contract; if they match, close the row with the evidence.
3. **F-47 previous close (Tier A data path).** Kite's previous close into the adapter and the quote model; the chain
   fills Change from the server (REQ-029 AC-2). Real-data proof: a live chain push with non-null Change equal to LTP -
   close for 3 contracts, cross-checked against Kite's quote.
4. **W-118-sel: Option Chain selection and import (REQ-030), then the live preview (REQ-031).** Split: (a) selection,
   Buy/Sell chips (action only, never an order: REQ-029 AC-6, ADR-002), lot stepper, Selected Legs bar, import to the
   Builder; (b) preview from the one engine (ADR-008). Read REQ-030/031 in full first; design basis: the design note's
   Option Chain section (REQ-030 AC-2's visible Buy and Sell on every row; the table scrolls in its card at 390 px).
5. **#439** chain socket self-starvation by invalid messages; IV on the chain at the Advanced level from the engine.
6. **#435** TemplateText per (template, field); the shell UI lines to the owner with the next wording batch; Learn content
   (REQ-011 "Open").
7. **DRAFT-LABEL** (MINOR): a draft without planned entries shows "Live data not connected" while data is live.
8. After GC-3F adds execution state: **#433** Home state 3, **#434** Strategy Live Position tab (reuse W-113's card and
   its wasLive rule).
Not here: Positions P&L (held #398/#410, GC-3F), My Strategies (#393), Settings (#397), Orders, Execute.

## Rules carried from GC-5S (each from a measured miss)
- A screen brief names the ONE router map (`REAL_PAGES` in `frontend/src/router/routes.js`, keyed by route name): three
  GC-5S PRs each invented a map and every merge conflicted.
- Every built page carries `data-testid="page-title"` (W-118 failed navigation/responsive e2e without it).
- A route that newly imports a domain module checks its imports against `requirements-app.txt` (W-117's API could not
  start in CI: jsonschema).
- After merging main into a branch, run `python scripts/ruff_ratchet.py` before pushing (an E501 from a merge resolution
  failed #437's api job).
- A live view's state machine follows `useIndexAnswer` (clear on drop and on any change of choice, drop counter, values
  only from a LIVE answer after the latest drop) - finding `last-live-answer-kept-after-drop` (4 samples).
- Every outbound socket message passes one rate gate - finding `rate-gate-on-success-path-only`.
