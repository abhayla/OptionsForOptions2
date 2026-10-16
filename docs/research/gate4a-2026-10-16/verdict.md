# Stage 4a gate re-run, 2026-10-16 (main 640a47b, live Kite, ofo_dev)

**Verdict: NOT PASSED.** The D8 money formulas pass on live data, but the run found a live-data defect (D-1): prices
stop updating with no warning. It also found that the leg picker cannot price legs (D-2).

## Setup
- The API on :8765 answered `NOT_CONNECTED` ("no live market data provider is connected") at 09:18. It started at
  08:54:52, and it reads the Kite session only when it starts, or else `LIVE_MARKET` was not set. I did not restart it.
- So I started a second app from the main checkout on :8766 (`serve.py`, run through dev_run.py, so it used ofo_dev).
  It used the stored session; there was no new Kite login. I stopped it afterwards.
- Expiry: 2026-10-19 (the nearest in the catalogue). Iron condor: SELL 23150 CE, BUY 23350 CE, SELL 22750 PE,
  BUY 22550 PE. Spot when the legs were picked: 22955.10. I also ran the condor plus a far-out 28700 CE leg.

## Check 2: D8, payoff equals the ADR-008 formula: PASS (formulas only)
- 3 REST calls at 09:20:26, 09:21:31 and 09:22:36. Each call: 27 graded cells matched with 0 mismatches, plus 144
  scenario cells with 0 mismatches. The live socket frame at each call also had 27 of 27 matching.
- TOTAL rows graded against ADR-076 (net amount, marked Cr or Dr). All three matched:
  - Entry Value: Rs 4,793.75 Cr in every call.
  - Current Value: Rs 4,137.25 Cr, then 4,225.00 Cr, then 4,098.25 Cr.
  - The ADR-076 check (entry minus current equals unrealized P&L) held: 656.50, 568.75, 695.50.
- The same grader flags the 2026-10-15 response, where Current Value was a plain sum (11105.25 against the expected
  4228.25), so the TOTAL check does catch the old error.
- Caveat: the spot input was frozen for all three calls (see D-1).

## Check 3: the saved draft reloads unchanged: equality PASS, gate PARTIAL
- I picked 4 legs in the screen, pressed Save Draft (draft 9), reloaded the page and reopened the draft. Every leg
  field was equal before and after, and the stored row matched the screen.
- But only 2 of the 4 legs got a planned entry from the leg picker (D-2). So ADR-075 was proven on 2 legs only.

## Check 4: screenshots of all 8 states: taken
- States seen: live = computed; stale leg = stale; API unreachable = error; no draft = no-draft. Each at 1280 and
  390 px, with no sideways scroll.
- Issue #232:
  - Item 1 (leg picker error): gone. The only error shown is the right one, in the API-unreachable state.
  - Item 2 (the broken "This request." fragment): gone.
  - Item 3 (raw instrument ids): the `NSE_FO:` ids are gone, but a variant remains. Legs opened from a link show
    "Contract details not available", and the notice box shows raw trading symbols such as `NIFTY26O1923150CE`.
  - Item 4 (raw ISO times): gone.

## Defects
- **D-1 (blocks the gate): prices freeze with no warning.** One socket releases an instrument, another socket
  subscribes it straight after, and that instrument stops updating. The answer still says COMPUTED and live.
  - In D8, `spot_at` stayed at 09:20:15 for all 3 calls while the leg prices moved.
  - Reproduced in `repro_spot.json`: spot frozen at 22982.45 (spot_at 09:23:39) for 26 s while the legs ticked.
  - In the 5-leg screenshot, two liquid at-the-money legs show "no live quote" during market hours.
  - Likely cause: the Kite subscription is lost when an instrument is released and taken again (unsubscribe and
    subscribe in the same diff). This is not proven in code.
- **D-2: the leg picker gets no price for a contract no socket is holding.** Legs 1 and 4 came back "no live price".
  The two legs that were priced had been held by a socket about 15 s earlier.
- **D-3: a last price (LTP) of 0 is used as a real price.** The 28700 CE had LTP 0 with health "available". It
  showed Current Value Rs 0.00 and P&L -100.00%. ADR-020 Q185 says "no fake prices", and the planned-entry route
  already refuses a zero price.
- **Minor:**
  - A stray "estimated from spot" fragment, and the same notice printed twice.
  - The page says "Margin from Zerodha is not shown yet; it needs your Kite login" even though a session exists.
  - The "Loss" line in the payoff chart is drawn at 0 across the profit zone.
