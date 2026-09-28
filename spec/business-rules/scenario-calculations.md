# Scenario and P&L calculations

Decisions: ADR-008 (Q15, Q33, Q33A–Q33D), ADR-001 (leg types). Sources: full chat T1 #83–#118 (the owner derived
the formulas, #95–#98); handoffs §21–§25. These rules are locked; code must match them exactly and must not duplicate them outside the one
calculation engine.

## 1. Expiry scenario P&L per leg (locked; owner, T1 #95–#98; entry-price rule confirmed by the owner 2026-09-29, ADR-035)

`Market` = the scenario underlying level at expiry. `Quantity` = units (lots × lot size), never lots.

| Leg | Expiry P&L |
|---|---|
| BUY CALL | `[MAX(Market − Strike, 0) − Entry Price] × Quantity` |
| SELL CALL | `[Entry Price − MAX(Market − Strike, 0)] × Quantity` |
| BUY PUT | `[MAX(Strike − Market, 0) − Entry Price] × Quantity` |
| SELL PUT | `[Entry Price − MAX(Strike − Market, 0)] × Quantity` |
| BUY FUTURES | `(Market − Entry Price) × Quantity` (Q207 = A, owner 2026-09-29, ADR-041) |
| SELL FUTURES | `(Entry Price − Market) × Quantity` (Q207 = A, owner 2026-09-29, ADR-041) |

- Strategy scenario P&L at a level = the sum of every leg's P&L at that level.
- Expiry scenarios use the **entry price**, never the current LTP. The LTP is used only in the live (current) P&L
  columns (§2), which Q33A = C shows alongside expiry P&L. Source: the owner typed the current price (₹38.20) at
  T1 #95; ChatGPT changed it to the entry price at #96; the owner confirmed the entry price on 2026-09-29 (Q215,
  ADR-035). Worked check: BUY 22,800 PE, entry ₹42.50, LTP ₹38.20, Quantity 75, Market 22,000 → expiry P&L
  `(800 − 42.50) × 75 = ₹56,812.50` (not ₹57,135, which the LTP would give).
- Every cell is filled for every leg, including out-of-the-money legs (owner, T1 #93, #95). No blanks.

## 2. Live (current) P&L (T1 #85)

- Per leg: BUY `(LTP − Entry Price) × Quantity`; SELL `(Entry Price − LTP) × Quantity`. Applies to option and
  futures legs alike (for a futures leg, LTP is the futures contract's LTP; ADR-041).
- First-class live fields: Entry Price, LTP, Entry Value, Current Value, Unrealized P&L, P&L %.
- Whether LTP, bid/ask mid or another price is used for live estimates, slippage and charges: open (§95).

## 3. Strategy-level values

- Net premium, max profit, max loss and breakevens are **strategy-level** (T1 #98); legs carry no breakeven.
- Max profit/loss and breakevens are computed from the payoff, never typed or hard-coded.
- **Net premium (definition, 2026-09-29, delegated overnight, ADR-045; W-013 fix round).** Signed rupee total, credit
  positive: each SELL option leg adds `price × Quantity`, each BUY option leg subtracts it; futures legs have no
  premium and add 0. `price` is the entry price or the LTP, named by the caller. Example: BUY 75 × 23,000 CE @ 100,
  SELL 150 × 23,200 CE @ 60 → 9,000 − 7,500 = **+₹1,500**; the §6 Iron Condor at entry → 91 × 75 = **+₹6,825**
  (equal to its max profit). Every consumer (rules, screens) reads it from the engine, never re-computes it.
- Payoff graph and scenario table use the same engine (§22).
- **Tails (clarification, 2026-09-29, delegated overnight, ADR-045).** An index cannot fall below 0, so the lower tail
  is evaluated at level 0 and is always finite; only the upper tail can be UNLIMITED (non-zero slope above the highest
  strike). Example: SELL 23,000 PE at ₹80 × 75 → max loss ₹17,19,000 (not "unlimited"); BUY 24,000 FUT × 75 → max
  loss ₹18,00,000, max profit UNLIMITED. `min_pnl` is the signed minimum of the payoff; max loss is its magnitude
  when negative, else 0. Breakevens are reported only above 0; a non-terminating breakeven is rounded half-even to
  0.01 points.

## 4. Scenario levels and views (Q33, Q33A–Q33D — owner answers, T1 #83–#118)

- Breakevens appear twice (Q213, delegated overnight, ADR-045): as 0-P&L columns inserted at their price position
  in the grid (Q33D = C) AND as Lower BE / Upper BE summary columns after the grid (T1 #90); a missing breakeven
  shows "—".
- Scenario column step is set **per index in Admin**: default **NIFTY 100 points**, **SENSEX 300 points**; every
  column sits on a real strike level (a multiple of the index's strike gap: NIFTY 50, SENSEX 100, measured
  2026-09-29) (Q208 = A, ADR-042). NIFTY columns are anchored to **rounded 100-point index levels** (Q33C). Index
  levels are **points**, not money: ₹ is used only for money values (premiums, P&L, margin); ChatGPT's option text
  "Rounded ₹100 level" (T1 #114) meant index points.
- The default range is chosen from spot, strikes, breakevens, risk boundaries and expected move; the user can
  customise it (Q33B = E). Example: NIFTY 23,000 → 22,000 … 24,000.
- The **exact live level (CURRENT)** and the **0-P&L / breakeven levels** are added as extra columns **at their actual
  price position**, e.g. `22,900 | 22,909 0-P&L | 23,000 | 23,047 CURRENT | 23,100 …` (Q33C, Q33D = C).
- Two views of the same columns (Q33A = C): **At Expiry** (default; the formulas in §1) and **Estimated Now**
  (model-based value before expiry using time and IV; labelled as an estimate; model not yet specified).
- Open: SENSEX step (Q208); whether Lower/Upper BE summary columns stay after the grid as well (Q213).
- **Level-set rules (implementation of Q33B–Q33D, 2026-09-29, delegated overnight under ADR-045, W-003; the spec
  was silent on these details — open for owner review, no decision row changed).** Code: `backend/ofo/scenario/`.
  - Admin config per index (points): step, anchor, minimum half-width, margin steps, maximum columns. Defaults NIFTY
    100 / 100 / 1,000 / 2 / 200 and SENSEX 300 / 300 / 3,000 / 2 / 200. Step and anchor must be multiples of the
    strike gap listed in the instrument catalogue for that expiry, else the config is refused.
  - Default range: covers spot, every strike, every breakeven, every risk boundary (strike where the payoff reaches
    max loss) and, when IV and days are given, spot ± spot × IV × √(days/365); plus the margin steps beyond the
    outermost of these; and at least the minimum half-width each side of spot rounded to the anchor. Example: the
    §6 Iron Condor at spot 23,047 → 22,000 … 24,000 (21 grid columns + 22,909, 23,047 CURRENT, 23,491 = 24 columns).
  - A user range must start and end on anchor multiples a whole number of steps apart. The CURRENT column is always
    present, even outside a user range (at its price position); a breakeven outside the range is not inserted but
    still shows in Lower BE / Upper BE.
  - Lower BE / Upper BE: with two or more breakevens, the lowest and highest; with exactly one, it is the Lower BE
    when the payoff is a profit above it (long call, short put) and the Upper BE when the profit lies below it;
    the other shows "—".
  - Estimated Now at a breakeven with more than two decimals is taken at that level rounded half-even to 0.01; a
    strategy with an option leg lacking IV has no Estimated Now view (shown unavailable with the reason).

## 5. Money precision

Use exact decimal arithmetic (or integer paise) for all money. Measured 2026-09-28: plain binary floating point
gives `-322.4999999999998` for the Iron Condor's leg 1, which must be `-322.50`. Show values rounded to paise; avoid
false precision for estimates (Q15, e.g. "~73%" not "73.48291%").

## 6. Golden test: the handoffs' Iron Condor (verified 2026-09-28)

NIFTY, quantity 75 on every leg (75 is illustrative; real lot size always comes from the instrument master).

| Leg | Contract | Entry | LTP | Live P&L |
|---|---|---|---|---|
| 1 | BUY 22,800 PE | 42.50 | 38.20 | −₹322.50 |
| 2 | SELL 23,000 PE | 86.00 | 72.50 | +₹1,012.50 |
| 3 | SELL 23,400 CE | 91.50 | 78.00 | +₹1,012.50 |
| 4 | BUY 23,600 CE | 44.00 | 39.50 | −₹337.50 |
| | **Strategy** | | | **+₹1,365.00** |

- Net credit 86 + 91.50 − 42.50 − 44 = ₹91/unit → **₹6,825** = max profit. Max loss (200 − 91) × 75 = **₹8,175**.
- Breakevens 23,000 − 91 = **22,909** and 23,400 + 91 = **23,491**.
- Strategy expiry P&L: 22,000–22,800 = −₹8,175 · 22,900 = −₹675 · 23,000–23,400 = +₹6,825 · 23,500 = −₹675 ·
  23,600–24,000 = −₹8,175.
- Per-leg samples (15 Sep §33): leg 1 at 22,000 = +₹56,812.50; leg 2 at 22,000 = −₹68,550; leg 3 at 23,500 =
  −₹637.50; leg 4 at 24,000 = +₹26,700.

**Evidence:** every number above (4 live legs, the total, 21 strategy levels, credit, max loss, both breakevens,
18 per-leg samples) was recomputed from the formulas in §1 on 2026-09-28 with 0 mismatches. This table is the first
test fixture for the calculation engine.
