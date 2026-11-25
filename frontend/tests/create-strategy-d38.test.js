// D-38 (GC-ICLIVE-D): Create Strategy step 4 COUNTED, and a timed-out step keeps what the user picked.
// BEFORE (21 Nov code, this file's own first run, library of 3 templates / 7 legs, 6 distinct contracts):
//   planned-entry requests = 3 (one per card, 7 ids asked in all), outcome requests = 3, all cards priced together.
// AFTER: ONE planned-entry request for the distinct contracts of every card (chunks of at most 20, the route's limit),
// then one outcome request per card, started together. Each card shows the same numbers as before.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'

const posts = []
let inFlight = 0
let maxInFlight = 0
let plannedFails = null
const leg = (action, instrument, strike_steps) => ({ action, instrument, strike_steps, expiry_slot: 'near', quantity_multiplier: 1 })
const TEMPLATES = { templates: [
  { id: 'bull_call_spread', name: 'Bull Call Spread', description: 'd', level: 'Beginner', views: ['bullish'], objectives: ['directional'], legs: [leg('BUY', 'CE', 0), leg('SELL', 'CE', 2)] },
  { id: 'cash_secured_put', name: 'Cash Secured Put', description: 'd', level: 'Intermediate', views: ['bullish'], objectives: ['income'], legs: [leg('SELL', 'PE', -2)] },
  { id: 'iron_condor', name: 'Iron Condor', description: 'd', level: 'Advanced', views: ['range-bound'], objectives: ['income'],
    legs: [leg('SELL', 'PE', -1), leg('BUY', 'PE', -3), leg('SELL', 'CE', 1), leg('BUY', 'CE', 3)] },
] }
const ct = (token, type, strike) => ({ contract_id: token, exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike, lot_size: 65, symbol: `NIFTY${strike}${type}` })
const CONTRACTS = [ct(1, 'PE', '22600.00'), ct(2, 'PE', '22700.00'), ct(3, 'CE', '22800.00'), ct(4, 'PE', '22800.00'),
  ct(5, 'CE', '22900.00'), ct(6, 'CE', '23000.00'), ct(7, 'CE', '23100.00'), ct(8, 'PE', '22500.00')]
const SUMMARY = { what_can_i_lose: 'L', what_can_i_make: 'M', where_do_i_start_losing: 'S', max_profit: '6175.00', max_loss: '-6825.00', max_profit_display: '+6,175', max_loss_display: '−6,825', breakevens_display: ['22,905 (+0.2%)'],
  max_profit_unlimited: false, max_loss_unlimited: false, breakevens: ['22905.00'], lower_be: null, upper_be: '22905.00', risk_boundaries: [] }
const SERVED = { 'limits.range_step': '100', 'limits.range_cap_nifty': '3000', 'limits.range_cap_sensex': '9000' }

const later = (v) => new Promise((resolve) => setTimeout(() => resolve(v), 5))
async function counted(v) { inFlight += 1; maxInFlight = Math.max(maxInFlight, inFlight); const r = await later(v); inFlight -= 1; return r }

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => {
      if (url === '/settings') return Promise.resolve({ data: { groups: [{ name: 'Limits', settings: Object.entries(SERVED).map(([key, value]) => ({ key, value })) }], charges: null } })
      if (url === '/strategy-templates') return Promise.resolve({ data: TEMPLATES })
      if (url === '/catalogue/NIFTY/expiries') return Promise.resolve({ data: { underlying: 'NIFTY', today: '2026-10-10', expiries: ['2026-10-13'] } })
      if (url.startsWith('/catalogue/NIFTY/contracts')) return Promise.resolve({ data: { underlying: 'NIFTY', contracts: CONTRACTS } })
      if (url === '/market/indices') return Promise.resolve({ data: { state: 'LIVE', indices: [{ underlying: 'NIFTY', value: '22812.40' }] } })
      return Promise.reject(new Error(url))
    },
    post: (url, body) => {
      posts.push({ url, body })
      if (url === '/strategies/planned-entry') {
        if (plannedFails) return Promise.reject(plannedFails)
        return counted({ data: { entries: body.instrument_ids.map((id) => ({ exchange_segment: 'NSE_FO', exchange_token: Number(id.split(':')[1]),
          planned_entry: '120.50', captured_at: '2026-10-13T09:20:00+05:30' })) } })
      }
      return counted({ data: { summary: SUMMARY, margin: null } })
    },
  } }
})
import { routes } from '@/router/routes'

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push('/strategies/create-strategy')
  await router.isReady()
  const w = mount({ template: '<router-view />' }, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return w
}
const pick = async (w, testid, key) => { await w.find(`[data-testid="${testid}"][data-key="${key}"]`).trigger('click'); await flushPromises() }
async function toResults(w) {
  await w.find('[data-testid="path-guided"]').trigger('click')
  await pick(w, 'objective', 'know')
  await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
  await flushPromises()
  await w.find('[data-testid="show-strategies"]').trigger('click')
  await new Promise((r) => setTimeout(r, 60))
  await flushPromises()
}
beforeEach(() => { posts.length = 0; inFlight = 0; maxInFlight = 0; plannedFails = null })

describe('D-38 Create Strategy step 4: requests counted', () => {
  it('asks the planned entries ONCE for the distinct contracts of all cards, then one outcome per card, together', async () => {
    const w = await mountPage()
    await toResults(w)
    const cards = w.findAll('[data-testid="strategy-card"]')
    expect(cards.length).toBeGreaterThanOrEqual(2)
    const entries = posts.filter((p) => p.url === '/strategies/planned-entry')
    const outcomes = posts.filter((p) => p.url === '/strategies/outcome')
    const asked = entries.flatMap((e) => e.body.instrument_ids)
    console.log(`D38 STEP4 cards=${cards.length} planned-entry requests=${entries.length} ids asked=${asked.length} distinct=${new Set(asked).size} outcome requests=${outcomes.length} max in flight=${maxInFlight}`)
    expect(new Set(asked).size).toBe(asked.length) // no contract asked twice
    expect(entries.length).toBe(1)
    expect(outcomes.length).toBe(cards.length)
    expect(maxInFlight).toBeGreaterThanOrEqual(2) // the outcomes are not one after another
    for (const e of entries) expect(e.body.instrument_ids.length).toBeLessThanOrEqual(20)
  })

  it('every card keeps its legs, planned entries and the engine numbers as sent', async () => {
    const w = await mountPage()
    await toResults(w)
    const csp = w.find('[data-testid="strategy-card"][data-template-id="cash_secured_put"]')
    expect(csp.find('[data-testid="card-max-loss"]').text()).toBe('−6,825')
    const outcome = posts.filter((p) => p.url === '/strategies/outcome').map((p) => p.body.legs.map((l) => [l.instrument_id, l.action, l.lots, l.planned_entry, l.captured_at]))
    expect(outcome.every((legs) => legs.every((l) => l[3] === '120.50' && l[4] === '2026-10-13T09:20:00+05:30'))).toBe(true)
  })
})

describe('D-38 a step that timed out says so and keeps what was picked', () => {
  it('a planned-entry call that hit the client limit says it took too long; the view, expiry and cards stay', async () => {
    plannedFails = { message: 'x', parts: null, status: null, code: 'ECONNABORTED' }
    const w = await mountPage()
    await toResults(w)
    const err = w.find('[data-testid="create-error"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toContain('took too long')
    expect(w.find('[data-testid="create-strategy"]').attributes('data-step')).toBe('4')
    expect(w.findAll('[data-testid="strategy-card"]').length).toBeGreaterThanOrEqual(2) // the unpriced cards, never wiped
  })
})
