<!-- Copied from abhayla/algochanakya@bf9faf7:docs/plans/cmp-fallback.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# CMP Fallback for Entry Prices & Position Status

## Requirements Summary

1. **CMP as Entry Fallback**: When `entry_price` is missing, use live CMP for P/L calculation
   - Entry field in UI stays blank (do NOT auto-fill)
   - P/L grid calculation uses CMP as entry price
   - Exit P/L column uses CMP as entry price
2. **Visual Indicator**: Show tooltip/hint when CMP is used instead of real entry
3. **Position Status**:
   - Position is "Open" when `exit_price` is blank
   - Position becomes "Closed" when `exit_price` is filled
   - Status change updates database

---

## Implementation Plan

### Step 1: Modify `calculatePnL()` to use CMP fallback

**File:** `frontend/src/stores/strategy.js`

- Remove `entry_price` from validation (only require `strike_price`, `expiry_date`, and `instrument_token`)
- Before sending to backend, substitute CMP for missing entry_price

### Step 2: Track CMP usage for UI indicator

**File:** `frontend/src/stores/strategy.js`

Add helper function:
```javascript
function isLegUsingCMPEntry(leg) {
  return !leg.entry_price && getLegCMP(leg) != null
}
```

### Step 3: Add tooltip/hint in Entry column

**File:** `frontend/src/views/StrategyBuilderView.vue`

Add blue badge with tooltip (?) next to Entry field when CMP is being used

### Step 4: Update `getLegPnL()` to use CMP fallback

**File:** `frontend/src/stores/strategy.js`

Use entry_price if available, otherwise use CMP as entry for Exit P/L calculation

### Step 5: Implement position status logic

**File:** `frontend/src/stores/strategy.js`

- Position is "open" when exit_price is blank
- Position becomes "closed" when exit_price is filled
- Auto-update position_status in `updateLeg()` when exit_price changes

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/stores/strategy.js` | CMP fallback in `calculatePnL()`, `getLegPnL()`, position status helpers, `isLegUsingCMPEntry()` |
| `frontend/src/views/StrategyBuilderView.vue` | Tooltip indicator for CMP usage in Entry column |

---

## Testing Checklist

1. Load "Abhay" strategy (no entry prices) → P/L grid should calculate using CMP
2. Entry fields remain blank, but calculations appear
3. Blue indicator appears next to blank Entry fields
4. Hover tooltip shows "Using CMP as entry price"
5. Fill exit_price → position status changes to "closed"
6. Save and reload → position_status persists
