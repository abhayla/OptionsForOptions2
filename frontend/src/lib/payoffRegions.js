// Which payoff points each chart line covers (issue 297 item 4; ADR-072 loss regions). Text only: the sign is read from
// the API's own string, no number is computed here (ADR-008).
// Loss covers the points below zero, plus a zero point that touches one (so the line closes at the break-even);
// Profit covers the points above zero, plus a zero point that touches one. A zero point between two zero points,
// or a zero between a loss and a profit, belongs to no flat stretch: it is drawn only by the line it touches.
const isLoss = (pnl) => String(pnl).trim().startsWith('-')
const isProfit = (pnl) => /^\+?(?=.*[1-9])\d+(\.\d*)?$/.test(String(pnl).trim())

export function payoffRegions(points) {
  const touches = (i, test) => [i - 1, i + 1].some((j) => j >= 0 && j < points.length && test(points[j].pnl))
  const cover = (test) => points.map((p, i) => test(p.pnl) || (!isLoss(p.pnl) && !isProfit(p.pnl) && touches(i, test)))
  return { loss: cover(isLoss), profit: cover(isProfit) }
}

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
