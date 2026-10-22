# Builder sequence core proof - 2026-10-22 10:03-10:10 IST

Contract: `goal-contract-builder-sequence-2026-10-22.md`, Core/Proof lines. Code under test: main at 235e1793 (the
main checkout), order path off (`/features` -> `"order_path":"off"`). No order was sent.

## Half 1: recorded replay (APP_ENV=test, OUTCOME_REPLAY=1, frames 2026-10-08 09:20, port 8771, ofo_dev)

NIFTY iron condor, expiry 2026-10-13, 1 lot (65), spot 22533.25. Planned entries from `POST /api/strategies/planned-entry`
(source `ltp`): SELL 22700 CE 64.70, BUY 22900 CE 22.70, SELL 22350 PE 67.60, BUY 22150 PE 28.95.

Hand calculation (Decimal): net credit 80.65 per unit; before charges max profit 5,242.25, max loss 7,757.75,
breakevens 22,269.35 and 22,780.65.

Engine (`POST /api/strategies/outcome`): breakevens 22269.35 / 22780.65 (equal); max profit 5025.10, max loss 7974.90,
charges 217.15. All 24 scenario levels equal `hand P&L before charges - 217.15 - 0.15% STT on the exercised value of the
bought option that ends in the money` to the paisa (24 of 24).

Save + reload could not run on the replay locally: ofo_dev holds no 2026-10-08 contracts (first list 2026-10-15) and
the test-catalogue seed is CI-only by design (`seed_test_catalogue.py` refuses off a CI runner). Half 2 covers it.

## Half 2: live (owner's Kite login 10:06 IST, LIVE_MARKET=1, port 8765, ofo_dev)

Live index socket: NIFTY 22,619.10 at 10:07:45, SENSEX 73,188.16. NIFTY iron condor, expiry 2026-10-27, 1 lot (65):
SELL 22750 CE 118.95, BUY 22950 CE 59.10, SELL 22450 PE 86.45, BUY 22250 PE 43.10 (live planned entries).

Hand: credit 103.20; before charges max profit 6,708.00, max loss 6,292.00, breakevens 22,346.80 / 22,853.20.
Engine (live socket `/api/strategies/live`): breakevens 22346.8 / 22853.2 (equal), max profit 6471.79, max loss
6528.21, charges 236.21; 24 of 24 levels equal the hand value on the same charges basis.

Save `POST /strategies` -> draft id 20, revision 1; `GET /strategies/20` returned every leg's contract id, action,
quantity and planned entry exactly as sent (4 of 4). The outcome rebuilt from the RELOADED record equals the outcome
before the save (summary equal: True; scenario totals equal: True).

## Verdict: core PASS, with two known gaps carried to their rows

1. **Basis is the pre-ADR-167 one.** Main's scenario totals and max profit/loss include charges, while the breakevens
   do not: the replay's total AT the breakeven 22,269.35 is -217.15, not 0. ADR-167 (curves and scenario values before
   charges) is built only on branch `build/W-127-b2-payoff`; it lands at rows 26 / 36. Not a new defect.
2. **First live frame is a refusal.** 3 of 3 fresh live sockets first pushed `REFUSED` ("the forward price could not
   be derived from the option chain"), then `COMPUTED` about 1 s later. REQ-133 AC-3, row 24 (not built). Finding
   `knowledge/findings/first-live-frame-before-first-price.json`.

Also seen (for rows 2 / 7): before the login, `/api/broker/status` said `live_market_data: connected` while
`/api/market/indices` answered `NOT_CONNECTED` with no value. It was not re-checked after the login; it gets measured
under REQ-015 / REQ-049.

Scripts (outside the repo, session scratchpad): `core_replay.py`, `core_live.py`, `run_api_replay.py`.
