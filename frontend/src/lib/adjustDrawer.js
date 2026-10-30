// Review-adjustment drawer (GC-ADJ1 step 3; REQ-046 AC-1..AC-3, REQ-045 AC-5; ADR-214 (1), ADR-003, ADR-008).
// Pure helpers. Display only: every figure is a text the tracking reply sent, "-" when absent. Nothing is computed here.
// The generic approaches carry NO figure (REQ-045 AC-5): the numbers appear only in the compare, after a pick. The names are
// the server's own catalogue names (backend ADJUSTMENT_APPROACH_LABEL_TEXT, same ids); the one-line explanations follow the
// behaviour documented in backend/ofo/adjustment/approaches.py. Decision-support wording, no ranking word (ADR-003).
import { NO_CHANGE_ID } from '@/lib/adjustCompare'

export const REVIEW_BUTTON_TEXT = 'Review adjustment'
export const PICK_NOTE = 'Pick any to compare. No change is always included.'
export const LAPSED_TEXT = 'The condition no longer holds. You can still compare the approaches.'
export const NOT_IRON_CONDOR_NOTE = 'Approaches for this kind of strategy come later. Only No change and Exit are offered now.'
export const NONE = '-'

const EXIT_ID = 'A-31'
export const APPROACHES = Object.freeze([
  { id: NO_CHANGE_ID, name: 'No change', about: 'Keep every leg as it is. This is the baseline the others are compared with.', condorOnly: false },
  { id: 'A-01', name: 'Roll the untested spread toward spot', about: 'Move the side spot is moving away from closer to spot, keeping its width.', condorOnly: true },
  { id: 'A-05', name: 'Roll the tested spread out (same width)', about: 'Move the side spot is pressing on further out, keeping its width.', condorOnly: true },
  { id: 'A-29', name: 'Reduce the tested side', about: 'Close part of the side spot is pressing on and keep the rest.', condorOnly: true },
  { id: 'A-28', name: 'Close the tested spread', about: 'Close the whole side spot is pressing on and keep the other side.', condorOnly: true },
  { id: 'A-11', name: 'Re-centre both shorts at the money', about: 'Move both short strikes to the strike nearest spot, keeping each wing\'s distance.', condorOnly: true },
  { id: EXIT_ID, name: 'Exit the whole strategy', about: 'Close every open leg.', condorOnly: false },
])

const isOpen = (l) => l && (l.exited_at === null || l.exited_at === undefined) && l.pnl_kind !== 'booked'

/** True for one short CE below a long CE and one short PE above a long PE, all open legs on one expiry (the shape the server
 *  builds the full approach set for). Anything else is false: the drawer then offers only the approaches that fit any strategy. */
export function isIronCondor(legs) {
  const open = (Array.isArray(legs) ? legs : []).filter(isOpen)
  if (open.length !== 4 || new Set(open.map((l) => l.expiry)).size !== 1) return false
  const pick = (type, action) => open.filter((l) => l.instrument === type && l.action === action)
  const [cs, cl, ps, pl] = [pick('CE', 'SELL'), pick('CE', 'BUY'), pick('PE', 'SELL'), pick('PE', 'BUY')]
  if ([cs, cl, ps, pl].some((x) => x.length !== 1)) return false
  const k = (l) => Number(l[0].strike) // compared only, never summed (ADR-008)
  return k(cl) > k(cs) && k(pl) < k(ps)
}

export const approachesFor = (legs) => (isIronCondor(legs) ? APPROACHES : APPROACHES.filter((a) => !a.condorOnly))

/** REQ-046 AC-2 Layer 2, from the tracking reply only. A value the card does not have reads "-", never a guess. */
export function stateRows(body) {
  const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : NONE)
  const open = Array.isArray(body?.legs) ? body.legs.filter(isOpen).length : null
  return [
    { id: 'pnl', label: 'Paper P&L (not real)', value: text(body?.paper_pnl_text) },
    { id: 'booked', label: 'Booked', value: text(body?.booked_text) },
    { id: 'unbooked', label: 'Not yet booked', value: text(body?.unbooked_text) },
    { id: 'index', label: 'Index', value: text(body?.index?.level) },
    { id: 'breakevens', label: 'Breakevens', value: Array.isArray(body?.breakevens) && body.breakevens.length ? body.breakevens.join(', ') : NONE },
    { id: 'open_legs', label: 'Open legs', value: open === null ? NONE : String(open) },
    { id: 'delta', label: 'Net delta', value: NONE },
    { id: 'theta', label: 'Theta per day', value: NONE },
    { id: 'days_left', label: 'Days left', value: NONE },
  ]
}

/** The compare address for a strategy and the ids picked in the drawer; No change is always among them. */
export function compareUrl(strategyId, ids) {
  const picks = [...new Set([NO_CHANGE_ID, ...ids])]
  return `/strategy/builder?adjust=${encodeURIComponent(String(strategyId))}&pick=${picks.map(encodeURIComponent).join(',')}`
}

/** The ids in a `pick` query value; an unknown or empty value is no pick (the compare then shows everything). */
export function picksFromQuery(value) {
  const raw = Array.isArray(value) ? value[0] : value
  return typeof raw === 'string' && raw !== '' ? [...new Set(raw.split(',').filter((x) => /^A-\d{2}$/.test(x)))] : []
}
