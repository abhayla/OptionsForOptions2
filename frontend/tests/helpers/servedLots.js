// What GET /api/settings serves for the three lot limits (REQ-167 AC-5): the registry defaults. A test's mocked API
// answers '/settings' with this so a screen that waits for the served caps has them; the browser itself types none.
export const SERVED_LOT_LIMITS = Object.freeze({ 'limits.max_lots': '10000', 'limits.multiplier_max': '50', 'limits.lot_choices': '10',
  'limits.chain_strikes_each_side': '15', 'other.undo_one_leg_seconds': '8' })

export const settingsData = (over = {}) => ({
  groups: [{ name: 'Limits', settings: Object.entries({ ...SERVED_LOT_LIMITS, ...over }).map(([key, value]) => ({ key, value })) }],
  charges: null,
})
