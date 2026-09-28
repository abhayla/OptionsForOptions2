# Scenario and P&L calculations

Decisions: ADR-008 (Q15, Q33, Q33A–Q33D), ADR-001 (leg types). Sources: full chat T1 #83–#118 (the owner derived
the formulas, #95–#98); handoffs §21–§25. These rules are locked; code must match them exactly and must not duplicate them outside the one
calculation engine.

## 1. Expiry scenario P&L per leg (locked; owner, T1 #95–#98)

`Market` = the scenario underlying level at expiry. `Quantity` = units (lots × lot size), never lots.

| Leg | Expiry P&L |
|---|---|
| BUY CALL | `[MAX(Market − Strike, 0) − Entry Price] × Quantity` |
| SELL CALL | `[Entry Price − MAX(Market − Strike, 0)] × Quantity` |
| BUY PUT | `[MAX(Strike − Market, 0) − Entry Price] × Quantity` |
| SELL PUT | `[Entry Price − MAX(Strike − Market, 0)] × Quantity` |
| BUY FUTURES | **not decided** — proposed `(Market − Entry Price) × Quantity` (open question Q207) |
| SELL FUTURES | **not decided** — proposed `(Entry Price − Market) × Quantity` (open question Q207) |

- Strategy scenario P&L at a level = the sum of every leg's P&L at that level.
- Expiry scenarios use the **entry price**, never the current LTP.
- Every cell is filled for every leg, including out-of-the-money legs (owner, T1 #93, #95). No blanks.

## 2. Live (current) P&L (T1 #85)

- Per leg: BUY `(LTP − Entry Price) × Quantity`; SELL `(Entry Price − LTP) × Quantity`.
- First-class live fields: Entry Price, LTP, Entry Value, Current Value, Unrealized P&L, P&L %.
- Whether LTP, bid/ask mid or another price is used for live estimates, slippage and charges: open (§95).

## 3. Strategy-level values

- Net premium, max profit, max loss and breakevens are **strategy-level** (T1 #98); legs carry no breakeven.
- Max profit/loss and breakevens are computed from the payoff, never typed or hard-coded.
- Payoff graph and scenario table use the same engine (§22).

## 4. Scenario levels and views (Q33, Q33A–Q33D — owner answers, T1 #83–#118)

- Scenario columns are ~100 points apart for NIFTY, anchored to **rounded ₹100 levels** (Q33C).
- The default range is chosen from spot, strikes, breakevens, risk boundaries and expected move; the user can
  customise it (Q33B = E). Example: NIFTY 23,000 → 22,000 … 24,000.
- The **exact live level (CURRENT)** and the **0-P&L / breakeven levels** are added as extra columns **at their actual
  price position**, e.g. `22,900 | 22,909 0-P&L | 23,000 | 23,047 CURRENT | 23,100 …` (Q33C, Q33D = C).
- Two views of the same columns (Q33A = C): **At Expiry** (default; the formulas in §1) and **Estimated Now**
  (model-based value before expiry using time and IV; labelled as an estimate; model not yet specified).
- Open: SENSEX step (Q208); whether Lower/Upper BE summary columns stay after the grid as well (Q213).

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
