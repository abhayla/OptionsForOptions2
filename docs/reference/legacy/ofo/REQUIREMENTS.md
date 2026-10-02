<!-- Copied from abhayla/algochanakya@bf9faf7:docs/features/ofo/REQUIREMENTS.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# OFO Requirements

## API Requirements

- [x] POST /api/ofo/calculate - Calculate strategy combinations
- [x] GET /api/ofo/strategies - Get available strategy types
- [x] Support for NIFTY, BANKNIFTY, FINNIFTY underlyings
- [x] Support for all available expiries
- [x] Configurable strike range (±5 to ±20)
- [x] Configurable lot multiplier (1-10)

## Strategy Requirements

- [x] Iron Condor calculation
- [x] Iron Butterfly calculation
- [x] Short Straddle calculation
- [x] Short Strangle calculation
- [x] Long Straddle calculation
- [x] Long Strangle calculation
- [x] Bull Call Spread calculation
- [x] Bear Put Spread calculation
- [x] Butterfly Spread calculation

## Calculation Requirements

- [x] Max profit calculation using PnLCalculator
- [x] Max loss calculation
- [x] Breakeven calculation
- [x] Net premium calculation
- [x] Risk-reward ratio calculation
- [x] Sort by max profit (descending)
- [x] Deduplicate identical P/L profiles
- [x] Return top 3 unique combinations per strategy

## UI Requirements

- [x] Underlying tabs (NIFTY, BANKNIFTY, FINNIFTY)
- [x] Spot price display
- [x] Expiry selector dropdown
- [x] Strategy multi-select dropdown
- [x] Select all / Clear all buttons
- [x] Strike range selector
- [x] Lots input field
- [x] Calculate button
- [x] Auto-refresh toggle with interval selector
- [x] Calculation time display
- [x] Last calculated timestamp
- [x] Strategy group headers with result count
- [x] Result cards with strategy details
- [x] Open in Builder button
- [x] Place Order button
- [x] Loading state
- [x] Empty state when no strategies selected
- [x] Error state handling

## Data Requirements

- [x] Live option chain data from WebSocket
- [x] Instrument token mapping
- [x] Lot size from trading constants

---
Last updated: 2026-01-02
