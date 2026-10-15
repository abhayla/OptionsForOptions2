# Builder brief: W-083 existing positions on connect - groups, adoption, audit (Tier A)

Core: seven documented-shape Kite position rows (a NIFTY 19-Oct iron condor of 4 legs, a NIFTY 26-Oct short call, a
SENSEX short put, one leg already in a strategy) give exactly three suggested groups - NIFTY 19-Oct (4 legs, resembling
an Iron Condor), NIFTY 26-Oct (1), SENSEX (1); the in-strategy leg is excluded; adopting the condor creates a strategy
whose legs carry Zerodha's average prices and products; each step writes an audit entry.
Proof: step 1 is `tests/reconciliation/test_position_grouping.py` on those rows (use real catalogue symbols from the
recorded captures, e.g. NIFTY26O1923150CE, NIFTY26O1923350CE, NIFTY26O1922750PE, NIFTY26O1922550PE). Write it FIRST, red.

Tier: A (decides which positions become a monitored strategy and at what entry). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD: at call 58 stop, commit, push, report done / not done / next command.
Report: evidence-table, under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no position-grouping row; reuse this repo's own parser and matcher.

Read first: `docs/process/builder-brief.md`, `work/W-083.md`, `spec/requirements/REQ-061.md`, `spec/decisions/ADR-084.md`,
ADR-018, ADR-006, ADR-002, `backend/ofo/execution/partial.py` (`position_line_from_kite_row` ~164, `BrokerPositionLine`
~137), `backend/ofo/strategy/matching.py` (`match` ~139), the audit log (`backend/ofo/audit/` or wherever W-015's
append-only log lives), the strategy model (`backend/ofo/strategy/`), `CLAUDE.md`.

## Spec basis
- REQ-061 AC-1: "On connection the platform fetches open positions and identifies possible multi-leg structures."
- REQ-061 AC-2: "For each, the user can add it to an existing strategy, create a new strategy, or leave it standalone"
- REQ-061 AC-4: "The grouping logic is explicit and auditable (every grouping decision recorded)."
- ADR-084: "A group is named only as a resemblance to a template"
- ADR-084: "An adopted leg's entry price is Zerodha's average price for that position"

## What to build
1. `suggest_groups(positions, strategies, catalogue)` (domain, standard library): open positions (non-zero quantity) not
   already in a strategy (match by contract identity via the catalogue, not by symbol text alone), grouped by
   (underlying, expiry); each group carries the matcher's resemblance label or none (Custom), never a strategy.
   Calendars are not suggested together (ADR-084 consequence).
2. A grouping session object: `move(position, to_group | to_strategy | standalone)`, `set_entry(position, price)`
   (Decimal, tick-valid, > 0), `confirm(group)` -> a new strategy (or legs added to an existing one through its proper
   method) with entry = Zerodha average unless edited, marked From-Zerodha vs Edited, product carried over. A
   standalone position is shown and never gets an order or a monitor.
3. Every action (suggest, move, set_entry, confirm, standalone) appends an audit entry through the existing audit log
   API (never a raw write); the entry names the position, from/to, old/new price, actor and time (DB/clock seam, no wall
   clock in tests).
4. Fail closed: a position whose contract is not in the catalogue -> shown, cannot be adopted (four-part message);
   quantity not a lot multiple -> refuse adoption; a position moved into a strategy of another underlying/expiry ->
   allowed only into an existing strategy whose legs share the underlying (calendar by explicit move), refuse otherwise.

## Reviewer checklist (write first; each red when mutated)
- Grouping key (underlying, expiry): drop expiry -> red (the 26-Oct short call joins the condor).
- In-strategy leg excluded; matched by contract identity -> red if matched by symbol text with a renamed row.
- Resemblance never applied: no strategy exists before confirm.
- Entry = average price unless edited; edited flag; product carried (MIS stays MIS).
- Every action writes exactly one audit entry; a forged/raw audit write is impossible (use the log's public API).
- Every guard has a killing test; list them.

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/reconciliation`, then `tests/strategy`, `tests/audit`
  (or the audit log's test dir), `tests/errors`, separately. No database. Then your worktree's own atool `--no-tests`.
- Do not touch backend/ofo/execution/basket.py, backend/ofo/broker/, backend/ofo_app/kite_http.py (W-080 in flight) or
  margin code (W-081). No kit/`spec/`/`views/`/findings INDEX edits; never write `evidence/`.
- Commit, push `build/W-083-position-grouping`. No PR.
