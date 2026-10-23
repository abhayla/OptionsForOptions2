// Leg edits of the Strategy Builder (W-148; REQ-076 AC-1 to AC-10, ADR-008). Adapted from this repo's own branch
// build/W-126-a1-leg-rows (frontend/src/lib/legEdit.js), REQ-076 controls only: Shift / Width / Hedge (REQ-078) and the
// typed price / Reset Prices (REQ-077) are not here. This module only BUILDS the request (one edit: a control and its
// direction or value) and READS the reply. It computes no strike, price, lot size or money: the server moves the strikes,
// re-captures the entries and returns the engine's numbers. Strings stay strings.

export const MULTIPLIER_MIN = 1
export const MULTIPLIER_MAX = 50
/** REQ-076 AC-9: the name shown when the server matched no shape. */
export const CUSTOM_STRATEGY = 'Custom Strategy'
/** REQ-076 AC-6: the label on an unticked leg. */
export const LEFT_OUT_LABEL = 'Left out of the numbers'
/** REQ-076 AC-7: why Execute is refused while any leg is unticked (the requirement's own sentence). */
export const EXECUTE_NEEDS_ALL_TICKED = 'Tick every leg to execute: the whole strategy is sent as one plan.'
/** REQ-076 AC-10: the empty list's sentence. */
export const NO_LEGS_YET = 'No legs yet'

/** The multiplier is CHOSEN from this fixed list (REQ-076 AC-4), never parsed from text: the server still refuses any
 *  other value. A fixed list, so the page converts no text to a number (ADR-008). */
export const MULTIPLIER_CHOICES = Object.freeze([...Array(MULTIPLIER_MAX + 1).keys()].slice(MULTIPLIER_MIN))

const CONTROL_FIELDS = {
  step: ['index', 'direction'],
  include: ['index', 'included'],
  multiplier: ['multiplier'],
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

/** The request body for ONE edit; null for an edit that is not complete or a leg the server cannot name. */
export function buildEditRequest(underlying, legs, edit) {
  const fields = CONTROL_FIELDS[edit?.control]
  if (!fields || fields.some((f) => edit[f] === undefined || edit[f] === null)) return null
  if (!legs.length || legs.some((l) => typeof l.instrument_id !== 'string' || !l.instrument_id)) return null
  const body = { control: edit.control }
  for (const f of fields) body[f] = edit[f]
  return {
    underlying,
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
      contract_id: r.contract_id ?? null, // the server's id for THIS contract (a stepped leg's new one); null = not savable
      lot_size: r.lot_size ?? null,
      symbol: same ? old.symbol ?? null : null,
      action: r.action,
      lots: r.lots,
      base_lots: r.base_lots,
      quantity: r.quantity ?? null, // the server's lots times lot size, drawn as sent (ADR-008)
      planned_entry: r.planned_entry,
      captured_at: r.captured_at,
      included: r.included,
      typed: r.price_source === 'typed',
      hedge: r.hedge === true,
      block: r.block ?? null,
      instrument_type: r.instrument,
      strike: r.strike,
      expiry: r.expiry,
    }
  })
}

/** REQ-076 AC-8/AC-9: the shape name exactly as the server sent it; 'Custom Strategy' when it matched none. */
export function shapeLabel(reply) {
  return reply.shape_name ?? CUSTOM_STRATEGY
}
