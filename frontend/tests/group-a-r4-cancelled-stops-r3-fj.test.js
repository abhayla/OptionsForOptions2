// Group A finding R4 (28 Nov, Opus review of the round-2 order paths; ADR-330 (48)): no page read `cancelled_stops`. On this head the builder's exit path reads it (Lane FJ item 2);
// this file proves it from the Positions-list side too and closes the path that still missed it: a MOVE (exit + entry in one post) whose answer was unknown and was then found stored by a re-read
// (its reply was never read, so what happened to the stop is not known: the unreadable sentence). Positions and the Alerts door post exit rows only, so they can never carry a move.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import { STOP_REPLY_UNREADABLE_TEXT } from '@/lib/tracking'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'

const { posts, adv, t, S } = H
beforeEach(H.setup)
afterEach(H.teardown)
const LINE = 'The stop on NIFTY 22800 CE (level 120.00) was removed with the move; set a new one on the new leg.'
const ok = (reply) => () => Promise.resolve({ data: reply })

// a move: leg 784 (a short leg) is taken out and a lot is added on leg 753, in one "Review and add"
async function stageMove(w) {
  const s = S(w)
  s.setLegs(s.legs.filter((l) => l.contract_id !== 784).map((l) => (l.contract_id === 753 ? { ...l, lots: l.lots + 1 } : l)))
  await flushPromises()
  await t(w, 'paper-review').trigger('click')
  await flushPromises()
  const tick = t(w, 'paper-not-live-ack')
  if (tick.exists() && !tick.element.checked) await tick.setValue(true)
  await t(w, 'paper-confirm-button').trigger('click')
  await flushPromises(); await adv(100)
}

describe('R4: the builder reads cancelled_stops', () => {
  it('a move answered 201 with cancelled_stops: the line is on the page', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = ok({ orders: [{ id: 5 }], cancelled_stops: [{ leg: 'NIFTY 22800 CE', contract: 784, level: '120.00' }] })
    const w = await H.showBuilder()
    await stageMove(w)
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.orders.map((o) => o.kind).sort()).toContain('exit')
    expect(t(w, 'stop-offer-cancelled').text()).toBe(LINE)
  })
  it('a move whose answer was unknown and is found stored by a re-read: the unreadable-reply sentence is on the page (never silence)', async () => {
    const w = await H.showBuilder()
    await stageMove(w)
    expect(posts()).toHaveLength(1)
    expect(JSON.parse(globalThis.localStorage.getItem('ofo.exitUnknown'))['1'].move).toBe(true)
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 784).net_quantity = 0; d.positions.find((p) => p.contract_id === 753).net_quantity = 130 }) })
    await adv(WINDOW + 10000)
    expect(globalThis.localStorage.getItem('ofo.exitUnknown') ?? '').not.toContain('"1"')
    expect(t(w, 'stop-offer-reply-unreadable').text()).toBe(STOP_REPLY_UNREADABLE_TEXT)
  })
})

describe('R4: Positions and the Alerts door send exit rows only', () => {
  it('the exit post carries no entry row, so a move cannot come from this list', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = ok({ orders: [{ id: 1 }], cancelled_stops: [] })
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.orders.every((o) => o.kind === 'exit')).toBe(true)
  })
})
