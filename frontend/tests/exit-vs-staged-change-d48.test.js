// D-48 review round 1 (Opus): a row Exit on a contract that has a staged change other than an exit (moved away by Change expiry or a
// strike step, lots raised) must not combine with it. Real case: a 2-lot trade, Change expiry A -> A', then type 1 in A's lots box and Exit:
// legs [A' 2, A 1], orders exit 1 of A + add 2 of A', the trade grows 2 -> 3 lots under a dialog called "Exit". The ONE door is
// legsAfterExit (every row Exit passes it); the panel shows the same reason beforehand (ADR-328 (4)). Finding 5: stagedExitIds sums lots.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { EXIT_BLOCKED_BY_CHANGE, legsAfterExit, paperOrdersFor, stagedChangeIds, stagedExitIds } from '@/lib/paperDrafts'

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
  it('exit-only states still work: untouched, partial exit, whole exit, another contract moved', () => {
    expect(stagedChangeIds(net, [A])).toEqual([])
    expect(legsAfterExit(net, [A], 1, 1).map((l) => l.lots)).toEqual([1])
    expect(legsAfterExit(net, [{ ...A, lots: 1 }], 1, 2).map((l) => l.lots)).toEqual([])
    const B = { ...A, id: 'paper-2', contract_id: 2, instrument_id: 'NSE_FO:2' }
    expect(legsAfterExit([A, B], [moved, B], 2, 1).map((l) => l.lots)).toEqual([2, 1])
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
