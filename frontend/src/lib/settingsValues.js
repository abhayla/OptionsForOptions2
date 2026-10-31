// REQ-167 AC-5 / AC-7 (ADR-222): the browser keeps no copy of a limit, a step or a wait. Every number it needs is the value
// in force that GET /api/settings serves, read through the ONE store in stores/settingsValues.js. These are its pure parts.

/** `{key: decimal string}` from the GET /api/settings answer (every group's settings, the value in force). */
export function settingsMap(data) {
  const out = {}
  for (const group of data?.groups ?? []) {
    for (const s of group.settings ?? []) out[s.key] = s.value
  }
  return out
}

/** A whole number from a served decimal string, or null: strict parse, never float maths ("15" yes; "1.5", "1e1", "" no). */
export function strictInt(text) {
  if (typeof text !== 'string' || !/^(0|[1-9][0-9]{0,8})$/.test(text)) return null
  return Number(text)
}

/** The strike-range picker's options: a third, two thirds and all of the served limit, each once, never above it. */
export function strikeRangesOf(max) {
  return [...new Set([1, 2, 3].map((k) => Math.max(1, Math.round((max * k) / 3))))]
}
