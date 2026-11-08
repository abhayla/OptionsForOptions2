// Compare: "Exit the whole strategy" prepares an exit basket for every open leg (no server call of its own, no order placed),
// and a prepare failure that never reached the server says so. Also: no Vue prop warning for the drawer's `client` prop.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { routerKey } from 'vue-router'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} update() {} } }))

import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import api from '@/services/api'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const EXIT = adj02.approaches.find((a) => a.id === 'A-31') // the real full exit: after_legs [], one closing trade per open leg
const PART = adj02.approaches.find((a) => a.id === 'A-28') // close_part: the new position still has legs
const contractsOf = (list) => list.map((l, i) => ({
  contract_id: 100 + i, symbol: l.tradingsymbol, expiry: l.expiry, instrument_type: l.type, strike: l.strike, lot_size: 65, exchange_segment: 'NFO', exchange_token: 900 + i,
}))

function client({ contractsFail = false, noContracts = false } = {}) {
  return {
    post: vi.fn(async () => ({ data: adj02 })),
    get: vi.fn(async (url) => {
      if (url.startsWith('/catalogue')) {
        if (contractsFail) throw Object.assign(new Error('x'), { parts: { what_happened: 'The contract list could not be read.' } })
        return { data: { contracts: noContracts ? [] : contractsOf([...EXIT.trades, ...PART.after_legs]) } }
      }
      if (url.endsWith('/tracking')) throw Object.assign(new Error('x'), { status: 404 })
      return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
    }),
  }
}
async function prepare(id, opts) {
  const c = client(opts)
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client: c } })
  await flushPromises()
  await t(w, 'adjust-pick').setValue(id)
  await t(w, 'adjust-open').trigger('click')
  await flushPromises()
  return { w, c }
}

describe('Compare: exit the whole strategy', () => {
  it('the fixture is a real full exit', () => {
    expect(EXIT.after_legs).toEqual([])
    expect(EXIT.trades.length).toBeGreaterThan(0)
  })

  it('emits prepare with one closing leg per open leg, flagged as an exit, and no error', async () => {
    const { w, c } = await prepare('A-31')
    const ev = w.emitted('prepare')
    expect(ev).toHaveLength(1)
    const p = ev[0][0]
    expect(p.exit).toBe(true)
    expect(p.underlying).toBe('NIFTY')
    expect(p.legs).toHaveLength(EXIT.trades.length)
    EXIT.trades.forEach((tr, i) => {
      expect(p.legs[i]).toMatchObject({ symbol: tr.tradingsymbol, action: tr.action, lots: tr.lots, planned_entry: tr.price })
    })
    expect(p.basketLegs).toBe(EXIT.trades.length)
    expect(w.text()).not.toContain('could not get an answer from the server')
    expect(c.post).toHaveBeenCalledTimes(1) // the compare read only: no order, no second POST
  })

  it('an approach that keeps legs (new legs, or a partial close) keeps the old path', async () => {
    const { w } = await prepare('A-28')
    const p = w.emitted('prepare')[0][0]
    expect(p.exit).toBe(false)
    expect(p.legs).toHaveLength(PART.after_legs.length)
    expect(p.legs[0]).toMatchObject({ symbol: PART.after_legs[0].tradingsymbol, action: PART.after_legs[0].side, lots: PART.after_legs[0].lots })
  })

  it('a failing contracts read shows the read error and prepares nothing', async () => {
    const { w } = await prepare('A-31', { contractsFail: true })
    expect(w.emitted('prepare')).toBeUndefined()
    expect(w.text()).toContain('The contract list could not be read.')
  })

  it('a trade with no contract fails locally with its own text, not the server-failure text', async () => {
    const { w } = await prepare('A-31', { noContracts: true })
    expect(w.emitted('prepare')).toBeUndefined()
    expect(w.text()).toContain('This approach could not be turned into a basket.')
    expect(w.text()).not.toContain('could not get an answer from the server')
  })
})

describe('TrackingPanel mounts its drawer without a Vue prop warning (issue 27)', () => {
  afterEach(() => vi.restoreAllMocks())
  it('the default api client (a function object) passes the client prop check', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    api.defaults.adapter = async (config) => { throw Object.assign(new Error('x'), { config, response: { status: 404, data: {} } }) }
    const w = mount(TrackingPanel, { props: { savedId: 72 }, global: { provide: { [routerKey]: { push: vi.fn() } } } })
    await flushPromises()
    const msgs = warn.mock.calls.map((a) => String(a[0]))
    expect(msgs.filter((m) => m.includes('Invalid prop'))).toEqual([])
    w.unmount()
  })
})
