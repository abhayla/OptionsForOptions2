<!-- Copied from abhayla/algochanakya@bf9faf7:docs/features/ofo/README.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# OFO - Options For Options

Options strategy finder and optimizer that calculates and ranks strategy combinations based on max profit, risk-reward ratio, and other metrics.

## Overview

OFO (Options For Options) is a powerful tool that helps traders find optimal option strategy combinations. It evaluates multiple strategy types simultaneously and ranks them by profitability.

## Supported Strategies

| Strategy | Type | Description |
|----------|------|-------------|
| Iron Condor | Defined Risk | 4-leg strategy selling OTM call & put spreads |
| Iron Butterfly | Defined Risk | 4-leg strategy with ATM short options |
| Short Straddle | Undefined Risk | Sell ATM CE + PE |
| Short Strangle | Undefined Risk | Sell OTM CE + PE |
| Long Straddle | Defined Risk | Buy ATM CE + PE |
| Long Strangle | Defined Risk | Buy OTM CE + PE |
| Bull Call Spread | Defined Risk | Buy lower CE, sell higher CE |
| Bear Put Spread | Defined Risk | Buy higher PE, sell lower PE |
| Butterfly Spread | Defined Risk | 3-strike butterfly |

## Features

- **Multi-strategy calculation**: Select multiple strategies to compare
- **Underlying selection**: NIFTY, BANKNIFTY, FINNIFTY
- **Expiry selection**: Choose from available expiries
- **Strike range**: Configure ±5 to ±20 strikes from ATM
- **Lot multiplier**: Calculate for 1-10 lots
- **Auto-refresh**: Automatic recalculation at configurable intervals
- **Unique results**: Deduplication ensures meaningfully different combinations

## Architecture

### Backend

- **API Route**: `backend/app/api/routes/ofo.py`
- **Calculator Service**: `backend/app/services/ofo_calculator.py`
- **Schemas**: `backend/app/schemas/ofo.py`

### Frontend

- **View**: `frontend/src/views/OFOView.vue`
- **Store**: `frontend/src/stores/ofo.js`
- **Components**:
  - `StrategyMultiSelect.vue` - Multi-select dropdown for strategies
  - `ResultCard.vue` - Individual strategy result card
  - `StrategyGroup.vue` - Group of results for a strategy type

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ofo/calculate` | Calculate strategy combinations |
| GET | `/api/ofo/strategies` | Get available strategy types |

## Calculation Logic

1. **Generate combinations**: For each selected strategy type, generate all valid strike combinations within the specified range
2. **Calculate P/L**: Use PnLCalculator to compute max profit, max loss, breakevens for each combination
3. **Sort by profitability**: Rank combinations by max profit (descending)
4. **Deduplicate**: Filter out combinations with identical P/L profiles
5. **Return top N**: Return top 3 unique combinations per strategy

## Related Features

- [Option Chain](../option-chain/) - Source of strike and price data
- [Strategy Builder](../strategy-builder/) - Open selected strategies for detailed analysis
