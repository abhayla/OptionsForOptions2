# Builder brief: W-102 The full cost in the Execute reply - net premium, charges, Zerodha funds and margin (Tier A: money)

Core: the Execute reply for the real ENTRY (strategy 1, BUY 65 NIFTY26O1923650CE LIMIT 3.35) carries
`net_premium` "-217.75" (paid; BUY pays, SELL receives; quantity x LIMIT per leg), `charges` = the total from
`ofo/charges/calculator.py` at the stored rate set as a 2-decimal string (expected value hand-computed from the rate
set's numbers and written in the test docstring - never pasted from your own output), and Zerodha's `funds_available`
and `margin_required` from the route's `_context` read, with `figures_read_at`. The EXIT reply (SELL 65 LIMIT 3.30)
shows `net_premium` "214.50" (received) and its own charges. No rates -> `charges` null plus `charges_note` saying
the charges are not included, never a default.
Proof: a pure-function test of the cost builder on the real ENTRY and EXIT legs (no DB), plus the route test's
existing core sequence extended to assert the new fields (runs in CI's DB job).

Tier: A. Model: opus.
Budget: 55 min wall-clock, 60 tool calls. HARD limit: at call 56 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - the calculator (`backend/ofo/charges/calculator.py`), the rate loader (`load_charge_rates` in
`backend/ofo_app/routes/outcome.py`) and the margin reads (`_zerodha_margin` in `backend/ofo_app/routes/execute.py`)
all exist; reuse them, never copy.
Findings checked: money-value-computed-outside-engine, money-parsed-through-float, margin-gate-blocks-closing-basket, test-asserts-implementation-output, fallback-time-claims-missing-data, repo-wide-scan-outside-targeted-tests
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-056 AC-8: "'Prepare Orders' builds the order plan (leg, action, instrument,
    quantity, order type, price, sequence, margin, charges, broker warnings) without placing anything"
- ADR-097: "the owner gives a final yes on the exact contract, side, quantity, limit price
  and cost"
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only"

## Build
1. A cost function in the domain (`backend/ofo/execution/` - pick the module that owns order plans; standard library
   only) taking the basket's orders (side, quantity, price, segment) and an optional `ChargeRates`: per leg signed
   premium (BUY -> negative, SELL -> positive), the sum as `net_premium`, and `charges_for_orders(...).total` when rates
   exist. Decimal throughout; quantize to paise (`ofo/money.py` PAISE) only at the API boundary.
2. `ExecuteOut` (`backend/ofo_app/routes/execute.py`) gains `cost`: {`net_premium`, `charges` (nullable),
   `charges_note` (nullable, catalogue text only - add an entry to the error/message catalogue if a sentence is new),
   `funds_available`, `margin_required`, `figures_read_at`} - every money field the `Money` 2-decimal string type.
   `funds_available` / `margin_required` are the values `_zerodha_margin` already returns in `_context` (keep them from
   that single read; do NOT read Zerodha again and do NOT touch the sealed basket - W-098). `figures_read_at` = the
   route clock read right after that call (an ISO string with offset). The exit's `margin_required` is whatever Zerodha
   returned (it can be negative for a closing basket - finding margin-gate-blocks-closing-basket): show it as given.
3. The rates: `load_charge_rates()` (already used by the outcome route), as a route dependency so a test can pass
   None. The browser computes nothing.
4. Update every test tree that asserts the Execute reply shape: grep `tests_app/`, `frontend/` for `plan_number` /
   `ExecuteOut` and add the field expectations (finding targeted-tests-miss-dependent-files). Regenerate nothing
   (`views/`, OpenAPI files) in this PR unless a check fails without it - then say so.

## Reviewer checklist (the Tier A reviewer checks exactly this; attack cases first)
- Attack: a SELL leg's premium sign; a 2-leg basket (BUY + SELL) nets correctly; quantity 0 or negative refused.
- Attack: rates None -> `charges` null + note, and no number anywhere claims to include charges.
- Attack: a float anywhere on the path (`Decimal(float)`), a JSON number for money in the reply.
- Expected values in tests come from a hand computation shown in the docstring.
- Funds/margin come from the one `_context` read (count Kite calls in the core test: unchanged from main).
- The exit case uses the real recorded exit margin reply (`margins-basket-exit-150717.json`).

## DB
NOT the shared-DB holder (W-103 holds ofo_test this run). Run NO DB command locally; the route's DB tests run in CI.
Local: the pure-function tests + the Tests line + `python scripts/ruff_ratchet.py`.

## Rules
- Branch `build/W-102-execute-cost` from origin/main. Work card `work/W-102.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-056, REQ-073]; tier A; depends_on [W-095]; tests_required
  ['AC-8: tests/execution/test_execute_cost.py', 'AC-1: tests_app/test_execute_route.py']) and `W-102: 4b` in
  `docs/process/coverage-stages.yaml`. Another builder (W-103) also edits `routes/execute.py` (audit write after
  `record_plan`): keep your change to `ExecuteOut`, `_answer` and `_context`'s return, nothing else in that file.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
