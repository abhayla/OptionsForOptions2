// D-48 review round 1 (Opus): a row Exit on a contract that has a staged change other than an exit (moved away by Change expiry or a
// strike step, lots raised) must not combine with it. Real case: a 2-lot trade, Change expiry A -> A', then type 1 in A's lots box and Exit:
// legs [A' 2, A 1], orders exit 1 of A + add 2 of A', the trade grows 2 -> 3 lots under a dialog called "Exit". The ONE door is
// legsAfterExit (every row Exit passes it); the panel shows the same reason beforehand (ADR-328 (4)). Finding 5: stagedExitIds sums lots.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { EXIT_BLOCKED_BY_CHANGE, exitOnlyOrders, legsAfterExit, paperOrdersFor, rowExitBlocked, stagedChangeIds, stagedExitIds } from '@/lib/paperDrafts'
import { admitLegs } from '@/lib/legDoor'

const A = { id: 'paper-1', contract_id: 1, instrument_id: 'NSE_FO:1', action: 'SELL', lots: 2, lot_size: 65, strike: 22800, instrument_type: 'CE', expiry: '2026-11-03' }
const net = [A]
const moved = { ...A, contract_id: 999001, instrument_id: 'NSE_FO:999001', expiry: '2026-11-10' } // id stays paper-1: the same row, moved
const position = (id, lots) => ({ contract_id: id, contract_text: `NIFTY C${id}`, net_quantity: -lots * 65, lots, average_text: '10', ltp_text: '9', booked_text: '0', unbooked_text: '0', total_text: '0' })

describe('a row Exit never combines with a staged change on its contract', () => {
  it("the reviewer's case: moved A -> A', Exit 1 of A produces no legs and no orders", () => {
    expect(stagedChangeIds(net, [moved])).toEqual([1])
    expect(legsAfterExit(net, [moved], 1, 1)).toBeNull()
  })
  it('a strike step (the same row id on another contract) is the same class', () => {
    expect(legsAfterExit(net, [{ ...A, contract_id: 77, instrument_id: 'NSE_FO:77', strike: 22850 }], 1, 1)).toBeNull()
  })
  it('lots raised above the net position is a staged add: blocked too', () => {
    expect(legsAfterExit(net, [{ ...A, lots: 3 }], 1, 1)).toBeNull()
  })
  it('exit-only states still work: untouched, partial exit, whole exit, removed leg, 1 + 1 rows, lots 2 -> 1 -> 2', () => {
    expect(stagedChangeIds(net, [A])).toEqual([])
    expect(rowExitBlocked(net, [A], 1)).toBe(false)
    expect(legsAfterExit(net, [A], 1, 1).map((l) => l.lots)).toEqual([1])
    expect(legsAfterExit(net, [{ ...A, lots: 1 }], 1, 2).map((l) => l.lots)).toEqual([])
    const B = { ...A, id: 'paper-2', contract_id: 2, instrument_id: 'NSE_FO:2' }
    expect(legsAfterExit([A, B], [A], 1, 1).map((l) => l.lots)).toEqual([1]) // B removed (an exit waiting): A's Exit still allowed
    expect(legsAfterExit(net, [{ ...A, lots: 1 }, { ...A, id: 'x', lots: 1 }], 1, 1)).not.toBeNull() // 1 + 1 rows: no change
    expect(legsAfterExit(net, [{ ...A, lots: 1 }], 1, 1).map((l) => l.lots)).toEqual([1]) // lots 2 -> 1 (an exit waiting), then Exit 1 of the net 2
    expect(legsAfterExit(net, [{ ...A, lots: 2 }], 1, 1).map((l) => l.lots)).toEqual([1]) // 2 -> 1 -> 2 is untouched
  })
  // ADR-330 (49) (owner, 27 Nov 2026) replaces D-48 round 2's "a row Exit never carries an add": only the CHANGED leg's Exit is blocked;
  // an untouched leg's Exit exits that leg only (exitOnlyOrders: one exit row, none of the other legs' staged changes).
  it('another contract moved: only the moved leg is blocked; the untouched leg exits alone', () => {
    const B = { ...A, id: 'paper-2', contract_id: 2, instrument_id: 'NSE_FO:2' }
    expect(stagedChangeIds([A, B], [moved, B])).toEqual([1])
    expect(legsAfterExit([A, B], [moved, B], 1, 1)).toBeNull()
    expect(legsAfterExit([A, B], [moved, B], 2, 1)).not.toBeNull()
    expect(exitOnlyOrders([A, B], 2, 1).map((o) => [o.kind, o.contract_id])).toEqual([['exit', 2]])
  })
  it('a new staged leg C blocks no row Exit: it is not a held leg, and A exits alone', () => {
    const C = { ...A, id: 'new-c', contract_id: 3, instrument_id: 'NSE_FO:3', lots: 1 }
    expect(stagedChangeIds(net, [A, C])).toEqual([])
    expect(legsAfterExit(net, [A, C], 1, 1).map((l) => l.contract_id)).toEqual([1, 3]) // C stays staged beside A's remaining lot
    expect(exitOnlyOrders(net, 1, 1).map((o) => [o.kind, o.contract_id, o.lots])).toEqual([['exit', 1, 1]])
  })
  it('ATK-1: a move onto a held contract answered with Increase: the raised contract B is blocked; A (no rows left, indistinguishable from a removed leg) exits alone', async () => {
    const B = { ...A, id: 'paper-2', contract_id: 2, instrument_id: 'NSE_FO:2', lots: 1 }
    const mv = { ...A, instrument_id: 'NSE_FO:2', contract_id: 2, lots: 2 } // row paper-1 moved onto B
    const r = await admitLegs([B], [mv], { ask: async () => 'increase', maxLots: 100 })
    const legs = r.legs
    expect(legs.map((l) => l.id)).toEqual(['paper-2'])
    expect(legs[0].lots).toBe(3)
    expect(paperOrdersFor([A, B], legs).map((o) => o.kind)).toContain('add')
    expect(legsAfterExit([A, B], legs, 2, 1)).toBeNull() // B holds 3 lots against 1 held: its own change
    expect(stagedChangeIds([A, B], legs)).toEqual([2])
    expect(exitOnlyOrders([A, B], 1, 1).map((o) => [o.kind, o.contract_id])).toEqual([['exit', 1]]) // never the add of B
  })
  it('ATK-7: an adjustment roll (adjust- ids, no paper- id): any Exit posts that exit only, never the roll\'s add', () => {
    const roll = { ...A, id: 'adjust-0', contract_id: 9, instrument_id: 'NSE_FO:9', lots: 2 }
    expect(paperOrdersFor(net, [roll]).map((o) => o.kind)).toContain('add')
    expect(exitOnlyOrders(net, 1, 1).map((o) => o.kind)).toEqual(['exit'])
  })
  it('the panel row says why and sends nothing', async () => {
    const book = { strategy_id: 1, state: 'LIVE', total_text: '0', positions: [position(1, 2)], closed: [], orders: [] }
    const w = mount(PaperBookPanel, { props: { book, net, changedIds: [1] } })
    const btn = w.find('[data-testid="net-exit"]')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('title')).toBe(EXIT_BLOCKED_BY_CHANGE)
    expect(w.find('[data-testid="net-exit-reason"]').text()).toBe('This leg has a change waiting; review or discard it first.')
    await btn.trigger('click')
    expect(w.emitted('exit')).toBeUndefined()
  })
  it('and the row of an untouched contract is enabled', () => {
    const book = { strategy_id: 1, state: 'LIVE', total_text: '0', positions: [position(1, 2)], closed: [], orders: [] }
    const w = mount(PaperBookPanel, { props: { book, net, changedIds: [] } })
    expect(w.find('[data-testid="net-exit"]').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-testid="net-exit-reason"]').exists()).toBe(false)
  })
  it('without the door the orders would have grown the trade 2 -> 3 (why the door exists)', () => {
    const orders = paperOrdersFor(net, [moved, { ...A, lots: 1 }])
    expect(orders.map((o) => [o.kind, o.contract_id])).toEqual(expect.arrayContaining([['exit', 1], ['add', 999001]]))
  })
})

describe('stagedExitIds sums the lots of a contract (finding 5)', () => {
  it('two kept rows of 1 + 1 lots against 2 held are no exit', () => {
    expect(stagedExitIds([A], [{ ...A, lots: 1 }, { ...A, lots: 1 }])).toEqual([])
    expect(stagedExitIds([A], [{ ...A, lots: 1 }])).toEqual([1])
    expect(stagedExitIds([A], [{ ...A, lots: 1 }, { ...A, lots: 0 }])).toEqual([1])
  })
})
