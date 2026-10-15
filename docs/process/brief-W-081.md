# Builder brief: W-081 margin check before the basket (Tier A)

Core: against the real 2026-10-15 basket-margin reply for the 4-leg NIFTY iron condor (`final.total` 68498.85,
`initial.total` 296332.8), available Rs 68,498.85 builds the basket and Rs 68,498.84 blocks it, the message showing
available vs required.
Proof: step 1 is `tests/execution/test_margin_gate.py` using
`docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json` (`json.load(..., parse_float=Decimal)`) as
the required-margin input. Write it FIRST, red.

Tier: A (execution gate, money). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD limit: at call 60 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no margin-gate row (searched: margin); algochanakya's order adapter is not copied (ADR-054).

Read first: `docs/process/builder-brief.md`, `work/W-081.md` (incl. the decision by role on `final.total`),
`spec/requirements/REQ-055.md`, `spec/decisions/ADR-016.md`, `backend/ofo_app/kite_client.py` (existing HTTP client
style, token use), the Kite token store (`backend/ofo_app/` token store module, find it), the error catalogue
(`backend/ofo/errors/`), `CLAUDE.md`.

## Spec basis
- REQ-055 AC-1: "fetch available funds/margin from Zerodha, obtain the required margin for
    the planned orders, and build the basket only if sufficient"
- REQ-055 AC-3: "The platform's own margin figure is shown as a planning estimate; Zerodha's figure is authoritative."
- REQ-055 AC-4: "If margin is insufficient: no basket is built; show available vs required, and offer quantity change, review,
    or an add-funds path."

## What to build
1. App layer client (`backend/ofo_app/`): `fetch_available_funds()` (Kite `GET /user/margins`, `equity.net` as
   Decimal) and `fetch_basket_margin(orders)` (Kite `POST /margins/basket?consider_positions=true` with the request
   shape of `margins_basket.json`'s `request`; returns `final.total`, `initial.total` and the per-order rows as
   Decimal). HTTP behind an injectable transport; tests replay the recorded reply files - no network in tests. A
   non-success status, a missing `final`/`total`, or a non-numeric value -> a typed error (fail closed: no basket).
2. Domain (`backend/ofo/execution/margin_gate.py`, standard library): `check_margin(available, required)` returns
   allowed / blocked with both amounts; boundary: equal is allowed; never accepts a caller-built verdict (builder
   brief rule) - the basket builder (W-080, parallel) will CALL this gate; expose a function W-080 can call, do not edit
   W-080's files.
3. Blocked -> four-part catalogue message (REQ-065/ADR-086) naming available and required as rupee display strings
   from the engine's money formatter (ADR-008), and the three offers of AC-4. Pins updated.
4. AC-3: where a platform margin estimate exists in code (`ctx.margin_estimate` or similar in `safety.py`), its user
   text says the word estimate; Zerodha's figure decides the gate. Grep and report what exists; change only wording through
   the catalogue.

## Reviewer checklist (write first; each red when mutated)
- `>=` mutated to `>` (equal amounts) -> red; `initial.total` used instead of `final.total` -> red.
- Available 1 paisa short -> blocked, message carries both amounts exactly.
- Client: HTTP 403/500, missing `final`, a non-numeric total -> typed error, gate blocks.
- Float anywhere in money -> raises.
- Every guard has a killing test; list them.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/execution tests/errors`; app:
  `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_margin_client.py`
  (only if it needs the database; prefer no-database tests). Then your worktree's own
  `scripts/orchestrator/atool.py <worktree> W-081 --no-tests`.
- No route, no UI, no migration. Do not edit basket, freeze, charges or executable-price code (parallel items). No kit
  or `spec/` edit, no `views/`, no findings INDEX. Never write `evidence/`.
- Commit and push `build/W-081-margin-gate`. No PR.
