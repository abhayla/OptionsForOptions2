// Lane N A4/A5/B1 (27 Nov 2026): ONE price-state source (priceState.priceNow / usePriceFreshness.now) and ONE as-of wording.
// ADR-330 (28): Add to Paper on a not-live price shows the tick box and the line; ADR-212 / ADR-330 (36): the close time.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { priceNow, usePriceFreshness, pausedText } from '@/lib/priceState'
import { withAsOf } from '@/lib/paperList'
import { confirmPaperName } from './helpers/paperName'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const CLOSE = '2026-11-27T15:30:00+05:30'
const LATE = '2026-11-27T15:35:41+05:30'
const FEED = '2026-11-27T11:02:10+05:30'
const open = (extra = {}) => ({ market_closed: false, last_price_at: FEED, closed_prices_text: null, ...extra })
const closed = (extra = {}) => ({ market_closed: true, last_price_at: CLOSE, closed_prices_text: null, ...extra })

describe('priceNow: one state for every not-live case', () => {
  it('live: open market, computed, feed not reconnecting', () => {
    expect(priceNow({ reply: open(), pageState: 'computed' }).kind).toBe('live')
  })
  it('after close: last_close with the reply time', () => {
    const n = priceNow({ reply: closed(), pageState: 'computed' })
    expect(n).toMatchObject({ kind: 'last_close', at: CLOSE })
    expect(n.text).toContain('15:30:00')
  })
  it('after close with the reply missing market_closed: the index answer decides (the A4 gap)', () => {
    const n = priceNow({ reply: open(), answer: { market_closed: true, last_price_at: CLOSE }, pageState: 'computed' })
    expect(n.kind).toBe('last_close')
    expect(n.at).toBe(CLOSE)
  })
  it('pre-open (calendar closed, no price time yet): last_close with no time clause', () => {
    const n = priceNow({ reply: closed({ last_price_at: null }), pageState: 'computed' })
    expect(n.kind).toBe('last_close')
    expect(n.at).toBeNull()
    expect(n.text).not.toContain('Time not available')
  })
  it('feed down in hours: stale with the feed time', () => {
    const n = priceNow({ reply: open(), pageState: 'computed', reconnecting: true })
    expect(n).toMatchObject({ kind: 'stale', at: FEED })
    expect(n.text).toBe(pausedText(FEED))
    expect(priceNow({ reply: open(), pageState: 'stale' }).kind).toBe('stale')
  })
  it('time missing: stale says so without a time clause, never "Time not available"', () => {
    const n = priceNow({ reply: open({ last_price_at: null }), pageState: 'stale' })
    expect(n.kind).toBe('stale')
    expect(n.at).toBeNull()
    expect(n.text).toBe('Paper P&L paused - prices not live')
  })
  it('partial reply while loading: closed, but the wrong 15:35:41 is never the banner time', () => {
    const n = priceNow({ reply: closed({ last_price_at: LATE }), pageState: 'loading' })
    expect(n.kind).toBe('last_close')
    expect(n.at).toBeNull()
  })
  it('not connected / no reply: unavailable', () => {
    expect(priceNow({ reply: null, pageState: 'not-connected' }).kind).toBe('unavailable')
    expect(priceNow({ reply: null, pageState: 'loading' }).kind).toBe('unavailable')
  })
  it('the composable exposes the same answer as `now` and live follows it', () => {
    const f = usePriceFreshness({ reply: () => closed(), pageState: () => 'computed' })
    expect(f.now.value.kind).toBe('last_close')
    expect(f.live.value).toBe(false)
  })
})

describe('one as-of wording: no "Time not available" inside a sentence', () => {
  it('pausedText without a readable time states the reason only', () => {
    expect(pausedText(null)).toBe('Paper P&L paused - prices not live')
    expect(pausedText('garbage')).toBe('Paper P&L paused - prices not live')
    expect(pausedText(CLOSE)).toBe('Paper P&L paused - prices not live, as of 27 Nov 2026, 15:30:00 IST')
  })
  it('withAsOf keeps the sentence as sent without a time', () => {
    expect(withAsOf('Paper P&L paused - prices not live', null)).toBe('Paper P&L paused - prices not live')
  })
})

const CURRENT = { id: 7, revision: 3, name: '"Condor"' }
const leg = (id, at) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: 100 + id, lot_size: 65, action: 'SELL', lots: 1, expiry: '2026-12-03', strike: '22800.00', instrument_type: 'CE', planned_entry: '112.40', captured_at: at })
async function addToPaper(props) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(SaveDraftBar, { props: { legs: [leg(1, null)], current: CURRENT, ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  await w.get('[data-testid="add-to-paper"]').trigger('click')
  await flushPromises()
  await confirmPaperName(w)
  return w
}
beforeEach(() => { calls.length = 0; answers = { 'GET /strategies': { strategies: [] } } })

describe('Add to Paper in every state (the page passes priceNow into the bar)', () => {
  const states = [
    ['after close', { pricesLive: false, priceAsOf: CLOSE }, 'as of 15:30.'],
    ['pre-open, time unknown', { pricesLive: false, priceAsOf: '' }, 'captured price.'],
    ['feed down in hours', { pricesLive: false, priceAsOf: FEED }, 'as of 11:02.'],
  ]
  for (const [name, props, tail] of states) {
    it(`${name}: tick box shown, Confirm waits for it, line ends "${tail}"`, async () => {
      const w = await addToPaper(props)
      expect(w.get('[data-testid="paper-not-live"]').text().endsWith(tail)).toBe(true)
      expect(w.get('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeDefined()
      w.unmount()
    })
  }
  it('the request carries prices_not_live_confirmed only when the line was shown and ticked', async () => {
    answers['POST /paper/strategies/7/orders'] = { strategy_id: 7, orders: [] }
    const w = await addToPaper({ pricesLive: false, priceAsOf: CLOSE })
    await w.get('[data-testid="paper-not-live-ack"]').setValue(true)
    await w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    const post = calls.find((c) => c.method === 'POST' && c.url === '/paper/strategies/7/orders')
    expect(post.body.prices_not_live_confirmed).toBe(true)
    w.unmount()
  })
  it('live: the request has no prices_not_live_confirmed', async () => {
    answers['POST /paper/strategies/7/orders'] = { strategy_id: 7, orders: [] }
    const w = await addToPaper({ pricesLive: true })
    await w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    const post = calls.find((c) => c.method === 'POST' && c.url === '/paper/strategies/7/orders')
    expect('prices_not_live_confirmed' in post.body).toBe(false)
    w.unmount()
  })
  it('live: no tick box, Confirm is active', async () => {
    const w = await addToPaper({ pricesLive: true })
    expect(w.find('[data-testid="paper-not-live"]').exists()).toBe(false)
    expect(w.get('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
})
