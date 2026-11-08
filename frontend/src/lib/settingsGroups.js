// Contract "Your adjustment settings" step 4: the Adjustment settings screen's groups, in the approved mockup's order
// (each group answers one trader question). Which group a setting sits in is decided here by its registry key; a key
// this map does not know goes to "Other settings" so the server's list is never silently cut. No value, unit or word
// of a setting is written here: those are the server's.

export const GROUPS = [
  { id: 'g-land', title: 'Where a moved leg lands' },
  { id: 'g-size', title: 'How much to adjust' },
  { id: 'g-tell', title: 'When to tell me' },
  { id: 'g-loud', title: 'Alert pace and sound' },
  { id: 'g-exit', title: 'Exits and targets' },
  { id: 'g-plan', title: 'Plan limits' },
  { id: 'g-pb', title: 'Playbook triggers' },
  { id: 'g-order', title: 'Order defaults' },
  { id: 'g-disp', title: 'Display only' },
  { id: 'g-other', title: 'Other settings' },
  { id: 'g-admin', title: 'Set by the admin only' },
]

/** Open when the screen first shows (the mockup: where a moved leg lands, and exits). */
export const OPEN_BY_DEFAULT = ['g-land', 'g-exit']

const BY_KEY = {
  'adjustments.short_delta_weekly': 'g-land',
  'adjustments.short_delta_monthly': 'g-land',
  'adjustments.roll_points_nifty': 'g-land',
  'adjustments.roll_points_sensex': 'g-land',
  'adjustments.shift_strikes': 'g-land',
  'adjustments.iron_fly_min_days': 'g-land',
  'adjustments.reduce_divisor': 'g-size',
  'adjustments.partial_close_percent': 'g-size',
  'adjustments.untested_decay_percent': 'g-size',
  'adjustments.near_level_percent': 'g-tell',
  'adjustments.gap_at_open_until': 'g-tell',
  'adjustments.compare_range_percent': 'g-disp',
  'adjustments.compare_steps': 'g-disp',
  'adjustments.compare_move_small': 'g-disp',
  'adjustments.compare_move_large': 'g-disp',
}

/** The server's source codes (backend ofo/settings/layers.py: strategy / user / default). "yours" is the older preferences word. */
export const isYours = (source) => source === 'user' || source === 'yours'

export const ALERT_KEY = /^alerts\.([a-z_]+)\./

export function groupOf(key) {
  if (ALERT_KEY.test(key)) return 'g-loud'
  if (key.startsWith('orders.')) return 'g-other' // two-layer (user > admin default); the approved "Other settings" group
  return BY_KEY[key] ?? 'g-other'
}

/** The filter chips; each one's test on a preference. Pressed chips combine with OR (any pressed chip matches). */
export const CHIPS = [
  { id: 'nifty', label: 'NIFTY', test: (p) => /nifty/i.test(`${p.key} ${p.label}`) },
  { id: 'sensex', label: 'SENSEX', test: (p) => /sensex/i.test(`${p.key} ${p.label}`) },
  { id: 'weekly', label: 'Weekly', test: (p) => /weekly/i.test(`${p.key} ${p.label}`) },
  { id: 'monthly', label: 'Monthly', test: (p) => /monthly/i.test(`${p.key} ${p.label}`) },
  { id: 'delta', label: 'Delta-based', test: (p) => /delta/i.test(`${p.key} ${p.label}`) },
  { id: 'changed', label: 'Changed by me', test: (p) => isYours(p.source) },
]

/** True when the preference passes the search text and the pressed chips. */
export function matches(p, search, pressed) {
  const q = String(search || '').trim().toLowerCase()
  if (q && !`${p.label} ${p.what_it_changes ?? ''} ${p.key}`.toLowerCase().includes(q)) return false
  const on = CHIPS.filter((c) => pressed[c.id])
  return !on.length || on.some((c) => c.test(p))
}

/** The source tag's words (ADR-245): the server's source, or "source unavailable" when it sent none it names. */
export function sourceWord(source) {
  if (isYours(source)) return 'Yours'
  if (source === 'default') return 'Default'
  if (source === 'strategy') return 'This strategy'
  return 'source unavailable'
}
