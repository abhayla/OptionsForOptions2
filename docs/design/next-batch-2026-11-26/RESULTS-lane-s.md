# RESULTS, Lane S: the "Real P&L" figure on the one Positions list (26 Nov 2026)

Highest status: **Fixed, not tested** (not screen-tested by the owner; no live open position read in this lane).
Branch `feat/nb-real-pnl-1126` from `feat/nb-screens-w2-1126` (a9bd41a). Standing direction: step 4 (the journey:
watch a real position), core, not iron-condor depth.

Spec basis: ADR-330 (10) and (24) (owner and coordinator, 26 Nov; LQS-1..3 in `owner-questions-lane-s.md`), ADR-008,
ADR-016 to ADR-019, ADR-109 (2), ADR-110, ADR-138 (2), ADR-003; REQ-044 AC-3 "Real P&L (Lane S)" paragraph.
Not readable here: the Sensibull study and the multi-broker-architecture folders (`D:\...`, the owner's PC). The
design rests on the spec and the existing adapter code only.

## What the figure is and where it comes from

- Per contract, the figure is **Zerodha's own `pnl`** from `GET /portfolio/positions` (read through the existing
  adapter, at most once per 45 s, `kite_period_reads.screen_positions`). The caption reads "Zerodha, as at HH:MM:SS IST".
- The one engine (`backend/ofo/engine/real_pnl.py`) re-derives it from Zerodha's own fields:
  `sell_value - buy_value + quantity x last_price x multiplier`, exact Decimal, both sides quantized to the paisa
  (half-even). Shown only when the two agree.
- A row shows a figure only if ONE predicate, `sole_holder` (`backend/ofo_app/routes/positions.py`), holds:
  (a) exactly one strategy holds the contract; (b) no outside lots on it; (c) no standalone record on it;
  (d) the strategy's units equal Zerodha's net; (e) every order filled on that contract today carries this
  strategy's own tag; (f) no flat row of the same contract (another product, closed today).
- The total is the exact sum of the rows' figures, shown only when every row has one. It is never added to Paper
  P&L, on the server or in the browser. The browser does no arithmetic: it prints the server's text.

Core proof on real recorded replies (owner's live session, 16 Oct 2026):

| Reply | Row | Zerodha `pnl` | Engine figure | Shown |
|---|---|---|---|---|
| `positions-122104.json` 12:21:07 (open) | NIFTY26O1923650CE qty 65, buy_value 331.5, sell_value 0, last 5.1 | 0 | 0 - 331.5 + 65 x 5.1 = 0.00 | 0.00 |
| `positions-151006.json` 15:10:09 (closed) | same, qty 0, buy 331.5, sell 201.5, last 3.1 | -130 | 201.5 - 331.5 + 0 = -130.00 | no row (closed today); total "No real positions are open in your strategies." plus the excludes line |

## States and their sentences (wording catalogue `backend/ofo/errors/explanations.py`, pins "pending owner read")

| State | Row / total | Sentence |
|---|---|---|
| stated | figure | caption "Zerodha, as at {time} IST" |
| not_available | no figure | "Zerodha's reply for {contract} lacks a figure needed to check its P&L; no figure is shown." |
| mismatch | no figure | "Zerodha's P&L for {contract} does not match its own trade values; no figure is shown." |
| shared | no figure | "This contract is shared (with another strategy or outside lots); Zerodha reports one P&L for the whole contract, so no split is shown." |
| shared (part closed) | no figure | "Part of {contract} was closed today on Zerodha and is reported apart, so no figure is shown for it." |
| pending (ADR-110) | no figure | "This contract is not yet confirmed, so no P&L is shown." |
| stale (> 90 s) | no figure | "Zerodha was last read more than {seconds} seconds ago, so no figure is shown until it is read again." |
| empty (total) | no figure | "No real positions are open in your strategies." |
| partial (total) | no figure | "{missing} of {total} contracts have no figure, so no total is shown." (distinct contracts) |
| excludes note | under total | "Excludes contracts not in a strategy here and contracts closed today." |
| broker not connected / unreadable reply | 409 refusal (unchanged) | the refusal's own catalogue message, under the dash |

## Tests, red then green

| Step | Red (before) | Green (after) |
|---|---|---|
| Build (engine, route, page) | written with the code by the builder (no red recorded) | engine 88, route 46, vitest 35 passed |
| Tier A review 1 (Opus): two holders doubled the total (-260 vs Zerodha -130), outside round trip, flat sibling, count | the 8 new tests run on the pre-fix code `d53fac2`: 8 failed, 137 passed (run by Lane S) | 145 passed (route + engine) |
| Tier A review 2 (Opus): another strategy's round trip on the same contract stated as this strategy's (-65 vs own 0.00) | 3 failed, 10 passed (builder, on unfixed code) | route + engine 149 passed; reviewer attacks F, G, H now "shared", total partial |
| Mutations (scratch copies) | removing derived==reported check, defaulting a missing field to 0, truncating instead of half-even, dropping (a), (e), (f), the `== sid` tag check: each fails at least one test | restored |

Owner-approved reviewer notes for the 7 new reply fields: commit d53fac2 (owner, 26 Nov 2026, in this session).

## Click-by-click check for the owner (browser, as a user)

1. Log in, Settings: Zerodha connected. Open Positions.
2. With no real NIFTY/SENSEX position in a strategy: "Real P&L" shows a dash and "No real positions are open in your
   strategies."; "Paper P&L" shows its own figure beside it, not added.
3. With one real position in one strategy: the row shows a rupee figure; the total shows the same figure with
   "Zerodha, as at HH:MM:SS IST". Open Kite's Positions at the same minute: the figure must equal Kite's P&L for that
   contract.
4. Disconnect Zerodha (or let the session expire), reload Positions: the Real total shows a dash and the
   "not connected" sentence; no old figure stays.
5. If a contract is in two strategies, or you also traded it on Kite outside the app today: that row and the total
   show a dash with the "shared" sentence (never a split figure).
6. Filter All / Real / Paper: the two totals stay separate in every filter.

## Not done, limits

- No real OPEN position has been read live through the new code (real orders hidden, ADR-281). Capture steps for the
  PC session: `owner-questions-lane-s.md`, "For the PC session".
- Not checked: Kite's carry-forward (overnight) meaning of `buy_value`/`sell_value` for positions bought on an
  earlier day; the e2e Playwright spec (mocks updated, not run); rows of other underlyings (e.g. BANKNIFTY) are not in
  the list or the total, so Kite's account total can differ (said in REQ-044).
- 10 new wording pins in `tests/errors/template_pins.json` wait for the owner's read.
- No order endpoint is called; no migration; no new route.
