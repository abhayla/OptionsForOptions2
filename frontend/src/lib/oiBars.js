// GC-UI 6c D-C26 (S-032): the strike drawer's OI bars. A bar's length is the ratio of two server OI counts in one reply,
// used for DRAWING only and never printed (ADR-008: OI counts, not money; the bar's label stays the server's L / Cr text).
// A missing, empty or non-numeric OI draws no bar, never a zero-width bar (REQ-083 AC-6).

const oiCount = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v))

/** The largest OI on either side of any row: the bars' scale (0 when no row has one). */
export function oiBarMax(rows) {
  return Math.max(0, ...(rows ?? []).flatMap((r) => ['ce', 'pe'].map((s) => oiCount(r?.[s]?.oi) ?? 0)))
}

/** One side's bar width as CSS text ("62%"), or null when there is nothing to draw. */
export function oiBarWidth(oi, max) {
  const n = oiCount(oi)
  return n === null || n <= 0 || !(max > 0) ? null : `${Math.round((n / max) * 100)}%`
}
