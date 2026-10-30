// Review-adjustment drawer (GC-ADJ1 step 3; REQ-046 AC-1..AC-3, REQ-045 AC-5; ADR-214 (1), ADR-003, ADR-008).
// Pure helpers. Display only: every figure is a text the server sent, "-" when absent. Nothing is computed here.
// The generic approaches carry NO figure (REQ-045 AC-5): the numbers appear only in the compare, after a pick. Their names,
// one-line texts and whether each applies come from the server (`available`); no approach text is kept in the browser.
import { NO_CHANGE_ID } from '@/lib/adjustCompare'
import { rupeesText } from '@/lib/displayFormat'

export const REVIEW_BUTTON_TEXT = 'Review adjustment'
export const PICK_NOTE = 'Pick any to compare. No change is always included.'
export const LAPSED_TEXT = 'The condition no longer holds. You can still compare the approaches.'
export const LOADING_TEXT = 'Reading the current position.'
export const NONE = '-'

const isOpen = (l) => l && (l.exited_at === null || l.exited_at === undefined) && l.pnl_kind !== 'booked'
const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : NONE)

/** The body of the drawer's one read: the server builds ONLY No change (the current position, allowed before a pick,
 *  REQ-045 AC-5) and sends `available` (every generic approach, no figure) plus the current state's figures. */
export const CURRENT_STATE_BODY = Object.freeze({ approaches: [NO_CHANGE_ID] })

/** REQ-046 AC-2 Layer 2, the part the card already has (tracking reply). A value it does not have reads "-". */
export function cardRows(body) {
  const open = Array.isArray(body?.legs) ? body.legs.filter(isOpen).length : null
  return [
    { id: 'pnl', label: 'Paper P&L (not real)', value: text(body?.paper_pnl_text) },
    { id: 'booked', label: 'Booked', value: text(body?.booked_text) },
    { id: 'unbooked', label: 'Not yet booked', value: text(body?.unbooked_text) },
    { id: 'index', label: 'Index', value: text(body?.index?.level) },
    { id: 'open_legs', label: 'Open legs', value: open === null ? NONE : String(open) },
  ]
}

// The compare criteria that describe the CURRENT position (No change = the position as it stands).
const REPLY_ROWS = Object.freeze([
  ['max_profit', 'Max profit'], ['max_loss', 'Max loss'], ['breakevens', 'Breakevens'],
  ['delta', 'Net delta'], ['gamma', 'Gamma'], ['theta', 'Theta'], ['vega', 'Vega'],
])

/** REQ-046 AC-2 Layer 2, the part from the No-change-only reply: figures, Greeks, margin, days to expiry, each as the
 *  server's text; "-" when the reply (or the cell) has none. */
export function replyRows(reply) {
  const cell = (id) => {
    const v = reply?.criteria?.find((c) => c.id === id)?.values?.[NO_CHANGE_ID]
    return v && v.unavailable_reason == null ? text(v.text) : NONE
  }
  const margin = reply?.approaches?.find((a) => a.id === NO_CHANGE_ID)?.margin
  return [
    ...REPLY_ROWS.map(([id, label]) => ({ id, label, value: cell(id) })),
    { id: 'margin', label: 'Margin needed', value: margin?.state === 'stated' ? rupeesText(text(margin.value)) : NONE },
    { id: 'days_left', label: 'Days to expiry', value: Number.isInteger(reply?.days_to_expiry) ? String(reply.days_to_expiry) : NONE },
  ]
}

export const stateRows = (body, reply) => [...cardRows(body), ...replyRows(reply)]

/** The server's `available` list as the drawer reads it; anything that is not a list is no approaches. */
export const availableOf = (reply) => (Array.isArray(reply?.available) ? reply.available : [])

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
