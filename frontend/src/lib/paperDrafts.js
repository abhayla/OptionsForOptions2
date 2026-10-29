// GC-TP step 3b1 (ADR-207 (2), REQ-109 AC-9; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): Drafts Mode in the builder.
// The structural fix for F-65 (a plan can never differ silently from the paper position): a paper strategy opens as its NET
// position, and every leg edit reaches the server ONLY as the paper orders paperOrdersFor(net, edited) returns, reviewed in
// the confirm list first. Quantities only (units = lots x lot size, a count): no price or money is formed here (ADR-008);
// prices are the server's texts or what the user types in the dialog.

/** The Drafts Mode frame's label (Sensibull 274-279; RD-121: paper trades said plainly as not real). */
export const PAPER_MODE_LABEL = 'Paper mode - not real trades'
export const pendingText = (n) => `${n} pending ${n === 1 ? 'change' : 'changes'}`
export const REVIEW_AND_ADD_LABEL = 'Review and add'
export const DISCARD_LABEL = 'Discard'
/** An edited leg the diff cannot read (no contract or lot size): no orders are offered; Discard restores the net position. */
export const PAPER_PENDING_UNREADABLE = 'These changes cannot be turned into paper orders. Discard them to go back to the position.'
/** REQ-109 AC-4: after hours there is no live price to default an exit to; the box says so and must be typed. */
export const LAST_CLOSE_LABEL = 'last close'
/** The paper book could not be read (network or unreadable answer): said plainly, never a silent fall-back to the plan. */
export const PAPER_BOOK_UNREADABLE = 'This strategy\'s paper position could not be read, so it is not shown. Try again.'

const SIDES = new Set(['BUY', 'SELL'])
const isCount = (v) => Number.isInteger(v) && v > 0

/** True when GET /paper/strategies/{id} answered a book with at least one order (Drafts Mode applies). */
export function isPaperBook(book) {
  return !!book && typeof book === 'object' && Array.isArray(book.orders) && book.orders.length > 0 && Array.isArray(book.positions)
}

/** The builder legs of the book's OPEN contracts (net_quantity != 0): side from the sign, lots = |net| / lot size, entry =
 *  the server's average text. `contracts` are the catalogue rows of the book's expiries. Null (fail closed) when a contract
 *  is not in the catalogue, a quantity is not an integer, or it does not divide into whole lots. */
export function netLegsFromBook(book, contracts) {
  if (!isPaperBook(book)) return null
  const byId = new Map((contracts ?? []).map((c) => [c.contract_id, c]))
  const out = []
  for (const p of book.positions) {
    if (!Number.isInteger(p?.net_quantity)) return null
    if (p.net_quantity === 0) continue // closed: booked, not a leg
    const c = byId.get(p.contract_id)
    if (!c || !isCount(c.lot_size)) return null
    const units = Math.abs(p.net_quantity)
    if (units % c.lot_size !== 0) return null
    out.push({
      id: `paper-${p.contract_id}`,
      underlying: book.underlying,
      instrument_id: `${c.exchange_segment}:${c.exchange_token}`,
      contract_id: p.contract_id,
      symbol: c.symbol ?? null,
      expiry: c.expiry,
      instrument_type: c.instrument_type,
      strike: c.strike,
      lot_size: c.lot_size,
      action: p.net_quantity > 0 ? 'BUY' : 'SELL',
      lots: units / c.lot_size,
      planned_entry: typeof p.average === 'string' ? p.average : null, // F-66: the paper fill, not the plan's entry
      captured_at: p.price_at ?? book.answered_at ?? null,
      typed: true, // the entry is the book's average: kept as given, never re-captured from today's price
      source: null,
      reason_code: null,
    })
  }
  return out
}

/** Per contract: signed units (BUY +, SELL -), its lot size, and first-seen order. Null for any leg it cannot read. */
function signedByContract(legs) {
  const out = new Map()
  for (const l of legs ?? []) {
    if (!Number.isInteger(l?.contract_id) || !isCount(l.lot_size) || !SIDES.has(l.action) || !Number.isInteger(l.lots) || l.lots < 0) return null
    const units = l.lots * l.lot_size * (l.action === 'BUY' ? 1 : -1)
    const had = out.get(l.contract_id)
    if (had && had.lot_size !== l.lot_size) return null
    out.set(l.contract_id, { units: (had?.units ?? 0) + units, lot_size: l.lot_size, leg: had?.leg ?? l })
  }
  return out
}

const order = (contractId, side, units, lotSize, kind, leg) => ({
  contract_id: contractId, side, quantity: units, lots: units / lotSize, lot_size: lotSize, kind, leg,
})

/** THE one diff of Drafts Mode: the paper orders that turn the net position (`net`, builder legs) into the edited legs.
 *  Per contract, comparing signed units: same side and larger -> one `add` (the position's side); same side and smaller ->
 *  one `exit` (opposite side) of the difference; to zero -> `exit` of the whole held quantity; crossing zero -> `exit` of the
 *  held quantity + `add` of the rest on the new side; a new contract -> `add`. Exits first, then adds, each in the order
 *  the contracts first appear (net, then edited). Each order carries the leg it came from (`leg`) for the dialog's text and
 *  default price. Null (fail closed) when any leg cannot be read: no orders are offered from an unreadable list. */
export function paperOrdersFor(net, edited) {
  const before = signedByContract(net)
  const after = signedByContract(edited)
  if (!before || !after) return null
  const exits = []
  const adds = []
  const ids = [...new Set([...before.keys(), ...after.keys()])]
  for (const id of ids) {
    const held = before.get(id)?.units ?? 0
    const want = after.get(id)?.units ?? 0
    if (held === want) continue
    const lotSize = (after.get(id) ?? before.get(id)).lot_size
    if (before.has(id) && after.has(id) && before.get(id).lot_size !== after.get(id).lot_size) return null
    const heldLeg = before.get(id)?.leg ?? null
    const wantLeg = after.get(id)?.leg ?? heldLeg
    const sideOf = (units) => (units > 0 ? 'BUY' : 'SELL')
    const opposite = (units) => (units > 0 ? 'SELL' : 'BUY')
    if (held === 0) {
      adds.push(order(id, sideOf(want), Math.abs(want), lotSize, 'add', wantLeg))
    } else if (want === 0 || Math.sign(want) !== Math.sign(held)) {
      exits.push(order(id, opposite(held), Math.abs(held), lotSize, 'exit', heldLeg))
      if (want !== 0) adds.push(order(id, sideOf(want), Math.abs(want), lotSize, 'add', wantLeg))
    } else if (Math.abs(want) > Math.abs(held)) {
      adds.push(order(id, sideOf(held), Math.abs(want) - Math.abs(held), lotSize, 'add', wantLeg))
    } else {
      exits.push(order(id, opposite(held), Math.abs(held) - Math.abs(want), lotSize, 'exit', heldLeg))
    }
  }
  return [...exits, ...adds]
}

/** The confirm list's rows for `orders` (PaperConfirmDialog props). Default price: an exit at the contract's live LTP text from
 *  the book; an add at the leg's builder entry price. With no live LTP (after hours, REQ-109 AC-4) the exit's box is empty, marked
 *  "last close", and must be typed (the dialog refuses an empty price). Texts only: no price is formed here (ADR-008). */
export function confirmRowsFor(orders, book, nameOf) {
  const byId = new Map((book?.positions ?? []).map((p) => [p.contract_id, p]))
  return orders.map((o, i) => {
    const p = byId.get(o.contract_id)
    const live = o.kind === 'exit' && p?.price_state === 'live' && typeof p.ltp_text === 'string' && p.ltp_text.trim() !== ''
    const price = o.kind === 'exit' ? (live ? p.ltp_text.trim() : '') : (typeof o.leg?.planned_entry === 'string' ? o.leg.planned_entry : '')
    return {
      key: `${o.kind}-${o.contract_id}-${i}`,
      contract_id: o.contract_id,
      side: o.side,
      text: nameOf(o.leg) || p?.contract_text || '',
      lots: o.lots,
      lot_size: o.lot_size,
      price,
      kind: o.kind,
      price_note: o.kind === 'exit' && !live ? LAST_CLOSE_LABEL : '',
    }
  })
}

/** Read GET /paper/strategies/{id} for the builder: {kind:'paper', book, net} when it has orders (Drafts Mode), {kind:'plan'} when
 *  it has none or the server answers 404 (not a paper strategy: the saved plan opens as before). Any other failure (network,
 *  5xx, an unreadable book) THROWS: the caller says so and never falls back to the plan silently. */
export async function readPaperBook(client, id) {
  let book
  try {
    book = (await client.get(`/paper/strategies/${id}`)).data
  } catch (e) {
    if (e?.status === 404) return { kind: 'plan' }
    throw e
  }
  if (!book || typeof book !== 'object' || !Array.isArray(book.orders)) throw new Error('unreadable paper book')
  if (!isPaperBook(book)) return { kind: 'plan' }
  const contracts = []
  const expiries = [...new Set(book.positions.filter((p) => p?.net_quantity !== 0).map((p) => p?.expiry))]
  for (const expiry of expiries) {
    contracts.push(...(await client.get(`/catalogue/${book.underlying}/contracts?expiry=${expiry}`)).data.contracts)
  }
  const net = netLegsFromBook(book, contracts)
  if (!net) throw new Error('unreadable paper book')
  return { kind: 'paper', book, net }
}
