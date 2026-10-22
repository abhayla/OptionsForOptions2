// Leg edits of the Strategy Builder (W-126; REQ-076, REQ-077, REQ-078; ADR-008). This module only BUILDS the request
// (one edit: a control and its direction or value) and READS the reply. It computes no strike, price, lot size or money:
// the server moves the strikes, re-captures the entries and returns the engine's numbers. Strings stay strings.

export const MULTIPLIER_MIN = 1
export const MULTIPLIER_MAX = 50

/** REQ-078 AC-2: why a control that does not apply is disabled (the requirement's own sentences). */
export const REASONS = {
  shift: 'Shift needs at least 2 legs and at least one option leg.',
  width: 'Width applies to straddles, strangles, iron butterflies and iron condors.',
  hedge: 'Hedge applies to vertical spreads, iron butterflies and iron condors.',
}

/** A whole number from 1 to 50 typed as digits (REQ-076 AC-4). */
export function multiplierValid(text) {
  return /^([1-9]|[1-4]\d|50)$/.test(String(text ?? ''))
}

/** REQ-077 AC-2 first screen only: digits with at most 2 decimals. The tick size is the server's to check (the file). */
export function priceShape(text) {
  return /^\d{1,7}(\.\d{1,2})?$/.test(String(text ?? ''))
}

const CONTROL_FIELDS = {
  step: ['index', 'direction'],
  shift: ['direction'],
  width: ['direction'],
  hedge: ['direction'],
  include: ['index', 'included'],
  price: ['index', 'price'],
  multiplier: ['multiplier'],
  reset_prices: [],
}

/** The request body for ONE edit. `edit` carries only the control and the fields that control needs (a Shift click sends
 *  `{control: 'shift', direction: 1}` and nothing else, REQ-078 AC-6). Returns null for an edit that is not complete. */
export function buildEditRequest(underlying, legs, edit, shiftTotal = 0) {
  const fields = CONTROL_FIELDS[edit?.control]
  if (!fields || fields.some((f) => edit[f] === undefined || edit[f] === null)) return null
  const body = { control: edit.control }
  for (const f of fields) body[f] = edit[f]
  return {
    underlying,
    shift_total: shiftTotal,
    edit: body,
    legs: legs.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      base_lots: l.base_lots ?? l.lots,
      planned_entry: l.planned_entry ?? null,
      captured_at: l.captured_at ?? null,
      included: l.included !== false,
      typed: l.typed === true,
    })),
  }
}

/** The page's legs after a reply: each keeps its page fields (id, symbol, ...) and takes the server's contract, lots,
 *  entry, capture time, tick and typed mark. Unpriced legs come back with `planned_entry: null` and stay in the list. */
export function applyEditReply(prev, reply) {
  return reply.legs.map((r, i) => ({
    ...(prev[i] ?? {}),
    id: prev[i]?.id ?? `edit-${i}`,
    underlying: prev[i]?.underlying,
    instrument_id: r.instrument_id,
    action: r.action,
    lots: r.lots,
    base_lots: r.base_lots,
    planned_entry: r.planned_entry,
    captured_at: r.captured_at,
    included: r.included,
    typed: r.price_source === 'typed',
    hedge: r.hedge,
    instrument_type: r.instrument,
    strike: r.strike,
    expiry: r.expiry,
    symbol: r.instrument_id === prev[i]?.instrument_id ? prev[i]?.symbol ?? null : null,
  }))
}

/** What the controls show after a reply: which apply, the Shift total and the shape label (id, a label only). */
export function controlsFrom(reply) {
  return { ...reply.controls, shiftTotal: reply.shift_total, shape: reply.shape }
}

export const NO_CONTROLS = { shift: false, width: false, hedge: false, shiftTotal: 0, shape: null }
/** Before the server has answered an edit for these legs every stepper is offered; a click that does not apply is
 *  refused by the server with its reason (REQ-078 AC-6), and each reply then says which controls apply (AC-2). */
export const OFFERED_CONTROLS = { shift: true, width: true, hedge: true, shiftTotal: 0, shape: null }

/** Late replies: only the newest request's answer is used (the same idea as `seq` in LegPicker.vue). */
export function newestWins() {
  let latest = 0
  return {
    start: () => ++latest,
    isCurrent: (token) => token === latest,
  }
}

/** A signed Shift total as the control shows it: "+50", "-100"; nothing moved shows "0". The sign is display only. */
export function shiftText(total) {
  const n = Number.isInteger(total) ? total : 0
  return n > 0 ? `+${n}` : String(n)
}
