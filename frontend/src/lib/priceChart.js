// GC-UI step 5 (D-B40, D-B41; REQ-091): text helpers for the Strategy Chart tab. Every figure shown is a string the
// server sent (`display`); nothing is computed here (ADR-008). The x axis is the minute INDEX of the reply's points, so
// closed hours and overnight gaps take no space; the tick text is read from that point's own `t`.
import { istTime } from '@/lib/displayFormat'

export const LEFT_AXIS_TITLE = 'Strategy Price'
export const INVERT_LABEL = 'Invert Price'
export const NOT_AVAILABLE = 'The strategy chart is not available.'
export const SWITCHED_OFF = 'The strategy chart is switched off.'
export const UNSAVED = 'Save the strategy to see its price chart.'
export const LOADING = 'Loading the strategy chart...'

const SHAPE = /^(\d{1,2}) (\w{3}) \d{4}, (\d{2}):(\d{2}):\d{2} IST$/

/** 'as of 28 Oct, 15:39 IST' from the reply's ISO as_of (India time, from the server instant, never the browser clock); null when unreadable. */
export function asOfText(iso) {
  const m = SHAPE.exec(istTime(iso))
  return m ? `as of ${m[1]} ${m[2]}, ${m[3]}:${m[4]} IST` : null
}

/** '14 Oct 09:15' for one point's t (an axis tick or tooltip title); '' when unreadable. */
export function pointText(iso) {
  const m = SHAPE.exec(istTime(iso))
  return m ? `${m[1]} ${m[2]} ${m[3]}:${m[4]}` : ''
}

/** The two chart.js data arrays: x = the point's index, y = the reply's value string as sent (null = a gap, never joined). */
export function seriesOf(points) {
  const list = Array.isArray(points) ? points : []
  return {
    strategy: list.map((p, i) => ({ x: i, y: p?.strategy?.value ?? null })),
    future: list.map((p, i) => ({ x: i, y: p?.future?.value ?? null })),
  }
}

/** The text that replaces the chart: the reply's reason, else the plain sentence; null when the reply has a chart to draw. */
export function reasonOf(reply) {
  if (!reply || typeof reply !== 'object') return NOT_AVAILABLE
  if (reply.available === true && Array.isArray(reply.points) && reply.points.length) return null
  return typeof reply.reason === 'string' && reply.reason.trim() ? reply.reason : NOT_AVAILABLE
}
