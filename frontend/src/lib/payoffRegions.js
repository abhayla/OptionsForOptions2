// How the ONE payoff line is coloured (GC-BM F-8; issue 297 item 4; ADR-072 loss regions). Text only: the sign is read
// from the API's own string, no number is computed here (ADR-008). A segment between two loss points is red, between
// two profit points green, a run at 0.00 on neither (issue 297 item 4: the 0.00 plateau is not on the Loss line).
// F-8 replaced the two-line split (payoffRegions, one line per region with nulls elsewhere), which broke the line
// wherever the P&L changed sign between two sent points.
const isLoss = (pnl) => String(pnl).trim().startsWith('-')
const isProfit = (pnl) => /^\+?(?=.*[1-9])\d+(\.\d*)?$/.test(String(pnl).trim())

/** GC-BM F-8: each sent point's sign, read from its own text: 'loss', 'profit' or '' (zero). */
export function pointSigns(points) {
  return points.map((p) => (isLoss(p.pnl) && /[1-9]/.test(String(p.pnl)) ? 'loss' : isProfit(p.pnl) ? 'profit' : ''))
}

/**
 * GC-BM F-8/F-11: the chart.js segment colour of the ONE payoff line (see PayoffChart.vue). The pixel geometry of the
 * zero-crossing gradient is drawing work and lives in PayoffChart.vue (ADR-008 named drawing exception); it is GIVEN
 * here as crossing(chart), which returns a gradient or null (null = grey, nothing drawn wrongly).
 */
export function segmentColour(signs, colours, crossing) {
  return (c) => {
    const a = signs[c.p0DataIndex]
    const b = signs[c.p1DataIndex]
    if (!a && !b) return colours.flat
    if (a !== 'loss' && b !== 'loss') return colours.profit
    if (a !== 'profit' && b !== 'profit') return colours.loss
    return (typeof crossing === 'function' && crossing(c.chart)) || colours.flat
  }
}
