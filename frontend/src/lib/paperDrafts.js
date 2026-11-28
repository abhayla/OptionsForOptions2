// GC-TP step 3b1 (ADR-207 (2), REQ-109 AC-9; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): Drafts Mode in the builder.
// The structural fix for F-65 (a plan can never differ silently from the paper position): a paper strategy opens as its NET
// position, and every leg edit reaches the server ONLY as the paper orders paperOrdersFor(net, edited) returns, reviewed in
// the confirm list first. Quantities only (units = lots x lot size, a count): no price or money is formed here (ADR-008);
// prices are the server's texts or what the user types in the dialog.
import { entryPriceFor, afterFigure } from '@/lib/tracking'

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

/** The book AND the catalogue both answered, but the book's open contracts are not in the catalogue's answer (or do not divide into
 *  its lots): an answer that does not match, not a failed read. Never worded "could not be read" (no request failed). */
export const PAPER_BOOK_UNMATCHED = Object.freeze({
  what_happened: 'This strategy\'s paper position was read, but its contracts are not in the catalogue for today, so it is not shown.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  what_is_blocked: 'Nothing was changed and no order was placed.',
  next_action: 'Trying again will not help until the catalogue lists these contracts.',
})

const SIDES = new Set(['BUY', 'SELL'])
const isCount = (v) => Number.isInteger(v) && v > 0
// a count of units (an integer quantity, never money): its size and its side
const size = (n) => (n < 0 ? -n : n)
const sameSide = (a, b) => (a > 0) === (b > 0)

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
    const held = size(p.net_quantity)
    if (held % c.lot_size !== 0) return null
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
      lots: held / c.lot_size,
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
    const signed = l.action === 'BUY' ? l.lots * l.lot_size : -(l.lots * l.lot_size)
    const had = out.get(l.contract_id)
    if (had && had.lot_size !== l.lot_size) return null
    out.set(l.contract_id, { units: (had?.units ?? 0) + signed, lot_size: l.lot_size, leg: had?.leg ?? l })
  }
  return out
}

const order = (contractId, side, units, lotSize, kind, leg) => ({
  contract_id: contractId, side, quantity: units, lots: units / lotSize, lot_size: lotSize, kind, leg,
})

/** The contract ids that more than one row holds with the same action (a kept duplicate); rows with lots 0 do not count. */
function keptDuplicateIds(legs) {
  const seen = new Set()
  const out = new Set()
  for (const l of legs ?? []) {
    if (!(l.lots > 0)) continue
    const key = `${l.contract_id}:${l.action}`
    if (seen.has(key)) out.add(l.contract_id)
    seen.add(key)
  }
  return out
}

/** THE one diff of Drafts Mode: the paper orders that turn the net position (`net`, builder legs) into the edited legs.
 *  Per contract, comparing signed units: same side and larger -> one `add` (the position's side); same side and smaller ->
 *  one `exit` (opposite side) of the difference; to zero -> `exit` of the whole held quantity; crossing zero -> `exit` of the
 *  held quantity + `add` of the rest on the new side; a new contract -> `add`. Listed BUY exits, BUY adds, SELL exits, SELL adds (REQ-159 AC-6: hedge
 *  first on entry, short buy-backs before long sales), each group in the order the contracts first appear (net, then edited). Each order carries the leg it came from (`leg`) for the dialog's text and
 *  default price. Null (fail closed) when any leg cannot be read: no orders are offered from an unreadable list. */
export function paperOrdersFor(net, edited) {
  const before = signedByContract(net)
  const after = signedByContract(edited)
  if (!before || !after) return null
  const exits = []
  const adds = []
  // D-60 (ADR-319 (3), A4 review 3 finding 1): two rows of one contract and action are a KEPT duplicate. It is never summed into
  // one order: each row goes as its own `add`, so the server's duplicate check (the one refusal source) sees both and refuses
  // with its gate sentence. Netting stays per contract for every other edit (one row's lots changed, a buy and a sell).
  const dups = keptDuplicateIds(edited)
  for (const id of dups) {
    for (const l of edited) {
      if (l.contract_id === id && l.lots > 0) adds.push(order(id, l.action, l.lots * l.lot_size, l.lot_size, 'add', l))
    }
  }
  const ids = [...new Set([...before.keys(), ...after.keys()])].filter((id) => !dups.has(id))
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
      adds.push(order(id, sideOf(want), size(want), lotSize, 'add', wantLeg))
    } else if (want === 0 || !sameSide(want, held)) {
      exits.push(order(id, opposite(held), size(held), lotSize, 'exit', heldLeg))
      if (want !== 0) adds.push(order(id, sideOf(want), size(want), lotSize, 'add', wantLeg))
    } else if (size(want) > size(held)) {
      adds.push(order(id, sideOf(held), size(want) - size(held), lotSize, 'add', wantLeg))
    } else {
      exits.push(order(id, opposite(held), size(held) - size(want), lotSize, 'exit', heldLeg))
    }
  }
  // REQ-159 AC-6 / REQ-058: buy legs first, whatever the diff produced: short buy-backs, new hedges, old-hedge sales, new shorts.
  const rank = (o) => (o.side === 'BUY' ? 0 : 2) + (o.kind === 'exit' ? 0 : 1)
  return [...exits, ...adds].sort((a, b) => rank(a) - rank(b)) // stable (ES2019)
}

/** The confirm list's rows for `orders` (PaperConfirmDialog props). Default price: an exit at the contract's live LTP text from
 *  the book; an add at the leg's builder entry price. With no live LTP (after hours, REQ-109 AC-4) the exit's box is empty, marked
 *  "last close", and must be typed (the dialog refuses an empty price). Texts only: no price is formed here (ADR-008). */
export function confirmRowsFor(orders, book, nameOf, livePriceById = {}) {
  const byId = new Map((book?.positions ?? []).map((p) => [p.contract_id, p]))
  return orders.map((o, i) => {
    const p = byId.get(o.contract_id)
    const live = o.kind === 'exit' && p?.price_state === 'live' && typeof p.ltp_text === 'string' && p.ltp_text.trim() !== ''
    // an entry starts at the live price the page holds for the leg, else the planned entry (noted); fix/paper-dialog-safe item 2
    const entry = o.kind === 'exit' ? null : entryPriceFor(o.leg, livePriceById)
    const price = o.kind === 'exit' ? (live ? p.ltp_text.trim() : '') : entry.price
    return {
      key: `${o.kind}-${o.contract_id}-${i}`,
      contract_id: o.contract_id,
      side: o.side,
      text: nameOf(o.leg) || p?.contract_text || '',
      lots: o.lots,
      lot_size: o.lot_size,
      price,
      price_at: o.kind === 'exit' && live && typeof p.price_at === 'string' ? p.price_at : null, // D-09: the shown quote's own time
      kind: o.kind,
      price_note: o.kind === 'exit' ? (live ? '' : LAST_CLOSE_LABEL) : entry.price_note,
    }
  })
}

/** Read GET /paper/strategies/{id} for the builder: {kind:'paper', book, net} when it has orders (Drafts Mode), {kind:'plan'} when
 *  it has none or the server answers 404 (not a paper strategy: the saved plan opens as before). Any other failure (network,
 *  5xx, an unreadable book) THROWS: the caller says so and never falls back to the plan silently. */
export async function readPaperBook(client, id) {
  const sentAt = Date.now() // Lane FJ item 1: when this read was SENT (the unknown-exit rule asks it, never the time its answer came)
  let book
  try {
    book = (await client.get(`/paper/strategies/${id}`)).data
  } catch (e) {
    if (e?.status === 404) return { kind: 'plan', sentAt }
    throw e
  }
  if (!book || typeof book !== 'object' || !Array.isArray(book.orders)) throw new Error('unreadable paper book')
  if (!isPaperBook(book)) return { kind: 'plan', sentAt }
  const contracts = []
  const expiries = [...new Set(book.positions.filter((p) => p?.net_quantity !== 0).map((p) => p?.expiry))]
  for (const expiry of expiries) {
    const rows = (await client.get(`/catalogue/${book.underlying}/contracts?expiry=${expiry}`)).data?.contracts
    if (!Array.isArray(rows)) throw new Error('unreadable catalogue answer') // an answer that is not a contracts list: a failed read
    contracts.push(...rows)
  }
  const net = netLegsFromBook(book, contracts)
  // D-40: an open leg on an expired contract is not in the catalogue; the server says so (expired_open) and why nothing is priced.
  // Any other unreadable book (catalogue, net mismatch, a leg that is not live but not expired) still throws below.
  if (!net && book.expired_open === true) return { kind: 'unpriced', book, sentAt }
  if (!net) {
    const err = new Error('paper book does not match the catalogue')
    err.unmatched = book.positions.every((p) => Number.isInteger(p?.net_quantity)) // every quantity read, so the mismatch is the contracts', not a malformed answer
    throw err
  }
  return { kind: 'paper', book, net, sentAt }
}

/** GC-ICFIX issue 18: waits (ms) before each read of the book after practice orders were stored: now, then two spaced retries.
 *  Three tries in all, never a loop; after them the screen shows the shared "could not load" state with Retry. */
export const PAPER_REREAD_DELAYS_MS = Object.freeze([0, 400, 1200])

// GC-TP step 3b2 (REQ-109 AC-9; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): the rest of Drafts Mode.
/** R-11: a leg loaded from the book carries the paper fill's average, not a price the user typed (no time beside it). */
export const PAPER_AVERAGE_LABEL = 'Paper average'
export const PROFIT_LEFT_LABEL = 'Profit left'
// D-14 (ADR-320 (2)): on the trade's expiry day only, Max profit and Profit left are shown twice under these two labels
export const HELD_TO_EXPIRY_LABEL = 'If held to expiry'
export const EXITED_NOW_LABEL = 'If exited now'
export const LOSS_LEFT_LABEL = 'Loss left'
// ADR-302: when Profit left (after charges) is larger than Max profit the server sends `recover_text`; this one sentence says why
export const RECOVER_LINE_PREFIX = 'includes Rs '
export const RECOVER_LINE_SUFFIX = ' needed to recover the current loss'
const serverText = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)
/** Drafts Mode summary: { profit, loss } as afterFigure results (the server's after text labelled, else the before text labelled with
 *  the reason, else the paused sentence), `recover` = the fixed line around the server's amount (its leading "+" dropped: text only),
 *  `reason` = extremes_reason_text. Nothing is added up, capped or compared here (ADR-008). */
export const LEFT_BREAKDOWN_LABELS = Object.freeze({
  maxProfit: 'Max profit (after charges)', maxLoss: 'Max loss (after charges)', total: 'Total P&L so far (after charges)',
})
export function paperLeftOf(book, pausedText = null) {
  if (!book) return null
  // ADR-306: Profit left = Max profit - Total P&L so far (both after charges): the tap shows those two server texts, never a sum
  // made here. Only an "after" figure with both texts opens; a reason or a paused figure opens nothing (the reason is on screen).
  const one = (k, maxLabel) => {
    const f = afterFigure(book, serverText(book[`${k}_left_text`]), pausedText, `${k}_left_after_text`, [])
    const max = serverText(book[`max_${k}_text`])
    const total = serverText(book.total_after_text)
    const rows = f.kind === 'after' && max !== null && total !== null
      ? [{ id: 'max', label: maxLabel, text: max }, { id: 'total', label: LEFT_BREAKDOWN_LABELS.total, text: total }] : null
    return { ...f, breakdown: rows && { rows, reason: null } }
  }
  const profit = one('profit', LEFT_BREAKDOWN_LABELS.maxProfit)
  const recover = serverText(book.recover_text)
  return {
    profit, loss: one('loss', LEFT_BREAKDOWN_LABELS.maxLoss),
    recover: recover !== null && profit.kind === 'after' ? `${RECOVER_LINE_PREFIX}${recover.replace(/^\+/, '')}${RECOVER_LINE_SUFFIX}` : null,
    reason: serverText(book.extremes_reason_text), // R-20: the server's sentence for extremes_reason, never written here
    // F-94: the server's sentence on whether the round-trip charges are inside Max Profit / Max Loss; `after` = the server sent the
    // charges amount (its presence, not a number made here). Nothing beside a paused figure.
    // D-14 round 2: a paused book's Max Profit is before charges: the server's sentence says so beside it (after: false)
    extremes: { text: serverText(book.extremes_charges_text), after: profit.kind !== 'paused' && serverText(book.extremes_charges) !== null },
    // D-14 (ADR-320 (2)): the server sends the held pair on the trade's expiry day only; the exited pair is the usual figures
    expiryPair: serverText(book.max_profit_hold_text) === null || profit.kind !== 'after' ? null : {
      held: { maxProfit: serverText(book.max_profit_hold_text), profitLeft: serverText(book.profit_left_hold_text) },
      exited: { maxProfit: serverText(book.max_profit_text), profitLeft: profit.text },
    },
  }
}
/** D-13/D-14 round 2: what the Charges dialog shows in Drafts Mode, the paper reply's own texts as sent (no sum made here):
 *  charges paid, the estimated cost to close at the live price, and `total` = extremes_charges (the charges inside Max Profit and
 *  Max Loss; null when those are before charges). Null when the reply has no paid-charges text (the dialog then has nothing to show). */
export function paperChargesOf(book) {
  const paid = serverText(book?.charges_paid_text ?? book?.charges_text)
  if (paid === null) return null
  return { paid, toClose: serverText(book.charges_to_close_text), total: serverText(book.extremes_charges), sentence: serverText(book.extremes_charges_text) }
}
export const EXIT_ALL_LABEL = 'Exit all'
export const EXIT_LABEL = 'Exit'
export const ADD_KIND_LABEL = 'Add'
export const STOP_KIND_LABEL = 'Stop'
export const SETTLE_KIND_LABEL = 'Settled'
export const NET_POSITIONS_LABEL = 'Net Positions'
export const ORDERBOOK_LABEL = 'Orderbook'

/** ADR-330 (10): every exit confirmation names what it exits in its title. The ONE place the word is spelled: 'Paper', or
 *  'Real (Zerodha order)' for a real exit (none is rendered today, ADR-281). Anything but 'real' reads Paper (fail closed). */
const KIND_WORDS = { paper: 'Paper', real: 'Real (Zerodha order)' }
/** Only exactly 'paper' or 'real' is accepted; anything else THROWS (fail closed: a wrong word on a confirmation is worse than none). */
export const positionKindWord = (kind) => {
  if (kind !== 'paper' && kind !== 'real') throw new Error(`positionKindWord: unknown kind ${String(kind)}`)
  return KIND_WORDS[kind]
}
export const exitConfirmTitle = (kind) => `Exit ${positionKindWord(kind)} positions`
export const reviewConfirmTitle = (kind) => `Review ${positionKindWord(kind)} orders`

/** The confirm list's title by what it holds: only adds (an `open` is the first add) -> Add to Paper; only exits ->
 *  exitConfirmTitle; both -> reviewConfirmTitle. */
export const PAPER_TITLE_ADD = 'Add to Paper'
export const PAPER_TITLE_EXIT = exitConfirmTitle('paper')
export const PAPER_TITLE_BOTH = reviewConfirmTitle('paper')
export function paperDialogTitle(orders, kind = 'paper') {
  const list = orders ?? []
  const exits = list.filter((o) => o?.kind === 'exit').length
  if (exits === 0) return PAPER_TITLE_ADD
  return exits === list.length ? exitConfirmTitle(kind) : reviewConfirmTitle(kind)
}
/** Each row's kind beside B/S ('open' and 'add' both add to the position; D-23: a stop-out and an expiry settlement keep their own
 *  kind, the server's `stop` and `settle`, so they never read as a new buy). */
const KIND_LABELS = { exit: EXIT_LABEL, stop: STOP_KIND_LABEL, settle: SETTLE_KIND_LABEL }
export const paperKindLabel = (kind) => KIND_LABELS[kind] ?? ADD_KIND_LABEL

/** The open lots of `contractId` in the net position (a count), or 0. */
export function openLots(net, contractId) {
  const l = (net ?? []).find((x) => x.contract_id === contractId)
  return l ? l.lots : 0
}
/** The whole lots 1..max a lots-box text names (a count), or null: matched against the allowed counts, never parsed. */
export function exitLotsFrom(text, max) {
  const s = String(text ?? '').trim()
  for (let k = 1; k <= max; k += 1) if (String(k) === s) return k
  return null
}
export const exitLotsOk = (text, max) => exitLotsFrom(text, max) !== null
/** D-48 review (ADR-328 (4)): the sentence of a row Exit on a contract that has a change waiting that is not an exit. */
export const EXIT_BLOCKED_BY_CHANGE = 'This leg has a change waiting; review or discard it first.'

/** ADR-330 (49) (owner, 27 Nov 2026), replacing D-48 round 2's "a row Exit never carries an add": ONLY the changed leg's Exit is
 *  blocked. Round 2 (F3): a held leg is untouched ONLY if exactly one screen row carries its id, that row is the only row of its
 *  contract, and it has the held contract, side and lots. Anything else blocks it: a missing row (a merge answered with Increase,
 *  a removed leg), a row id that is gone (an adjustment roll `adjust-i`), changed lots (also the held contract a merge raised), a
 *  flipped side, a moved contract, a second row of the contract. What the OTHER legs stage is not read here: an untouched leg's Exit
 *  posts that leg's exit alone (exitOnlyOrders). ONE predicate: legsAfterExit (the door) and the panel (stagedChangeIds) both use it. */
export function rowExitBlocked(net, legs, contractId) {
  const held = (net ?? []).find((n) => n.contract_id === contractId)
  if (!held) return true
  const rows = legs ?? []
  const byId = rows.filter((l) => l.id === held.id)
  const ofContract = rows.filter((l) => l.contract_id === contractId)
  const only = byId.length === 1 && ofContract.length === 1 && byId[0] === ofContract[0] ? byId[0] : null
  return !(only && only.action === held.action && only.lots === held.lots)
}
/** The contract ids whose row Exit is off before the click (the panel's `changedIds`): rowExitBlocked, per open contract. */
export const stagedChangeIds = (net, legs) => (net ?? []).filter((n) => rowExitBlocked(net, legs, n.contract_id)).map((n) => n.contract_id)

/** The EDITED legs for "exit `lots` of `contractId`": every other contract keeps the legs on screen; this contract becomes its
 *  net leg less `lots` (gone at zero), in its place. Only legs change: the orders still come from paperOrdersFor(net, edited),
 *  never a second order-building path. Null when `lots` is not 1..open lots. */
export function legsAfterExit(net, legs, contractId, lots) {
  const held = (net ?? []).find((l) => l.contract_id === contractId)
  if (!held || !Number.isInteger(lots) || lots < 1 || lots > held.lots) return null
  if (rowExitBlocked(net, legs, contractId)) return null // the ONE door: an Exit never combines with a staged move, add or new leg
  const rest = held.lots - lots
  const out = []
  let placed = false
  for (const l of legs ?? []) {
    if (l.contract_id !== contractId) { out.push(l); continue }
    if (!placed && rest > 0) out.push({ ...held, lots: rest })
    placed = true
  }
  if (!placed && rest > 0) out.push({ ...held, lots: rest })
  return out
}

/** ADR-330 (49): the orders of a row Exit of `lots` of `contractId`: the ONE diff (paperOrdersFor) of the NET position against
 *  itself less those lots, so exactly one `exit` row and nothing the page's other legs stage. Null when `lots` is not 1..open. */
export function exitOnlyOrders(net, contractId, lots) {
  const next = legsAfterExit(net, net, contractId, lots)
  return next ? paperOrdersFor(net, next) : null
}

/** D-48 (REQ-078 AC-13): the contract ids of the legs that have an Exit waiting in Drafts Mode: the leg is still there but
 *  holds fewer lots than the net position (a partial Exit; a whole Exit leaves no leg). A texts-only comparison of the
 *  page's own copies, no number is formed. */
export function stagedExitIds(net, legs) {
  const held = new Map((net ?? []).map((l) => [l.contract_id, l.lots]))
  const kept = new Map() // the lots kept per contract, summed over its rows (1 + 1 against 2 held is no Exit)
  for (const l of legs ?? []) if (held.has(l.contract_id)) kept.set(l.contract_id, (kept.get(l.contract_id) ?? 0) + (Number.isInteger(l.lots) ? l.lots : 0))
  return [...kept].filter(([id, lots]) => lots < held.get(id)).map(([id]) => id)
}

/** R-11: a leg is the book's paper fill while its entry and its time are still the ones the net position loaded. */
export const paperFillKey = (l) => [l?.contract_id, l?.planned_entry, l?.captured_at].join('|') // an identity key, never shown
