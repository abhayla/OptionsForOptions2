// W-124 (REQ-087 AC-1..AC-5, REQ-029 AC-3/AC-9, REQ-031 AC-1/AC-2; ADR-008): what the Option Chain draws per UX level.
// Pure helpers over the server's answer: every value is a string the SERVER computed (per lot, intrinsic, time value,
// breakeven %, Greeks, in-the-money); nothing here does money maths. Copy from: none - no algochanakya row.

export const STRIKE_CHOICES = Object.freeze([10, 20, 30, 40]) // REQ-087 AC-3
export const DEFAULT_STRIKES = 10
export const UX_LEVELS = Object.freeze(['guided', 'standard', 'advanced'])
export const SETTING_PATH = '/user-settings/chain-strikes' // relative to the api base (/api)
export const PREVIEW_PATH = '/market/chain/preview'
export const UNLIMITED = 'Unlimited'

const BASE = [['ltp', 'LTP'], ['change', 'Change'], ['oi', 'OI'], ['volume', 'Volume']]
const GUIDED = [['ltp', 'LTP'], ['oi', 'OI']]
const ADVANCED_EXTRA = [['bid', 'Bid'], ['ask', 'Ask'], ['oi_change', 'OI Change'], ['intrinsic', 'Intrinsic (vs spot)'],
  ['time_value', 'Time value'], ['breakeven_pct', 'Breakeven %'], ['delta', 'Delta'], ['gamma', 'Gamma'],
  ['theta', 'Theta'], ['vega', 'Vega']]

/** REQ-029 AC-9: Guided keeps the chain simple, Standard is the default set, Advanced adds bid / ask, OI change, the
 *  REQ-087 AC-4 columns and the Greeks (REQ-029 AC-3). Unknown level: the Standard set (never a wider one). */
export function fieldsFor(level, perLot, lotSize) {
  const base = level === 'guided' ? GUIDED : level === 'advanced' ? [...BASE, ...ADVANCED_EXTRA] : BASE
  return base.map(([key, label]) => (key === 'ltp' && perLot
    ? ['per_lot', lotSize ? `LTP per lot (x${lotSize})` : 'LTP per lot'] // REQ-087 AC-1: the lot size in the heading
    : [key, label]))
}

/** The lot size the server sent on the first cell that has one (the instrument file's, REQ-087 AC-1), else null. */
export function lotSizeOf(view) {
  const cell = (view?.rows ?? []).flatMap((r) => [r.ce, r.pe]).find((c) => c && Number.isInteger(c.lot_size))
  return cell ? cell.lot_size : null
}

/** The preview's one-line words (REQ-031 AC-1): Unlimited is a word from the server's flag, never a number. */
export function previewLines(p) {
  if (!p || p.state !== 'COMPUTED') return null
  const money = (v, unlimited) => (unlimited ? UNLIMITED : (typeof v === 'string' ? v : '-'))
  return {
    net: typeof p.net_premium === 'string' ? `${p.net_premium} ${p.net_side ?? ''}`.trim() : '-',
    maxProfit: money(p.max_profit, p.max_profit_unlimited),
    maxLoss: money(p.max_loss, p.max_loss_unlimited),
    breakevens: Array.isArray(p.breakevens) && p.breakevens.length ? p.breakevens.join(', ') : '-',
  }
}

/** The legs the preview asks about: only those with an action and a captured price (a leg without one cannot be priced). */
export function previewLegs(entries) {
  return entries
    .filter((e) => e.action && e.permitted === true && typeof e.planned_entry === 'string' && typeof e.captured_at === 'string')
    .map((e) => ({ instrument_id: e.instrument_id, action: e.action, lots: e.lots, planned_entry: e.planned_entry, captured_at: e.captured_at }))
}
