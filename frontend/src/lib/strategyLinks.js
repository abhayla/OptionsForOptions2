// S-18 / S-14: one place that builds the router targets that carry a strategy id (a link without it opens an empty builder).
const positiveId = (id) => {
  const s = typeof id === 'number' ? String(id) : id
  return typeof s === 'string' && /^[1-9]\d{0,14}$/.test(s) ? s : null // up to 15 digits: always a safe integer, no conversion
}

/** The Strategy Builder opened on strategy `id`; null for anything but a positive whole number (the caller shows no link). */
export function builderLinkOf(id) {
  const s = positiveId(id)
  return s === null ? null : { path: '/strategy/builder', query: { strategy: s } }
}

/** The Paper tab of Current positions on strategy `id` (same shape as PaperStrategies.vue's compact list); null as above. */
export function paperStopsLinkOf(id) {
  const s = positiveId(id)
  return s === null ? null : { path: '/positions/current-positions', query: { tab: 'paper', strategy: s } }
}
