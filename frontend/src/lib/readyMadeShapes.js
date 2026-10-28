// GC-UI D-C04: one static payoff-SHAPE drawing per shape family (hand-drawn points in a 48 x 28 box, zero line at y = 14,
// smaller y = profit). Artwork only: nothing here is computed from prices or legs, and no image is copied from anywhere.
// A template picks its shape by its own catalogue `id` (the field every template already has); an id not listed here
// gets no icon (the card keeps its name), never an error.

export const ZERO_Y = 14
export const SHAPE_POINTS = {
  longCall: [[0, 18], [22, 18], [46, 2]],
  longPut: [[2, 2], [26, 18], [48, 18]],
  shortCall: [[0, 10], [22, 10], [46, 26]],
  shortPut: [[2, 26], [26, 10], [48, 10]],
  bullSpread: [[0, 20], [16, 20], [32, 6], [48, 6]],
  bearSpread: [[0, 6], [16, 6], [32, 20], [48, 20]],
  longFuture: [[0, 26], [48, 2]],
  shortFuture: [[0, 2], [48, 26]],
  shortStraddle: [[0, 24], [24, 6], [48, 24]],
  longStraddle: [[0, 4], [24, 22], [48, 4]],
  shortStrangle: [[0, 24], [14, 8], [34, 8], [48, 24]],
  longStrangle: [[0, 4], [14, 20], [34, 20], [48, 4]],
  shortCondor: [[0, 22], [12, 22], [18, 8], [30, 8], [36, 22], [48, 22]],
  longCondor: [[0, 6], [12, 6], [18, 20], [30, 20], [36, 6], [48, 6]],
  shortButterfly: [[0, 20], [14, 20], [24, 6], [34, 20], [48, 20]],
  longButterfly: [[0, 8], [14, 8], [24, 22], [34, 8], [48, 8]],
  callBackSpread: [[0, 12], [16, 12], [24, 20], [48, 0]],
  putBackSpread: [[0, 0], [24, 20], [32, 12], [48, 12]],
  callRatioSpread: [[0, 18], [14, 18], [26, 8], [48, 26]],
  putRatioSpread: [[0, 26], [22, 8], [34, 18], [48, 18]],
  jadeLizard: [[0, 26], [14, 10], [48, 10]],
  reverseJadeLizard: [[0, 10], [34, 10], [48, 26]],
  calendar: [[0, 18], [24, 8], [48, 18]],
  rangeForward: [[0, 26], [14, 14], [34, 14], [48, 2]],
  riskReversal: [[0, 2], [14, 14], [34, 14], [48, 26]],
  batman: [[0, 22], [8, 22], [14, 8], [20, 8], [24, 14], [28, 8], [34, 8], [40, 22], [48, 22]],
  strip: [[0, 0], [24, 20], [48, 8]],
  strap: [[0, 8], [24, 20], [48, 0]],
  coveredCall: [[0, 26], [30, 10], [48, 10]],
}

export const SHAPE_OF_ID = {
  buy_call: 'longCall', sell_put_atm: 'shortPut', bull_call_spread: 'bullSpread', bull_put_spread: 'bullSpread',
  ratio_backspread_call: 'callBackSpread', calendar_spread: 'calendar', bull_condor: 'shortCondor', butterfly_spread: 'shortButterfly',
  range_forward: 'rangeForward', synthetic_long: 'longFuture', buy_future: 'longFuture',
  buy_put: 'longPut', sell_call: 'shortCall', bear_call_spread: 'bearSpread', bear_put_spread: 'bearSpread',
  ratio_backspread_put: 'putBackSpread', long_calendar_puts: 'calendar', bear_condor: 'shortCondor', bear_butterfly: 'shortButterfly',
  risk_reversal: 'riskReversal', synthetic_short: 'shortFuture', sell_future: 'shortFuture',
  short_straddle: 'shortStraddle', iron_butterfly: 'shortButterfly', short_strangle: 'shortStrangle', iron_condor: 'shortCondor',
  batman: 'batman', double_plateau: 'batman', jade_lizard: 'jadeLizard', reverse_jade_lizard: 'reverseJadeLizard',
  call_ratio_spread: 'callRatioSpread', put_ratio_spread: 'putRatioSpread', long_straddle: 'longStraddle',
  long_iron_butterfly: 'longButterfly', long_strangle: 'longStrangle', reverse_iron_condor: 'longCondor', strip: 'strip', strap: 'strap',
  covered_call: 'coveredCall', cash_secured_put: 'shortPut', diagonal_spread: 'calendar',
}

/** The drawing points for a template id, or null when the id has no listed shape (the card then shows no icon). */
export function shapePoints(id) {
  const key = SHAPE_OF_ID[id]
  return key ? SHAPE_POINTS[key] : null
}

export const pointsAttr = (pts) => pts.map(([x, y]) => `${x},${y}`).join(' ')
