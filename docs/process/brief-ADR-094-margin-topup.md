# Builder brief: ADR-094 margin top-up for option BUY legs (Tier A: money)

Core: for a real Kite `POST /margins/basket` reply recorded today, `required_from_basket_reply(data, orders)` returns
`final.total` + sum over option BUY legs of max(0, quantity x limit price - that leg's `option_premium`), and blocks
(raises `MarginReplyError`) when a BUY leg's `option_premium` is missing, not a Decimal/int, or negative.
Proof: a test on the real recorded reply (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/rest/rest-*.json`, a call named
`margins/basket NIFTY ... long_strangle bump=5 cp=true`): copy that one call's `request` + `reply.body` into
`tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json` (no account data: it holds only margin
figures) and assert the exact Decimal sum by hand-computed numbers from that file. Show the test red on origin/main first.

Model: sonnet.
Budget: 30 min wall-clock, 60 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words.
Copy from: none - extends this repo's `backend/ofo/execution/margin_gate.py` (W-081); algochanakya has no basket
margin top-up (legacy-reuse map has no margin-gate row).

## Spec basis
ADR-094 decision, verbatim: "The margin the basket needs is Zerodha's basket figure (`final.total` of `POST
/margins/basket`) plus, for every option BUY leg, max(0, quantity x limit price - that leg's `option_premium` in the
same reply). SELL legs add nothing; a negative difference counts as 0, never as a credit." Also ADR-016 (no margin model
of our own), REQ-055 AC-1/3/4, finding F-39.

## What to build
- `backend/ofo/execution/margin_gate.py`: `required_from_basket_reply(data, orders)` where `orders` is the request list
  sent to Kite (same order as `data["orders"]`). Pair reply orders with request orders by index AND check each pair's
  `tradingsymbol`/`exchange`/`transaction_type` match; a count or identity mismatch raises `MarginReplyError` (fail
  closed). An option leg = tradingsymbol ending CE/PE on NFO/BFO (reuse an existing helper if one exists - grep
  `instrument_type`, `is_option` first). Futures BUY legs add nothing.
- Quantity and price from the request: `quantity` int > 0, `price` exact Decimal > 0, else raise.
- Keep the old one-argument behaviour impossible: update every caller (grep `required_from_basket_reply`).
- Money exact Decimal, no float; the result is never below `final.total`.

## Reviewer checklist (the Tier A reviewer will attack these - test each first)
1. SELL leg with option_premium negative or larger than qty x price adds 0.
2. BUY leg with qty x price < option_premium adds 0 (never a credit).
3. BUY leg with option_premium missing / None / float / str / bool / negative -> raises.
4. Reply has fewer or more orders than the request, or orders swapped -> raises.
5. Futures BUY adds nothing; option on BFO (SENSEX) counted.
6. The 10:33 case from ADR-094: Kite 2,073.50, two BUY legs at limits 5.00 above live -> 2,723.50.
7. Mutation: flip `max(0, ...)` to plain difference, or drop the identity check -> a test must fail.
Findings classes checked: `identifier-unique-only-by-convention`, `targeted-tests-miss-dependent-files` (grep every
importer of margin_gate and run its tests).

## Rules
- Your own worktree, branch `build/ADR-094-margin-topup` from `origin/main`.
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/execution` plus any test file importing
  margin_gate; `python scripts/ruff_ratchet.py`.
- No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; no regenerated files in the PR.
- Commit and push the branch; do not open the PR; never write `evidence/`, `work/` or the spec.
