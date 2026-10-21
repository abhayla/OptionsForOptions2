# W-118 builder brief (GC-5S item 4b): Option Chain screen, display only

Common brief: docs/process/builder-brief.md
Core: the Option Chain page renders W-116's chain socket rows as Calls | Strike | Puts with the ATM row marked, and shows no number from an answer that is not live for this page's own socket.
Proof: Vitest with a fake chain socket: two pushes change an LTP cell; a drop with a failing fallback leaves no number on screen (finding last-live-answer-kept-after-drop).
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (display; no money computed; the data path is W-116's, Tier A, already reviewed).
Copy from: spec/technical-design/legacy-reuse.md row 144 (`views/OptionChainView.vue`: ADAPT, no local ATM fallback, strike logic in the backend) for layout only.
Design basis: docs/design/screens-research-2026-10-19.md section `Option Chain` (header: underlying selector, spot + time + health, expiry selector with days left; rows by strike; ATM highlighted; 15 strikes each side; at 390 px the table scrolls inside its card and keeps LTP + OI per side visible first).

## Spec basis (quoted)
- REQ-029 AC-1: "The chain lays out Calls | Strike | Puts for a chosen underlying and expiry."
- REQ-029 AC-2: "Default columns: Strike, LTP, Change, OI, Volume (Q45); IV appears from the Advanced level only (Q232, ADR-056)."
- REQ-029 AC-6: "The chain never offers direct order placement."
- REQ-029 AC-8: "The ATM strike is highlighted, the underlying price is shown, an expiry selector sits on top, and selected contracts are highlighted (Q45)."
- Not here: REQ-030 (selection, Buy/Sell chips, import), REQ-031 (preview), AC-3/AC-9 Advanced fields and filters (no
  IV/Greeks/bid-ask in W-116's payload), AC-7 Pro-only (no entitlement route). `change` arrives null (F-47): the Change
  column shows `-` with no computed value.

## What to build
1. `/market/option-chain` (nav.js:40) -> `OptionChainPage.vue`. Underlying selector (NIFTY / SENSEX), expiry selector
   from `/api/catalogue/{u}/expiries` (nearest first), days-left label from the expiry date only.
2. A chain composable built the W-115 way (one state machine owns first-paint read, drop counter, clear-on-drop,
   fallback read; components render its rows) - follow `useIndexAnswer` in `frontend/src/composables/useIndexLive.js`;
   reuse `createLiveSocket` backoff (import, never copy).
3. Table: Calls (LTP, Change, OI, Volume) | Strike | Puts (same, mirrored); ATM row highlighted from the server's
   `atm_strike`; each cell shows its health word when not `available`; values as given (strings). No Buy/Sell, no order
   link (AC-6).
4. States: LIVE, NOT_CONNECTED (server label), rows_missing reasons, catalogue unreadable, socket down.

## Tests
`frontend/tests/option-chain.test.js`: AC-1 layout order; AC-2 the four default columns per side, no IV column; AC-8 ATM
row marked, spot + time shown, expiry selector present; AC-6 no button/link to any order or execute route; the Proof's
drop table. Mutations: clear-on-drop removed -> red; ATM marking from a browser guess instead of the server -> red.
Run `npm run lint`, `npx vitest run tests/option-chain.test.js`, `npm run build`.

## Isolation
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w118` (branch `build/W-118-chain-screen`, stacked on W-116 only;
read W-115's `useIndexAnswer` for the pattern with `git -C D:/Abhay/Ventures/OptionsForOptions2-gc5s-w118 show
origin/build/W-115-home:frontend/src/composables/useIndexLive.js` - follow its state machine, do not import from that
unmerged branch; import `createLiveSocket` from `frontend/src/composables/useStrategyLive.js`, which is on main). Never run git or npm in
`D:\Abhay\Ventures\OptionsForOptions2`; no database, no server, no Playwright run; no backend change. Commit, push; no PR.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.
