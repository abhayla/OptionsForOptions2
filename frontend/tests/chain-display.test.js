// W-124 (REQ-087 AC-1..AC-5, REQ-029 AC-3/AC-5/AC-9, REQ-031 AC-1/AC-2/AC-3, REQ-030 AC-14): the Option Chain's display
// options, per-UX-level columns, strikes preference and live preview. Every value is a string the server computed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const calls = []
let settingValue = null // the stored strikes preference, or null = never set (the page then keeps the default)
let putFails = false
let previewAnswer = () => Promise.reject(new Error('down'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body, cfg) => {
    calls.push({ method, url, body, params: cfg?.params })
    if (url.startsWith('/catalogue/')) return Promise.resolve({ data: { expiries: ['2026-10-27'] } })
    if (url === '/user-settings/chain-strikes' && method === 'get') return settingValue ? Promise.resolve({ data: { strikes_each_side: settingValue, is_default: false } }) : Promise.reject(new Error('none'))
    if (url === '/user-settings/chain-strikes' && method === 'put') return putFails ? Promise.reject(new Error('down')) : Promise.resolve({ data: body })
    if (url === '/market/chain/preview') return previewAnswer(body)
    if (url === '/market/chain') return Promise.reject(new Error('down'))
    return Promise.reject(new Error('unexpected ' + url))
  }
  return { ...actual, default: {
    get: (url, cfg) => respond('get', url, undefined, cfg),
    put: (url, body) => respond('put', url, body),
    post: (url, body) => respond('post', url, body),
  } }
})
// chart.js needs a canvas: the page's chart is replaced by a stub that shows how many points it was given
vi.mock('@/components/strategy/PayoffChart.vue', async () => { const { h } = await import('vue'); return { default: { props: ['points'], render() { return h('i', { 'data-testid': 'payoff-chart' }, String(this.points.length)) } } } })
import { createPinia, setActivePinia } from 'pinia'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import { STRIKE_CHOICES, fieldsFor, lotSizeOf, previewLegs, previewLines } from '@/lib/chainDisplay'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
}

const EXPIRY = '2026-10-27'
const extras = (over = {}) => ({ lot_size: 65, in_the_money: false, per_lot: '9750.00', intrinsic: '76.85', time_value: '73.15', breakeven: '23050.00', breakeven_pct: '0.32', delta: '0.5766', gamma: '0.0015', theta: '-12.1000', vega: '8.2000', ...over })
const cell = (id, ltp, over = {}) => ({ instrument_id: id, ltp, bid: '149.00', ask: '151.00', change: null, oi: '1000', oi_change: '40', volume: '50', health: 'available', at: '2026-10-19T10:00:00+05:30', permitted: true, unavailable_reason: null, ...extras(), ...over })
const row = (strike, ceOver = {}, peOver = {}) => ({ strike, ce: cell(`NFO:${strike}CE`, '150.00', ceOver), pe: cell(`NFO:${strike}PE`, '80.00', peOver) })
const answer = (over = {}) => ({
  state: 'LIVE', underlying: 'NIFTY', expiry: EXPIRY, spot: '22976.85', spot_at: '2026-10-19T10:00:00+05:30', spot_health: 'available', atm_strike: '23000.00',
  rows_missing: null, answered_at: '2026-10-19T10:00:01+05:30',
  rows: [row('22900.00', { in_the_money: true }, { in_the_money: false }), row('23000.00', { in_the_money: false }, { in_the_money: true })], ...over,
})
const PREVIEW = { state: 'COMPUTED', underlying: 'NIFTY', reason: null, net_premium: '6500.00', net_side: 'Cr', max_profit: '6500.00', max_loss: null, max_profit_unlimited: false, max_loss_unlimited: true,
  breakevens: ['22835.00'], payoff: [{ level: '22000.00', pnl: '-1000.00' }, { level: '23000.00', pnl: '6500.00' }], matched_template: 'Short Put', answered_at: '2026-10-19T10:00:02+05:30' }

async function mountLive(over = {}) {
  const w = mount(OptionChainPage)
  await flushPromises()
  FakeSocket.all.at(-1).serverOpen()
  FakeSocket.all.at(-1).serverPush(answer(over))
  await flushPromises()
  return w
}
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((c) => c.text())

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  calls.length = 0
  settingValue = null
  putFails = false
  previewAnswer = () => Promise.reject(new Error('down'))
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('REQ-087 display options', () => {
  it('AC-1: Per lot swaps LTP for the server per-lot value and puts the lot size in the heading', async () => {
    const w = await mountLive()
    expect(texts(w, 'ce-ltp')).toEqual(['150.00', '150.00'])
    await w.find('[data-testid="per-lot-toggle"]').setValue(true)
    expect(texts(w, 'ce-per_lot')).toEqual(['9750.00', '9750.00'])
    expect(w.find('[data-testid="head-per_lot"]').text()).toBe('LTP per lot (x65)')
    expect(w.find('[data-testid="ce-ltp"]').exists()).toBe(false)
  })

  it('AC-2: in-the-money cells follow the server flag (calls below spot, puts above), nothing is computed in the browser', async () => {
    const w = await mountLive()
    const shade = (id) => w.findAll(`[data-testid="${id}"]`).map((c) => c.attributes('data-itm'))
    expect(shade('ce-ltp')).toEqual(['true', 'false'])
    expect(shade('pe-ltp')).toEqual(['false', 'true'])
    // a server answer that says false stays unshaded whatever the strike and spot look like
    FakeSocket.all.at(-1).serverPush(answer({ rows: [row('22900.00', { in_the_money: false }, { in_the_money: null })] }))
    await flushPromises()
    expect(shade('ce-ltp')).toEqual(['false'])
    expect(shade('pe-ltp')).toEqual(['false'])
  })

  it('AC-2: a stale spot turns shading off at once with the server\'s data label, never from the old spot', async () => {
    const w = await mountLive({ spot_health: 'stale', spot_label: 'stale since 10:00 IST' })
    expect(w.findAll('[data-itm="true"]')).toHaveLength(0)
    expect(w.find('[data-testid="itm-off"]').text()).toContain('stale since 10:00 IST')
    for (const health of ['delayed', 'unavailable']) {
      FakeSocket.all.at(-1).serverPush(answer({ spot_health: health }))
      await flushPromises()
      expect(w.findAll('[data-itm="true"]')).toHaveLength(0)
    }
  })

  it('AC-2/AC-5: with no spot the shading is off and says why', async () => {
    const w = await mountLive({ spot: null, rows: [row('22900.00', { in_the_money: null, intrinsic: null }, { in_the_money: null, intrinsic: null })] })
    expect(w.find('[data-testid="itm-off"]').exists()).toBe(true)
    expect(w.findAll('[data-itm="true"]')).toHaveLength(0)
  })

  it('AC-3: the strikes choice is 10 / 20 / 30 / 40, default 10, loaded for the user, and kept on change', async () => {
    const w = await mountLive()
    expect(JSON.parse(FakeSocket.all.at(-1).sent[0]).strikes_each_side).toBe(10)
    expect(w.find('[data-testid="strikes-select"]').findAll('option').map((o) => o.text())).toEqual(['10', '20', '30', '40'])
    await w.find('[data-testid="strikes-select"]').setValue('30')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'put').at(-1).body).toEqual({ strikes_each_side: 30 })
    expect(JSON.parse(FakeSocket.all.at(-1).sent.at(-1)).strikes_each_side).toBe(30)
    expect(w.find('[data-testid="strikes-not-saved"]').exists()).toBe(false)
  })

  it('AC-3: a stored choice of 20 is used for the first request; a failed save is said, not hidden', async () => {
    settingValue = 20
    putFails = true
    const w = mount(OptionChainPage)
    await flushPromises()
    await w.find('[data-testid="strikes-select"]').setValue('40')
    await flushPromises()
    expect(w.find('[data-testid="strikes-not-saved"]').exists()).toBe(true)
    expect(STRIKE_CHOICES).toEqual([10, 20, 30, 40])
    expect(w.find('[data-testid="strikes-select"]').element.value).toBe('40')
  })
})

describe('REQ-029 AC-3 / AC-9: columns by UX level', () => {
  it('guided is simplest, standard the default, advanced adds Bid/Ask, OI change, REQ-087 columns and Greeks', async () => {
    const w = await mountLive()
    const heads = () => w.find('[data-testid="chain-columns"]').findAll('th').map((t) => t.text()).filter(Boolean).slice(0, 14)
    expect(heads().join('|')).not.toMatch(/Delta|Bid/)
    await w.find('[data-testid="ux-level-select"]').setValue('advanced')
    const advanced = heads().join('|')
    for (const label of ['Bid', 'Ask', 'OI Change', 'Intrinsic (vs spot)', 'Time value', 'Breakeven %', 'Delta', 'Gamma', 'Theta', 'Vega']) expect(advanced).toContain(label)
    expect(texts(w, 'ce-intrinsic')).toEqual(['76.85', '76.85'])
    expect(texts(w, 'ce-breakeven_pct')).toEqual(['0.32', '0.32'])
    expect(texts(w, 'ce-delta')).toEqual(['0.5766', '0.5766'])
    await w.find('[data-testid="ux-level-select"]').setValue('guided')
    expect(w.find('[data-testid="ce-volume"]').exists()).toBe(false)
    expect(w.find('[data-testid="ce-delta"]').exists()).toBe(false)
  })

  it('REQ-087 AC-5: a missing value is a dash, never 0', async () => {
    const w = await mountLive({ rows: [row('22900.00', { intrinsic: null, time_value: null, breakeven_pct: null, delta: null })] })
    await w.find('[data-testid="ux-level-select"]').setValue('advanced')
    expect([texts(w, 'ce-intrinsic'), texts(w, 'ce-time_value'), texts(w, 'ce-breakeven_pct'), texts(w, 'ce-delta')]).toEqual([['-'], ['-'], ['-'], ['-']])
  })

  it('an unknown level shows the standard set, never a wider one', () => {
    expect(fieldsFor('expert', false, null).map(([k]) => k)).toEqual(['ltp', 'change', 'oi', 'volume'])
    expect(lotSizeOf(answer())).toBe(65)
    expect(lotSizeOf({ rows: [] })).toBeNull()
  })
})

describe('REQ-031 live preview and REQ-030 AC-14', () => {
  async function pickShortCall(w) {
    await w.find('[data-testid="sell-ce"]').trigger('click')
    await flushPromises()
  }

  it('AC-1/AC-2/AC-14: the selection posts to the server and shows net premium, max profit, Unlimited loss, breakevens, the matched template and a mini payoff', async () => {
    previewAnswer = () => Promise.resolve({ data: PREVIEW })
    const w = await mountLive()
    await pickShortCall(w)
    const post = calls.filter((c) => c.method === 'post').at(-1)
    expect(post.url).toBe('/market/chain/preview')
    expect(post.body).toEqual({ underlying: 'NIFTY', legs: [{ instrument_id: 'NFO:22900.00CE', action: 'SELL', lots: 1, planned_entry: '150.00', captured_at: '2026-10-19T10:00:00+05:30' }] })
    expect(w.find('[data-testid="preview-net"]').text()).toBe('Net premium: 6500.00 Cr')
    expect(w.find('[data-testid="preview-max-profit"]').text()).toBe('Max profit: 6500.00')
    expect(w.find('[data-testid="preview-max-loss"]').text()).toBe('Max loss: Unlimited')
    expect(w.find('[data-testid="preview-breakevens"]').text()).toBe('Breakevens: 22835.00')
    expect(w.find('[data-testid="preview-template"]').text()).toBe('Matches: Short Put')
    expect(w.find('[data-testid="payoff-chart"]').text()).toBe('2') // the server's two payoff points go to the existing chart
    expect(w.find('[data-testid="preview-stale"]').exists()).toBe(false)
    // AC-14: the match is shown only; the selection is still the leg the user chose, and no order control appears
    expect(texts(w, 'selected-leg-name')).toEqual(['NIFTY 2026-10-27 22900.00 CE'])
    expect(w.html()).not.toMatch(/Execute|Place order/i)
  })

  it('AC-2: when the feed drops the preview shows NO numbers, only that it is unavailable', async () => {
    previewAnswer = () => Promise.resolve({ data: PREVIEW })
    const w = await mountLive()
    await pickShortCall(w)
    previewAnswer = () => Promise.resolve({ data: { ...PREVIEW, state: 'NOT_CONNECTED', net_premium: null, max_profit: null, breakevens: [], payoff: [] } })
    await w.find('[data-testid="lots-plus"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="preview-stale"]').exists()).toBe(true)
    expect(w.find('[data-testid="preview-net"]').exists()).toBe(false) // no last numbers under a banner
    expect(w.find('[data-testid="preview-max-loss"]').exists()).toBe(false)
  })

  it('AC-1: no leg, no preview; a leg without a captured price is not previewed', async () => {
    const w = await mountLive()
    expect(w.find('[data-testid="chain-preview"]').exists()).toBe(false)
    expect(previewLegs([{ instrument_id: 'NFO:1', action: 'BUY', lots: 1, permitted: true, planned_entry: null, captured_at: null }])).toEqual([])
    expect(previewLegs([{ instrument_id: 'NFO:1', action: null, lots: 1, permitted: true, planned_entry: '1.00', captured_at: 'x' }])).toEqual([])
    expect(previewLegs([{ instrument_id: 'NFO:1', action: 'BUY', lots: 1, permitted: false, planned_entry: '1.00', captured_at: 'x' }])).toEqual([])
  })

  it('AC-3: only the summary words are carried; unlimited profit and a not-computed state read as words or dashes', () => {
    expect(previewLines({ ...PREVIEW, max_profit_unlimited: true, max_profit: null }).maxProfit).toBe('Unlimited')
    expect(previewLines({ ...PREVIEW, state: 'NOT_CONNECTED' })).toBeNull()
  })
})

describe('REQ-029 AC-5: reachable from the Strategy Builder and Market', () => {
  it('the Builder carries a "Select from Option Chain" link to the chain route; the Market nav lists the chain', () => {
    const builder = readFileSync(resolve(__dirname, '../src/pages/StrategyBuilderPage.vue'), 'utf8')
    expect(builder).toMatch(/to="\/market\/option-chain"[^>]*data-testid="select-from-chain">Select from Option Chain</)
    expect(readFileSync(resolve(__dirname, '../src/router/nav.js'), 'utf8')).toContain("['option-chain', 'Option Chain']")
  })
})
