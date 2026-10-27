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

/** GC-BM F-8: the chart.js segment colour of the ONE payoff line (see PayoffChart.vue). */
export function segmentColour(signs, colours) {
  return (c) => {
    const a = signs[c.p0DataIndex]
    const b = signs[c.p1DataIndex]
    if (!a && !b) return colours.flat
    if (a !== 'loss' && b !== 'loss') return colours.profit
    if (a !== 'profit' && b !== 'profit') return colours.loss
    const chart = c.chart
    const area = chart?.chartArea
    const y0 = chart?.scales?.y?.getPixelForValue?.(0)
    if (!chart?.ctx?.createLinearGradient || !area || !(area.bottom > area.top) || !Number.isFinite(y0)) return colours.flat
    const at = Math.max(0, Math.min(1, (y0 - area.top) / (area.bottom - area.top)))
    const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom)
    g.addColorStop(0, colours.profit)
    g.addColorStop(at, colours.profit)
    g.addColorStop(at, colours.loss)
    g.addColorStop(1, colours.loss)
    return g
  }
}
