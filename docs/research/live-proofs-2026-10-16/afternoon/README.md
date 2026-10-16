# Live proofs, 2026-10-16 afternoon (owner present)

All Kite calls here are reads or calculations (`/quote`, `/instruments`, `/margins/basket`, `/charges/orders`,
`/user/margins`, `/portfolio/*`, `/orders`, `/trades`); no order is placed by any script. Raw recordings with account
data stay outside the repo in `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/` (`frames-*.bin.gz`, `rest/`, `outcome/`,
`real-order/`).

## Real 1-lot test order (ADR-097)
- Basket built by W-080's `build_basket` (branch land/W-080-r8, offline) from `real_order.py fetch` replies; real gates:
  freeze check, Zerodha margin with the ADR-094 top-up, funds. The page's one button posted the basket form to Kite's
  basket page; the owner pressed Execute.
- Order 261016170576173: BUY NIFTY26O1923650CE NFO NRML LIMIT 5.45 qty 65, COMPLETE 12:20:50, average 5.10
  (trade 4484194); tag `OFS1V1L0` came back on Kite's order. Funds 1,003 -> 671.50 (exactly 65 x 5.10; charges come
  with the contract note). Holdings before/after: 6 symbols, unchanged.
- W-080's runtime egress gate refused the first script's direct urllib call (`EgressRefused: socket.connect to
  ('104.16.33.50', 443) refused`), so Kite reads ran under main's code and the basket was built offline.

## ADR-094 / ADR-095 on main after merge (`live_proof_pm.py`, `live-proof-pm.json`, 13:45 IST)
- ADR-094 NIFTY long strangle at limits live + 5: Zerodha 5,453.50, required 6,103.50, top-up 650.00 = 2 x 65 x 5;
  SENSEX: 13,906 -> 14,104 (top-up 198 <= 200, price moved between quote and reply); both blocked against funds 671.50.
- ADR-095 live NIFTY iron condor, Rs 300 tolerance: limits 22.05 / 41.10 / 39.60 / 16.05, total adverse 292.50 <= 300,
  every leg fills within its limit on live depth.

## Recorders (weekend input)
- `rec_rest.py`: every 20 min, 10 shapes x NIFTY/SENSEX, bumps 0/2/5, consider_positions true/false, charges, funds,
  positions - 92 calls per round, all 200.
- Websocket full-chain frames (1,293 instruments) through the close; outcome pushes for 5 shapes x 2 UX levels every
  10 min from the API's live socket.
