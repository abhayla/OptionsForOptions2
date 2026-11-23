// GC-TP step 3b1 CORE (ADR-207 (2), REQ-109 AC-9; F-65 structural fix): paperOrdersFor(net, edited) is the ONE function that
// turns a Drafts Mode edit into paper orders. Proven on the REAL strategy 63 book after its roll (repo fixture
// tests/fixtures/paper/strategy-63-roll.json, measured live 2026-10-29): +65 22600 PE, -65 22700 PE, +65 23000 CE,
// -65 22950 CE, 22900 CE closed (net 0). Netting is PER CONTRACT, so stepping the short 22950 CE onto 23000 CE (already held
// long) closes both contracts: two exits, never an add.
import { describe, it, expect } from 'vitest'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'
import { paperOrdersFor, netLegsFromBook } from '@/lib/paperDrafts'

const LOT = 65
// the catalogue rows of the book's contracts (contract_id, lot size, instrument id): what the page reads for the expiry
const CATALOGUE = BOOK.positions.map((p, i) => ({
  contract_id: p.contract_id, lot_size: LOT, exchange_segment: 'NFO', exchange_token: 9000 + i, symbol: `NIFTY${p.strike}${p.instrument}`,
  expiry: p.expiry, instrument_type: p.instrument, strike: p.strike,
}))
const net = () => netLegsFromBook(BOOK, CATALOGUE)
const ID = { pe22600: 5572, pe22700: 5576, ce22900: 5583, ce23000: 5587, ce22950: 5585 }
const strip = (orders) => orders.map(({ side, contract_id, quantity, kind }) => ({ side, contract_id, quantity, kind }))

describe('netLegsFromBook (the net position as builder legs)', () => {
  it('loads only the open contracts, lots = |net| / lot size, side from the sign, entry = the average text', () => {
    const legs = net()
    expect(legs.map((l) => [l.contract_id, l.action, l.lots, l.planned_entry])).toEqual([
      [ID.pe22600, 'BUY', 1, '72.60'], [ID.pe22700, 'SELL', 1, '102.00'], [ID.ce23000, 'BUY', 1, '80.95'], [ID.ce22950, 'SELL', 1, '108.00'],
    ])
    expect(legs.every((l) => l.lot_size === LOT && typeof l.instrument_id === 'string')).toBe(true)
  })
  it('fails closed (null) when a contract is missing from the catalogue or does not divide into whole lots', () => {
    expect(netLegsFromBook(BOOK, CATALOGUE.slice(1))).toBeNull()
    expect(netLegsFromBook(BOOK, CATALOGUE.map((c) => ({ ...c, lot_size: 50 })))).toBeNull()
  })
})

describe('paperOrdersFor(net, edited) on the real strategy 63 book', () => {
  it('(a) stepping the short 22950 CE up onto the held long 23000 CE gives exactly two EXITS: BUY 65 22950 CE, SELL 65 23000 CE', () => {
    const edited = net().map((l) => (l.contract_id === ID.ce22950 ? { ...CATALOGUE_LEG(ID.ce23000), action: 'SELL', lots: 1 } : l))
    expect(strip(paperOrdersFor(net(), edited))).toEqual([
      { side: 'SELL', contract_id: ID.ce23000, quantity: 65, kind: 'exit' },
      { side: 'BUY', contract_id: ID.ce22950, quantity: 65, kind: 'exit' },
    ].sort(byContractOrder(net())))
  })
  it('(b) lots 1 -> 2 on 22600 PE gives one BUY 65 add', () => {
    const edited = net().map((l) => (l.contract_id === ID.pe22600 ? { ...l, lots: 2 } : l))
    expect(strip(paperOrdersFor(net(), edited))).toEqual([{ side: 'BUY', contract_id: ID.pe22600, quantity: 65, kind: 'add' }])
  })
  it('(c) removing the 22700 PE leg gives one BUY 65 exit', () => {
    const edited = net().filter((l) => l.contract_id !== ID.pe22700)
    expect(strip(paperOrdersFor(net(), edited))).toEqual([{ side: 'BUY', contract_id: ID.pe22700, quantity: 65, kind: 'exit' }])
  })
  it('(d) no edit gives no orders', () => {
    expect(paperOrdersFor(net(), net())).toEqual([])
  })
  it('(e) crossing zero on one contract: an exit of the held quantity plus an add of the rest on the new side', () => {
    // the long 22600 PE (+65) becomes a 2-lot SELL (-130): exit SELL 65 (to zero), then add SELL 130 (the rest of the change)
    const edited = net().map((l) => (l.contract_id === ID.pe22600 ? { ...l, action: 'SELL', lots: 2 } : l))
    expect(strip(paperOrdersFor(net(), edited))).toEqual([
      { side: 'SELL', contract_id: ID.pe22600, quantity: 65, kind: 'exit' },
      { side: 'SELL', contract_id: ID.pe22600, quantity: 130, kind: 'add' },
    ])
  })
  it('a smaller same-side position is one exit of the difference; a new contract is an add; exits come before adds', () => {
    const two = net().map((l) => (l.contract_id === ID.pe22600 ? { ...l, lots: 3 } : l))
    const edited = [...two.map((l) => (l.contract_id === ID.pe22600 ? { ...l, lots: 1 } : l)), { ...CATALOGUE_LEG(ID.ce22900), action: 'BUY', lots: 2 }]
      .filter((l) => l.contract_id !== ID.ce22950)
    expect(strip(paperOrdersFor(two, edited))).toEqual([
      { side: 'SELL', contract_id: ID.pe22600, quantity: 130, kind: 'exit' },
      { side: 'BUY', contract_id: ID.ce22950, quantity: 65, kind: 'exit' },
      { side: 'BUY', contract_id: ID.ce22900, quantity: 130, kind: 'add' },
    ])
  })
  it('two edited legs on one contract are netted before the diff (BUY 2 + SELL 1 of 22600 PE = +65: no order)', () => {
    const extra = { ...net()[0], id: 'dup', action: 'SELL', lots: 1 }
    const edited = [...net().map((l) => (l.contract_id === ID.pe22600 ? { ...l, lots: 2 } : l)), extra]
    expect(paperOrdersFor(net(), edited)).toEqual([])
  })
  it('every order carries lots and lot size for the confirm list (quantity = lots x lot size, units not money)', () => {
    const edited = net().map((l) => (l.contract_id === ID.pe22600 ? { ...l, lots: 3 } : l))
    const [o] = paperOrdersFor(net(), edited)
    expect([o.lots, o.lot_size, o.quantity]).toEqual([2, 65, 130])
  })
  it('fails closed (null) on a leg without an integer contract id or lot size', () => {
    expect(paperOrdersFor(net(), [...net(), { contract_id: null, action: 'BUY', lots: 1, lot_size: 65 }])).toBeNull()
    expect(paperOrdersFor(net(), [...net(), { contract_id: 1, action: 'BUY', lots: 1, lot_size: null }])).toBeNull()
    expect(paperOrdersFor(net(), [...net(), { contract_id: 1, action: 'HOLD', lots: 1, lot_size: 65 }])).toBeNull()
  })
})

function CATALOGUE_LEG(contractId) {
  const c = CATALOGUE.find((x) => x.contract_id === contractId)
  return { id: `new-${contractId}`, contract_id: c.contract_id, lot_size: c.lot_size, instrument_id: `${c.exchange_segment}:${c.exchange_token}`, strike: c.strike, instrument_type: c.instrument_type, expiry: c.expiry }
}
// exits are listed in the order the contracts appear in the net position
function byContractOrder(legs) {
  const at = (id) => legs.findIndex((l) => l.contract_id === id)
  return (a, b) => at(a.contract_id) - at(b.contract_id)
}

// REQ-159 AC-6 / REQ-058 (Q238): buy legs first. One rule on the whole basket: BUY exits (short buy-backs), BUY adds (new
// hedges), SELL exits (old hedges), SELL adds (new shorts); stable within each group. Real shapes seen 2026-11-23.
describe('paperOrdersFor puts every BUY before every SELL (REQ-159 AC-6)', () => {
  const L = (contract_id, action, lots = 1) => ({ contract_id, action, lots, lot_size: 25 })
  const seq = (orders) => orders.map((o) => `${o.side} ${o.contract_id} ${o.kind}`)
  const buysFirst = (orders) => orders.findLastIndex((o) => o.side === 'BUY') < orders.findIndex((o) => o.side === 'SELL')
  it('put-spread roll: BUY short buy-back, BUY new hedge, SELL old hedge, SELL new short', () => {
    const got = paperOrdersFor([L(25300, 'BUY'), L(25400, 'SELL')], [L(25400, 'BUY'), L(25500, 'SELL')])
    expect(seq(got)).toEqual(['BUY 25400 exit', 'BUY 25400 add', 'SELL 25300 exit', 'SELL 25500 add'])
  })
  it('call-spread shift: both BUYs before both SELLs', () => {
    const got = paperOrdersFor([L(25600, 'SELL'), L(25700, 'BUY')], [L(25650, 'SELL'), L(25750, 'BUY')])
    expect(seq(got)).toEqual(['BUY 25600 exit', 'BUY 25750 add', 'SELL 25700 exit', 'SELL 25650 add'])
  })
  it('close-tested-spread: the short is bought back before the hedge is sold', () => {
    expect(seq(paperOrdersFor([L(25300, 'BUY'), L(25400, 'SELL')], []))).toEqual(['BUY 25400 exit', 'SELL 25300 exit'])
  })
  it('two-expiry diagonal roll: ids differ per expiry, same rule', () => {
    const got = paperOrdersFor([L(2, 'BUY'), L(1, 'SELL')], [L(4, 'BUY'), L(3, 'SELL')])
    expect(seq(got)).toEqual(['BUY 1 exit', 'BUY 4 add', 'SELL 2 exit', 'SELL 3 add'])
  })
  it('a plain entry of four adds lists the BUYs first', () => {
    const got = paperOrdersFor([], [L(1, 'SELL'), L(2, 'SELL'), L(3, 'BUY'), L(4, 'BUY')])
    expect(seq(got)).toEqual(['BUY 3 add', 'BUY 4 add', 'SELL 1 add', 'SELL 2 add'])
    expect(buysFirst(got)).toBe(true)
  })
  it('is stable within a group (contract order is kept)', () => {
    // net: short 9, short 7, long 8 -> exits: BUY 9, BUY 7 (their order kept), then SELL 8
    expect(seq(paperOrdersFor([L(9, 'SELL'), L(7, 'SELL'), L(8, 'BUY')], []))).toEqual(['BUY 9 exit', 'BUY 7 exit', 'SELL 8 exit'])
  })
})
