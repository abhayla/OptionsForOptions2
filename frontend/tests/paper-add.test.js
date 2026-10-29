// GC-TP step 2 (ADR-207 (1), REQ-109 AC-1; Sensibull Add to Drafts 166-173): "Add to Paper" in the builder's action row, the
// confirm list, the toast. The core: Confirm records ONE POST /paper/strategies/{id}/orders with one `open` order per ticked
// leg at the price shown in the list (the leg's entry price, or the one typed), and nothing else records a paper order.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import * as tracking from '@/lib/tracking'

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

const CAPTURED = '2026-10-29T10:00:00+05:30'
const mk = (id, contract_id, action, strike, type, price, over = {}) => ({
  id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id, lot_size: 65, action, lots: 1, expiry: '2026-11-03',
  strike, instrument_type: type, planned_entry: price, captured_at: CAPTURED, ...over,
})
// NIFTY short iron condor: entry prices 112.40 / 38.15 / 95.00 / 41.30
const CONDOR = () => [
  mk(1, 101, 'SELL', '22800.00', 'CE', '112.40'), mk(2, 102, 'BUY', '23000.00', 'CE', '38.15'),
  mk(3, 103, 'SELL', '22400.00', 'PE', '95.00'), mk(4, 104, 'BUY', '22200.00', 'PE', '41.30'),
]
const CURRENT = { id: 7, revision: 3, name: '"Condor"' }
const BOOK = { strategy_id: 7, orders: [] }
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const posts = () => calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))

async function bar(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategies/my-strategies', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(SaveDraftBar, { props: { legs: CONDOR(), current: CURRENT, ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return w
}
async function openList(w) {
  await t(w, 'add-to-paper').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'POST /paper/strategies/7/orders': BOOK }
})

describe('Add to Paper: the core', () => {
  it('CORE: type 113.00 over the first price, Confirm -> ONE POST of 4 open orders at 113.00 / 38.15 / 95.00 / 41.30; the toast offers both links', async () => {
    const w = await bar()
    await openList(w)
    expect(all(w, 'paper-order')).toHaveLength(4)
    expect(all(w, 'paper-price').map((i) => i.element.value)).toEqual(['112.40', '38.15', '95.00', '41.30']) // default = the builder entry price
    expect(all(w, 'paper-order-text')[0].text()).toBe('NIFTY 3 Nov 22800 CE')
    await all(w, 'paper-price')[0].setValue('113.00')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(posts()[0].url).toBe('/paper/strategies/7/orders')
    expect(posts()[0].body).toEqual({ orders: [
      { contract_id: 101, side: 'SELL', quantity: 65, price: '113.00', kind: 'open' },
      { contract_id: 102, side: 'BUY', quantity: 65, price: '38.15', kind: 'open' },
      { contract_id: 103, side: 'SELL', quantity: 65, price: '95.00', kind: 'open' },
      { contract_id: 104, side: 'BUY', quantity: 65, price: '41.30', kind: 'open' },
    ] })
    expect(t(w, 'paper-toast-message').text()).toBe('Added to Paper')
    expect(t(w, 'paper-open-builder').text()).toBe('Open in Builder')
    expect(t(w, 'paper-open-positions').text()).toBe('Open Paper positions')
    expect(t(w, 'paper-open-positions').attributes('href')).toBe('/positions/current-positions?tab=paper')
    expect(w.find('[data-testid="paper-confirm"]').exists()).toBe(false) // the list closed
    w.unmount()
  })

  it('the list carries the not-a-real-trade footer of REQ-109 AC-1 and nothing is posted by opening it', async () => {
    const w = await bar()
    await openList(w)
    expect(t(w, 'paper-not-real').text()).toBe('This is not a real trade. Paper orders use no real money.')
    expect(posts()).toHaveLength(0)
    w.unmount()
  })
})

describe('Add to Paper: price and lots', () => {
  it.each(['', '0', '-5', '112.43', '1.234', 'abc'])('price "%s" disables Confirm and says why beside the box; nothing is sent', async (bad) => {
    const w = await bar()
    await openList(w)
    await all(w, 'paper-price')[1].setValue(bad)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(all(w, 'paper-reason')[0].text()).toBe('Enter a price in steps of 0.05')
    await t(w, 'paper-confirm-button').trigger('click')
    expect(posts()).toHaveLength(0)
    w.unmount()
  })
  it('lots are whole lots >= 1; quantity = lots x lot size', async () => {
    const w = await bar()
    await openList(w)
    await all(w, 'paper-lots')[0].setValue('0')
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await all(w, 'paper-lots')[0].setValue('3')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()[0].body.orders[0]).toMatchObject({ contract_id: 101, quantity: 195 })
    w.unmount()
  })
  it('a leg with no entry price starts empty and blocks Confirm until a price is typed', async () => {
    const w = await bar({ legs: [mk(1, 101, 'SELL', '22800.00', 'CE', null, { captured_at: null })] })
    await openList(w)
    expect(t(w, 'paper-price').element.value).toBe('')
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('two legs on the SAME contract are two orders in the one request (the book nets them)', async () => {
    const w = await bar({ legs: [mk(1, 101, 'SELL', '22800.00', 'CE', '112.40'), mk(2, 101, 'SELL', '22800.00', 'CE', '110.00')] })
    await openList(w)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.orders.map((o) => [o.contract_id, o.price])).toEqual([[101, '112.40'], [101, '110.00']])
    w.unmount()
  })
  it('only ticked legs are listed; no tick -> the button is disabled', async () => {
    const legs = CONDOR().map((l, i) => ({ ...l, included: i === 2 }))
    const w = await bar({ legs })
    await openList(w)
    expect(all(w, 'paper-order')).toHaveLength(1)
    await w.setProps({ legs: CONDOR().map((l) => ({ ...l, included: false })) })
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})

describe('Add to Paper: answer states of the POST', () => {
  it.each([
    ['4xx refusal', { status: 422, parts: { what_happened: 'Enter a price in steps of 0.05' } }, 'Enter a price in steps of 0.05'],
    ['409 strategy changed', { status: 409, parts: { what_happened: 'The strategy changed; open it again' } }, 'The strategy changed; open it again'],
    ['network failure', new Error('Network Error'), null],
  ])('%s: the text is shown, the list stays open, no toast, nothing recorded', async (_n, failure, text) => {
    answers['POST /paper/strategies/7/orders'] = () => Promise.reject(failure)
    const w = await bar()
    await openList(w)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-error').text().length).toBeGreaterThan(0)
    if (text) expect(t(w, 'paper-error').text()).toBe(text)
    expect(w.find('[data-testid="paper-confirm"]').exists()).toBe(true)
    expect(w.find('[data-testid="paper-toast"]').exists()).toBe(false)
    w.unmount()
  })
  it('a double click sends ONE request (the button is busy)', async () => {
    let release
    answers['POST /paper/strategies/7/orders'] = () => new Promise((resolve) => { release = () => resolve({ data: BOOK }) })
    const w = await bar()
    await openList(w)
    await t(w, 'paper-confirm-button').trigger('click')
    await t(w, 'paper-confirm-button').trigger('click')
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    release()
    await flushPromises()
    expect(posts()).toHaveLength(1)
    w.unmount()
  })
})

describe('Add to Paper: unsaved strategy, toast, old path', () => {
  it('an UNSAVED strategy is saved first under its shown name, then the list posts to the new id', async () => {
    answers['POST /strategies'] = { id: 12, revision: 1, name: '"Iron Condor"' }
    answers['POST /paper/strategies/12/orders'] = { ...BOOK, strategy_id: 12 }
    const w = await bar({ current: null, shownName: 'Iron Condor' })
    await openList(w)
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url)).toEqual(['/strategies'])
    expect(calls.find((c) => c.url === '/strategies' && c.method === 'POST').body.name).toBe('Iron Condor')
    expect(w.emitted('saved')[0].slice(0, 2)).toEqual([12, 1])
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts().map((c) => c.url)).toEqual(['/paper/strategies/12/orders'])
    w.unmount()
  })
  it('a failed save stops before any paper order and shows the save error', async () => {
    answers['POST /strategies'] = () => Promise.reject({ status: 422, parts: { what_happened: 'Give the strategy a name' } })
    const w = await bar({ current: null })
    await openList(w)
    expect(w.find('[data-testid="paper-confirm"]').exists()).toBe(false)
    expect(posts()).toHaveLength(0)
    expect(t(w, 'save-error').text()).toContain('Give the strategy a name')
    w.unmount()
  })
  it('"Open in Builder" reloads this strategy', async () => {
    answers['GET /strategies/7'] = () => Promise.reject(new Error('read'))
    const w = await bar()
    await openList(w)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    await t(w, 'paper-open-builder').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.method === 'GET' && c.url === '/strategies/7')).toBe(true)
    w.unmount()
  })
  it('the "..." menu offers Add to Paper (the same list); "Start tracking" is gone from the code and the screen', async () => {
    const w = mount(SaveDraftBar, { props: { legs: CONDOR(), current: CURRENT }, slots: { menu: '<template #menu="{ close, addToPaper }"><button data-testid="menu-add-to-paper" @click="close(); addToPaper()">Add to Paper</button></template>' }, global: { stubs: { RouterLink: true } }, attachTo: document.body })
    await flushPromises()
    await t(w, 'more-menu').trigger('click')
    await t(w, 'menu-add-to-paper').trigger('click')
    await flushPromises()
    expect(all(w, 'paper-order')).toHaveLength(4)
    expect(w.text()).not.toContain('Start tracking')
    expect('START_TRACKING_LABEL' in tracking).toBe(false)
    w.unmount()
  })
  it('the dialog takes a list of orders, not legs: a single exit order emits a single exit order', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [{ key: 'x', contract_id: 5, side: 'BUY', text: 'NIFTY 3 Nov 22800 CE', lots: 2, lot_size: 65, price: '10.05', kind: 'exit' }] } })
    await t(w, 'paper-confirm-button').trigger('click')
    expect(w.emitted('confirm')[0][0]).toEqual([{ contract_id: 5, side: 'BUY', quantity: 130, price: '10.05', kind: 'exit' }])
    w.unmount()
  })
})
