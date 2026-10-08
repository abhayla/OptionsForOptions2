// Pixel geometry for the payoff chart ONLY (W-064). The one place a payoff string is turned into a number, and only to
// place a point on the screen: nothing computed here is ever displayed. Axis labels and the table show the API's own
// strings. The grep test (tests/no-client-maths.test.js) allows this file and no other.

/** Plot positions (0..width, 0..height) for payoff points, in the order the API sent them. */
export function plotPoints(points, width, height, pad) {
  if (!points.length) return []
  const xs = points.map((p) => Number(p.level))
  const ys = points.map((p) => Number(p.pnl))
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const [y0, y1] = [Math.min(...ys, 0), Math.max(...ys, 0)]
  const sx = (v) => pad + ((v - x0) / (x1 - x0 || 1)) * (width - 2 * pad)
  const sy = (v) => height - pad - ((v - y0) / (y1 - y0 || 1)) * (height - 2 * pad)
  return points.map((p, i) => ({ x: sx(xs[i]), y: sy(ys[i]), level: p.level, pnl: p.pnl }))
}

/** The y position of the zero line and the x position of a level, on the same scale as plotPoints. */
export function plotAxes(points, currentLevel, width, height, pad) {
  const xs = points.map((p) => Number(p.level))
  const ys = points.map((p) => Number(p.pnl))
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const [y0, y1] = [Math.min(...ys, 0), Math.max(...ys, 0)]
  const zeroY = height - pad - ((0 - y0) / (y1 - y0 || 1)) * (height - 2 * pad)
  const cur = currentLevel == null ? null : pad + ((Number(currentLevel) - x0) / (x1 - x0 || 1)) * (width - 2 * pad)
  return { zeroY, currentX: cur }
}
