// Leg edits of the Strategy Builder (W-148; REQ-076 AC-1 to AC-10, ADR-008). Adapted from this repo's own branch
// build/W-126-a1-leg-rows (frontend/src/lib/legEdit.js), REQ-076 controls only: Shift / Width / Hedge (REQ-078) and the
// typed price / Reset Prices (REQ-077) are not here. This module only BUILDS the request (one edit: a control and its
// direction or value) and READS the reply. It computes no strike, price, lot size or money: the server moves the strikes,
// re-captures the entries and returns the engine's numbers. Strings stay strings.

import { canonicalMoney } from '@/lib/liveMatch'
import { listReasonText } from '@/lib/legPicker'
import { istTime } from '@/lib/displayFormat'

export const MULTIPLIER_MIN = 1
export const MULTIPLIER_MAX = 50
/** REQ-076 AC-9: the name shown when the server matched no shape. */
export const CUSTOM_STRATEGY = 'Custom Strategy'
/** REQ-076 AC-6: the label on an unticked leg. */
export const LEFT_OUT_LABEL = 'Left out of the numbers'
/** REQ-076 AC-7: why Execute is refused while any leg is unticked (the requirement's own sentence). */
// REQ-119 AC-4: shown beside the disabled Execute while the newest outcome or edit request has no applied reply
export const EXECUTE_WAITS_FOR_LATEST = 'Waiting for the latest numbers: Execute opens once they have arrived.'
export const EXECUTE_NEEDS_ALL_TICKED = 'Tick every leg to execute: the whole strategy is sent as one plan.'
/** REQ-076 AC-10: the empty list's sentence. */
export const NO_LEGS_YET = 'No legs yet'
/** REQ-135 AC-1: the Clear all legs question (N = the number of legs on the list) and how long Undo stays offered. */
export const removeAllPrompt = (n) => `Remove all ${n} legs?`
export const LEGS_CLEARED = 'All legs removed.'
export const CLEAR_UNDO_MS = 10000

/** The multiplier is CHOSEN from this fixed list (REQ-076 AC-4), never parsed from text: the server still refuses any
 *  other value. A fixed list, so the page converts no text to a number (ADR-008). */
export const MULTIPLIER_CHOICES = Object.freeze([...Array(MULTIPLIER_MAX + 1).keys()].slice(MULTIPLIER_MIN))

const CONTROL_FIELDS = {
  step: ['index', 'direction'],
  include: ['index', 'included'],
  multiplier: ['multiplier'],
  price: ['index', 'price'], // REQ-077 AC-1/AC-2: the typed TEXT as entered, judged by the server only
  reset_prices: [], // REQ-077 AC-5: every leg is re-captured from its current price
  reset_leg: ['index'], // REQ-077 AC-5: the same for one leg
  shift: ['direction'], // REQ-078 AC-6: the browser sends only the control and its direction; the server moves the strikes
  width: ['direction'],
  hedge: ['direction'],
  read: [], // changes no leg: the server answers the current numbers, shape name and Hedge marks (REQ-076 AC-8)
}

/** True for a leg the step control applies to: an option leg only (an allow-list: a futures or unknown leg has none). */
export function canStep(leg) {
  return leg?.instrument_type === 'CE' || leg?.instrument_type === 'PE'
}

/** REQ-076 AC-7: the reason Execute is refused, or null when every leg is ticked. */
export function executeRefusal(legs) {
  return legs.some((l) => l.included === false) ? EXECUTE_NEEDS_ALL_TICKED : null
}

/** The request body for ONE edit; null for an edit that is not complete or a leg the server cannot name. `shiftTotal` is the
 *  page's last Shift total as the server sent it (an integer, never computed from strikes); sent only when there is one. */
export function buildEditRequest(underlying, legs, edit, shiftTotal = null) {
  const fields = CONTROL_FIELDS[edit?.control]
  if (!fields || fields.some((f) => edit[f] === undefined || edit[f] === null)) return null
  if (!legs.length || legs.some((l) => typeof l.instrument_id !== 'string' || !l.instrument_id)) return null
  if (edit.control === 'price' && typeof edit.price !== 'string') return null // text, never a number (ADR-008)
  const body = { control: edit.control }
  for (const f of fields) body[f] = edit[f]
  return {
    underlying,
    edit: body,
    ...(Number.isInteger(shiftTotal) ? { shift_total: shiftTotal } : {}),
    legs: legs.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      base_lots: l.base_lots ?? l.lots,
      planned_entry: l.planned_entry ?? null,
      captured_at: l.captured_at ?? null,
      close_at: l.close_at ?? null, // ADR-197: sent back as is; the server keeps it on a leg it does not re-capture
      included: l.included !== false,
      typed: l.typed === true,
    })),
  }
}

/** The page's legs after a reply: each keeps its page fields and takes the server's contract, lots, entry, capture time,
 *  tick and Hedge mark. The saved-contract fields (`contract_id`, `lot_size`)
 *  are the reply's own, so a stepped leg saves its NEW contract, and a reply without them leaves the leg unsavable: Save
 *  Draft never sends the old contract. */
export function applyEditReply(prev, reply) {
  return reply.legs.map((r, i) => {
    const old = prev[i] ?? {}
    const same = old.instrument_id === r.instrument_id
    return {
      ...old,
      id: old.id ?? `edit-${i}`,
      underlying: old.underlying,
      instrument_id: r.instrument_id,
      // ADR-197: the close label of the entry, as the reply sent it
      close_at: r.close_at ?? null, // the server's answer: kept, re-captured after hours, or none
      contract_id: r.contract_id ?? null, // the server's id for THIS contract (a stepped leg's new one); null = not savable
      lot_size: r.lot_size ?? null,
      symbol: same ? old.symbol ?? null : null,
      action: r.action,
      lots: r.lots,
      base_lots: r.base_lots,
      quantity: r.quantity ?? null, // the server's lots times lot size, drawn as sent (ADR-008)
      planned_entry: r.planned_entry,
      planned_entry_display: r.planned_entry_display ?? null, // GC-UI D-PX: the server's two-decimal text
      captured_at: r.captured_at,
      included: r.included,
      typed: r.price_source === 'typed',
      price_reason: r.price_reason ?? null,
      hedge: r.hedge === true,
      replaced_typed: r.replaced_typed === true, // REQ-078 AC-8: a typed price this reply replaced (the screen says so)
      block: r.block ?? null,
      instrument_type: r.instrument,
      strike: r.strike,
      expiry: r.expiry,
      days_to_expiry: r.days_to_expiry ?? null, // REQ-135 AC-2: the server's day count, drawn as sent
    }
  })
}

/** REQ-078 AC-2: shown only when the strategy has at least 2 legs and at least one option leg. */
export function showsControls(legs) {
  return legs.length >= 2 && legs.some(canStep)
}

/** REQ-078 AC-2: nothing applies until the server says so (no reply yet, or an old server without the field). */
/** The AC-2 sentence for Width, used only when a control is off and the server sent no reason for it. */
export const WIDTH_REASON_FALLBACK = 'Width applies to straddles, strangles, iron butterflies and iron condors.'
export const NO_REASON_FALLBACK = 'This move is not available for these legs.'
export const NO_CONTROLS = Object.freeze({ shift: false, width: false, hedge: false, shiftTotal: null,
  reasons: Object.freeze({ shift: NO_REASON_FALLBACK, width: WIDTH_REASON_FALLBACK, hedge: NO_REASON_FALLBACK }) })

/** REQ-078 AC-2/AC-3: which controls work and the Shift total, exactly as the reply sent them. A control is on only when the
 *  server said `true`; the reason is the server's sentence (`what_happened` of its catalogue text), never built here. */
export function controlsFrom(reply) {
  const c = reply?.controls
  if (!c || typeof c !== 'object') return NO_CONTROLS
  const reasons = {}
  for (const id of ['shift', 'width', 'hedge']) {
    const text = reply.control_reasons?.[id]?.what_happened
    reasons[id] = c[id] === true ? null : typeof text === 'string' && text ? text : id === 'width' ? WIDTH_REASON_FALLBACK : NO_REASON_FALLBACK
  }
  return { shift: c.shift === true, width: c.width === true, hedge: c.hedge === true,
    shiftTotal: Number.isInteger(reply.shift_total) ? reply.shift_total : null, reasons }
}

/** REQ-078 AC-3 / ADR-186 (2): the Shift total as text from the server's integer: '+50', '-100'; '-' for none or 0. No arithmetic. */
export function shiftText(total) {
  if (!Number.isInteger(total) || total === 0) return '-'
  return total > 0 ? `+${total}` : `${total}`
}

/** REQ-078 AC-8: the sentence for a leg whose typed price this reply replaced; strike and type as the server sent them. */
export const replacedPriceNote = (number, leg) => `Your price for leg ${number} was replaced by the captured price of ${leg.strike} ${leg.instrument_type}.`

/** REQ-076 AC-8/AC-9: the shape name exactly as the server sent it; 'Custom Strategy' when it matched none. */
export function shapeLabel(reply) {
  return reply.shape_name ?? CUSTOM_STRATEGY
}

/** REQ-077 AC-1: the label of a priced leg - a typed price is the user's, a captured one keeps the ADR-068 label. */
export const YOUR_PRICE_LABEL = 'Your price'
export const PLANNED_ENTRY_LABEL = 'Planned entry'
/** REQ-077 AC-5: why a leg has no price after a reset, in the existing wording (REQ-049 / ADR-085); a closed map. */
const NO_LIVE_PRICE_TEXT = 'This contract has no live price right now, so it has no planned entry.'
export function priceReasonText(code) {
  if (code === 'not_connected') return listReasonText('NOT_CONNECTED')
  if (code === 'no_live_price') return NO_LIVE_PRICE_TEXT
  return null
}

/** REQ-152 AC-4: a price the server sent no display text for prints as the dash, never as the raw value. */
const NO_PRICE_TEXT = '—'

/** REQ-077 AC-6: the 'Price has moved' marker text, or null. The two server strings are compared for EQUALITY only; `shown` is the server's two-decimal display text of each (GC-UI D-PX), the only text printed (no
 *  arithmetic, ADR-008): no marker without a live price, no marker without a planned entry; the marker changes no number. */
export function movedMarker(leg, ltp, shown = {}) {
  if (leg?.planned_entry == null || ltp == null || ltp === '') return null
  const planned = canonicalMoney(leg.planned_entry) ?? leg.planned_entry
  const now = canonicalMoney(ltp) ?? ltp
  if (planned === now) return null
  const since = leg.captured_at == null ? '' : ` since ${istTime(leg.captured_at)}`
  return `Price has moved${since}: planned ${shown.planned_entry_display ?? NO_PRICE_TEXT}, now ${shown.ltp_display ?? NO_PRICE_TEXT}`
}

/** ADR-195 (Sensibull S-111, ADR-152): while any leg is left out of the numbers the builder names no shape, shows no Hedge
 *  mark and turns Width and Hedge off with this reason; ticking every leg again restores the server's controls as sent. */
export const UNTICKED_CONTROL_REASON = 'Width and Hedge work only when every leg is ticked.'
export const anyUnticked = (legs) => (Array.isArray(legs) ? legs : []).some((l) => l?.included === false)
export function controlsForSelection(controls, legs) {
  if (!anyUnticked(legs)) return controls
  return { ...controls, width: false, hedge: false, reasons: { ...controls.reasons, width: UNTICKED_CONTROL_REASON, hedge: UNTICKED_CONTROL_REASON } }
}

/** W-192 (UI-104): the compact leg row's column widths in px, in order (tick, B/S, expiry, strike, type, lots, price, depth,
 *  edit, remove). Their sum plus the card's side padding stays within the 480 px narrowest left column, so a row never wraps. */
// GC-UI 3a (D-A09, D-A16): tick, B/S, expiry, strike stepper, type, lots, price box, depth, bin (the pencil column is gone:
// the strike opens the leg in the drawer)
export const LEG_ROW_COLUMNS = Object.freeze([20, 24, 84, 100, 34, 48, 96, 22, 22])
export const LEG_CARD_PADDING_PX = 12
export const LEFT_COLUMN_MIN_PX = 480
