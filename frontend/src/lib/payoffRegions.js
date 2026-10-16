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
