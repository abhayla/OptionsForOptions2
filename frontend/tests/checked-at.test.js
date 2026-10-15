// W-077 AC-3 (REQ-039, ADR-088, issue #245): the unpriced, not-connected, error and refused states each show
// "Checked at <server answer time in IST>". Expected text is hand-computed: 03:50:05 UTC + 5:30 = 09:20:05 IST.
// The time is the SERVER's (answered_at, or the failed answer's Date header), never the browser's clock.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error || a?.__reject ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { mapError } from '@/services/api'

const STAMP = '2026-10-16T03:50:05Z'
const LINE = 'Checked at 16 Oct 2026, 09:20:05 IST'
const AT = '2026-10-08T09:20:09+05:30'
const DRAFT = {
  underlying: 'NIFTY',
  legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT }],
}

async function open(query = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const state = (w) => t(w, 'strategy-builder').attributes('data-state')
const withDraft = { draft: JSON.stringify(DRAFT) }

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-13'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': {
      underlying: 'NIFTY',
      contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }],
    },
  }
})
afterEach(() => vi.restoreAllMocks())

describe('Checked at on the four non-normal states', () => {
  it('not connected shows the answer time', async () => {
    answers['POST /strategies/outcome'] = { state: 'NOT_CONNECTED', status_label: 'x', legs: [], underlying: 'NIFTY', answered_at: STAMP }
    const w = await open(withDraft)
    expect(state(w)).toBe('not-connected')
    expect(t(w, 'checked-at').text()).toBe(LINE)
  })

  it('refused shows the answer time', async () => {
    answers['POST /strategies/outcome'] = { state: 'REFUSED', status_label: 'x', reason: 'r', legs: [], underlying: 'NIFTY', answered_at: STAMP }
    const w = await open(withDraft)
    expect(state(w)).toBe('refused')
    expect(t(w, 'checked-at').text()).toBe(LINE)
  })

  it('error shows the failed answer\'s server time', async () => {
    answers['POST /strategies/outcome'] = Object.assign(new Error('x'), { answered_at: STAMP })
    const w = await open(withDraft)
    expect(state(w)).toBe('error')
    expect(t(w, 'checked-at').text()).toBe(LINE)
  })

  it('error with no server time says so, never the browser time', async () => {
    answers['POST /strategies/outcome'] = new Error('x')
    const w = await open(withDraft)
    expect(t(w, 'checked-at').text()).toBe('Checked at Time not available')
  })

  it('mapError takes the time from the response Date header (Thu, 16 Oct 2026 03:50:05 GMT)', () => {
    const out = mapError({ response: { status: 500, headers: { date: 'Fri, 16 Oct 2026 03:50:05 GMT' }, data: {} } })
    expect(out.answered_at).toBe('2026-10-16T03:50:05.000Z')
    expect(mapError({ response: { status: 500, headers: {}, data: {} } }).answered_at).toBeUndefined()
  })

  it('unpriced shows the planned-entry answer time', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/SENSEX/expiries'] = { underlying: 'SENSEX', expiries: [] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = {
      underlying: 'NIFTY',
      contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }],
    }
    answers['POST /strategies/planned-entry'] = {
      answered_at: STAMP,
      entries: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, planned_entry: null, captured_at: null, source: null, reason_code: 'not_connected' }],
    }
    const w = await open()
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    await t(w, 'pick-type').setValue('CE')
    await t(w, 'pick-strike').setValue('22800.00')
    await t(w, 'pick-action').setValue('SELL')
    await t(w, 'pick-lots').setValue('1')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(state(w)).toBe('unpriced')
    expect(t(w, 'checked-at').text()).toBe(LINE)
  })

  it('the browser clock never moves the shown time', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.UTC(2031, 0, 1, 0, 0, 0))
    answers['POST /strategies/outcome'] = { state: 'NOT_CONNECTED', status_label: 'x', legs: [], underlying: 'NIFTY', answered_at: STAMP }
    const w = await open(withDraft)
    expect(t(w, 'checked-at').text()).toBe(LINE)
  })
})
