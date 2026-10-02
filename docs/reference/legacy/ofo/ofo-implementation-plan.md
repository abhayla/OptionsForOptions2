<!-- Copied from abhayla/algochanakya@bf9faf7:docs/plans/ofo-implementation-plan.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# OFO (Options For Options) Implementation Plan

## Overview

OFO is a position sizing and strategy recommendation feature that analyzes the option chain data to find and rank the best option strategy combinations for each strategy type.

**Status:** Implemented

## Original Requirements

Create a new page 'OFO' (Options For Options) with the following capabilities:

1. **Page Access:** Add OFO link to the main navigation menu
2. **Selection Controls:**
   - Underlying index selection (NIFTY, BANKNIFTY, FINNIFTY) - like Option Chain screen
   - Expiry selection dropdown
   - Multi-select dropdown for strategy types
3. **Strategy Analysis:**
   - For each selected strategy type, calculate all valid combinations from option chain data
   - Filter out invalid options (CMP = 0, 0.5, or null; OI ≤ 0; premium < 1)
   - Calculate max profit at expiry for each combination
   - Display top 3 most profitable combinations per strategy
4. **Result Cards:**
   - Show card for each top combination with leg details
   - Columns: Expiry, CE/PE, Buy/Sell, Strike Price, CMP, Lots, Qty, P/L
   - Actions: Open in Strategy Builder, Place Order
5. **Performance:**
   - Track calculation time to determine if on-demand (< 1 second) or scheduled (15 min intervals)
   - Configurable auto-refresh interval

---

## Architecture

### Backend

#### API Routes (`backend/app/api/routes/ofo.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ofo/strategies` | GET | Get list of available strategies for OFO |
| `/api/ofo/calculate` | POST | Calculate top 3 combinations for selected strategies |

**Calculate Request Schema:**
```python
{
    "underlying": "NIFTY",           # NIFTY, BANKNIFTY, FINNIFTY
    "expiry": "2025-01-09",          # YYYY-MM-DD format
    "strategy_types": ["iron_condor", "short_strangle"],
    "strike_range": 10,              # ±5, ±10, ±15, ±20 strikes from ATM
    "lots": 1                        # 1-50
}
```

**Calculate Response Schema:**
```python
{
    "underlying": "NIFTY",
    "expiry": "2025-01-09",
    "spot_price": 24100.50,
    "atm_strike": 24100.0,
    "lot_size": 25,
    "calculated_at": "2025-01-02T10:30:00",
    "calculation_time_ms": 1250,
    "total_combinations_evaluated": 15420,
    "results": {
        "iron_condor": [
            {
                "strategy_type": "iron_condor",
                "strategy_name": "Iron Condor",
                "max_profit": 4500.0,
                "max_loss": -8000.0,
                "breakevens": [23850.0, 24350.0],
                "net_premium": 180.0,
                "risk_reward_ratio": 0.56,
                "legs": [
                    {
                        "expiry": "2025-01-09",
                        "contract_type": "CE",
                        "transaction_type": "SELL",
                        "strike": 24200.0,
                        "cmp": 150.50,
                        "lots": 1,
                        "qty": 25,
                        "instrument_token": 12345678,
                        "tradingsymbol": "NIFTY2510924200CE"
                    }
                    // ... more legs
                ]
            }
            // ... top 3 results
        ]
    }
}
```

#### Schemas (`backend/app/schemas/ofo.py`)

- `OFOCalculateRequest` - Request schema with validation
- `OFOLegResult` - Individual leg details
- `OFOStrategyResult` - Strategy combination result
- `OFOCalculateResponse` - Full response with metadata
- `OFO_AVAILABLE_STRATEGIES` - List of 9 supported strategies

#### Calculator Service (`backend/app/services/ofo_calculator.py`)

**Class:** `OFOCalculator` (singleton instance: `ofo_calculator`)

**Key Methods:**

| Method | Description |
|--------|-------------|
| `calculate_best_strategies()` | Main entry point - calculates top N for each strategy |
| `is_valid_option()` | Filters out invalid options (CMP=0/0.5/null, OI≤0, premium<1) |
| `get_valid_strikes()` | Gets strikes within range of ATM |
| `calculate_strategy_pnl()` | Calculates P/L metrics using PnLCalculator |

**Combination Generators (one per strategy):**
- `generate_iron_condor_combinations()` - 4 legs: Buy OTM PE, Sell PE, Sell CE, Buy OTM CE
- `generate_iron_butterfly_combinations()` - 4 legs: ATM straddle with wings
- `generate_short_straddle_combinations()` - 2 legs: Sell CE + PE at same strike
- `generate_short_strangle_combinations()` - 2 legs: Sell OTM CE + PE
- `generate_long_straddle_combinations()` - 2 legs: Buy CE + PE at same strike
- `generate_long_strangle_combinations()` - 2 legs: Buy OTM CE + PE
- `generate_bull_call_spread_combinations()` - 2 legs: Buy lower CE, sell higher CE
- `generate_bear_put_spread_combinations()` - 2 legs: Buy higher PE, sell lower PE
- `generate_butterfly_spread_combinations()` - 4 legs: Buy wings, sell 2x middle

**Performance Constants:**
- `MIN_PREMIUM = 1.0` - Minimum option premium filter
- `MAX_COMBINATIONS_PER_STRATEGY = 5000` - Limit to prevent timeout

---

### Frontend

#### View (`frontend/src/views/OFOView.vue`)

**Page Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ OFO - Options For Options    [NIFTY][BN][FN]    Spot | Lot | ms │
├─────────────────────────────────────────────────────────────────┤
│ Expiry [▼]  Strategies [▼]  Range [▼]  Lots [1]  [Calculate]    │
│                                         [Auto □ 15min]          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Iron Condor (3 results)                                         │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐                    │
│ │  #1 Gold   │ │  #2 Silver │ │  #3 Bronze │                    │
│ │  Max: ₹X   │ │  Max: ₹Y   │ │  Max: ₹Z   │                    │
│ │  [Table]   │ │  [Table]   │ │  [Table]   │                    │
│ │ [Builder]  │ │ [Builder]  │ │ [Builder]  │                    │
│ │  [Order]   │ │  [Order]   │ │  [Order]   │                    │
│ └────────────┘ └────────────┘ └────────────┘                    │
│                                                                 │
│ Short Strangle (3 results)                                      │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐                    │
│ │    ...     │ │    ...     │ │    ...     │                    │
│ └────────────┘ └────────────┘ └────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**data-testid Conventions:**
- `ofo-page` - Main page container
- `ofo-header` - Page header section
- `ofo-underlying-tabs` - Underlying tab group
- `ofo-underlying-{nifty|banknifty|finnifty}` - Individual tabs
- `ofo-spot-price` - Spot price display
- `ofo-lot-box` - Lot size display
- `ofo-calc-time` - Calculation time display
- `ofo-expiry-select` - Expiry dropdown
- `ofo-strategy-select` - Strategy multi-select
- `ofo-strike-range` - Strike range dropdown
- `ofo-lots-input` - Lots input field
- `ofo-calculate-btn` - Calculate button
- `ofo-auto-refresh` - Auto-refresh toggle
- `ofo-refresh-interval` - Refresh interval dropdown
- `ofo-loading` - Loading state
- `ofo-empty` - Empty state (no strategies selected)
- `ofo-error` - Error message
- `ofo-results` - Results section
- `ofo-group-{strategy_type}` - Strategy group container
- `ofo-card-{strategy_type}-{rank}` - Result card (rank: 1, 2, 3)
- `ofo-card-legs-{rank}` - Legs table in card

#### Store (`frontend/src/stores/ofo.js`)

**State:**
```javascript
{
    underlying: 'NIFTY',
    expiry: '',
    expiries: [],
    selectedStrategies: [],
    strikeRange: 10,
    lots: 1,
    results: {},           // strategy_type -> top 3 results
    spotPrice: 0,
    atmStrike: 0,
    lotSize: 25,
    calculationTimeMs: 0,
    totalCombinationsEvaluated: 0,
    lastCalculated: null,
    autoRefreshEnabled: false,
    autoRefreshInterval: 5, // minutes
    isLoading: false,
    error: null,
    availableStrategies: [...] // 9 strategies
}
```

**Actions:**
- `setUnderlying(ul)` - Switch underlying, fetch expiries
- `fetchExpiries()` - Load expiries from API
- `toggleStrategy(key)` - Toggle strategy selection
- `selectAllStrategies()` / `clearStrategies()` - Bulk selection
- `calculate()` - Call backend API, update results
- `startAutoRefresh()` / `stopAutoRefresh()` / `toggleAutoRefresh()`
- `setAutoRefreshInterval(minutes)` - Update refresh interval
- `openInStrategyBuilder(result)` - Navigate to Strategy Builder with legs

#### Components

**`frontend/src/components/ofo/StrategyMultiSelect.vue`**
- Multi-select dropdown for strategy types
- Select All / Clear All buttons
- Checkboxes for each strategy
- Badge showing selected count

**`frontend/src/components/ofo/OFOResultCard.vue`**
- Displays single strategy result
- Rank badge (Gold/Silver/Bronze for #1/#2/#3)
- Max Profit badge
- Legs table with columns: Expiry, Type, B/S, Strike, CMP, Lots, Qty
- Summary: Net Premium, Max Loss, R:R Ratio, Breakevens
- Action buttons: Open in Builder, Place Order

---

### Supported Strategies (9 total)

| Key | Name | Category | Legs |
|-----|------|----------|------|
| `iron_condor` | Iron Condor | Neutral | 4 |
| `iron_butterfly` | Iron Butterfly | Neutral | 4 |
| `short_straddle` | Short Straddle | Neutral | 2 |
| `short_strangle` | Short Strangle | Neutral | 2 |
| `long_straddle` | Long Straddle | Volatile | 2 |
| `long_strangle` | Long Strangle | Volatile | 2 |
| `bull_call_spread` | Bull Call Spread | Bullish | 2 |
| `bear_put_spread` | Bear Put Spread | Bearish | 2 |
| `butterfly_spread` | Butterfly Spread | Neutral | 4 |

---

## File Structure

```
backend/
├── app/
│   ├── api/routes/ofo.py           # API endpoints
│   ├── schemas/ofo.py              # Pydantic schemas
│   └── services/ofo_calculator.py  # Calculation logic

frontend/
├── src/
│   ├── views/OFOView.vue           # Main page
│   ├── stores/ofo.js               # Pinia store
│   └── components/ofo/
│       ├── StrategyMultiSelect.vue # Multi-select dropdown
│       └── OFOResultCard.vue       # Result card component

tests/e2e/
├── pages/OFOPage.js                # Page Object
└── specs/ofo/
    ├── ofo.happy.spec.js           # Happy path tests
    ├── ofo.edge.spec.js            # Edge case tests
    └── ofo.api.spec.js             # API validation tests
```

---

## Navigation Integration

**Route:** `/ofo`

**Router entry (`frontend/src/router/index.js`):**
```javascript
{
  path: '/ofo',
  name: 'ofo',
  component: () => import('../views/OFOView.vue'),
  meta: { requiresAuth: true }
}
```

**Header link (`frontend/src/components/layout/KiteHeader.vue`):**
- Added "OFO" to navigation items
- data-testid: `kite-header-nav-ofo`

---

## Key Implementation Details

### Option Filtering Logic

Options are excluded from combinations if:
1. `ltp` (CMP) is `null`, `0`, or `0.5`
2. `oi` (Open Interest) is `null` or `≤ 0`
3. `ltp < MIN_PREMIUM` (1.0)

### P/L Calculation

Uses existing `PnLCalculator` service with `mode="expiry"` to calculate:
- Max Profit
- Max Loss
- Breakeven points
- Net Premium (credit/debit)
- Risk:Reward ratio

### Performance Optimization

1. **Batch Quotes:** Fetches quotes in batches of 500 (Kite API limit)
2. **Combination Limit:** Max 5000 combinations per strategy type
3. **Strike Range:** User-selectable range (±5 to ±20 strikes from ATM)
4. **Calculation Time Tracking:** Returns `calculation_time_ms` in response

### Integration with Strategy Builder

`openInStrategyBuilder(result)` method:
1. Sets underlying and expiry in Strategy store
2. Clears existing legs
3. Adds each leg from OFO result using `addLegFromOFO()`
4. Returns route path `/strategy` for navigation

---

## Testing

### E2E Tests (`tests/e2e/specs/ofo/`)

**Happy Path (`ofo.happy.spec.js`):**
- Page displays correctly
- Kite header integration
- Underlying tabs work
- Strategy multi-select works
- Controls (expiry, strike range, lots) work
- Empty state displays when no strategies selected
- No horizontal overflow

**Edge Cases (`ofo.edge.spec.js`):**
- Error handling for API failures
- Loading states
- Invalid inputs
- Auto-refresh behavior

**API Tests (`ofo.api.spec.js`):**
- API response validation
- Error responses

### Page Object (`tests/e2e/pages/OFOPage.js`)

Key methods:
- `navigate()` - Go to /ofo
- `selectUnderlying(ul)` - Select underlying tab
- `openStrategyDropdown()` / `closeStrategyDropdown()`
- `getStrategyOption(key)` - Get strategy checkbox
- `setStrikeRange(value)` / `setLots(value)`
- `calculate()` - Click calculate button
- `assertPageVisible()` / `assertHeaderVisible()`
- `hasHorizontalOverflow()` - Check for overflow issues

---

## Future Enhancements (TODO)

1. **Place Order:** Implement basket order modal for direct order placement
2. **Caching:** Cache calculation results for same underlying/expiry
3. **Scheduled Updates:** Server-side scheduled calculations for heavy load
4. **More Strategies:** Add ratio spreads, calendar spreads, etc.
5. **Custom Filters:** Allow filtering by min profit, max loss, etc.

---

## Related Documentation

- [Strategy Builder](../features/strategy-builder/README.md)
- [Option Chain](../features/option-chain/README.md)
- [Trading Constants](../../CLAUDE.md#trading-constants-critical)

---

*Created: January 2026*
*Last Updated: January 2026*
