// Lane R2 review fixes (Opus review, 28 Nov). Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens, real actions only stored);
// ADR-016 to ADR-019 (fail closed). A position whose kind is unknown, none, missing or odd keeps Exit, Stops and the link door locked and is
// never worded as paper; a real exit is never worded "placed on paper".
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import FIX from './fixtures/paper-strategies.json'

import { legacy } from './_paperList'
import { withPriceTexts } from './_priceTexts'
let paperReply = null
let answers = {}
const posts = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => { const a = legacy(answers, 'GET', url); if (a) return a(); return url === '/paper/strategies' ? Promise.resolve({ data: paperReply }) : Promise.reject({ status: 404, parts: null }) },
    post: (url) => { posts.push(url); return Promise.reject({ status: 404 }) }, delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { exitEndText } from '@/lib/usePaperExit'
import { REAL_UNKNOWN_TEXT } from '@/lib/positionKind'

const doc = (extra) => { const d = JSON.parse(JSON.stringify(FIX)); const s = d.strategies.find((x) => x.state === 'LIVE'); delete s.position_kind; Object.assign(s, extra); return d }
async function show(path, props = {}) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: { template: '<div/>' } }, { path: '/:x(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { props, global: { plugins: [r, createPinia()] } })
  await flushPromises()
  return w
}
beforeEach(() => { setActivePinia(createPinia()); posts.length = 0; answers = {} })

describe('F1: only exactly paper or real is a kind on the paper list', () => {
  for (const kind of [undefined, 'none', 'unknown', 'REAL', '', null]) {
    it(`kind ${String(kind)}: no PAPER tag, no Stops, no Exit button`, async () => {
      paperReply = doc({ position_kind: kind })
      const w = await show('/p')
      const g = w.get('[data-testid="paper-group"][data-strategy="1"]')
      expect(g.find('[data-testid="paper-tag"]').exists()).toBe(false)
      expect(g.find('[data-testid="stops-open-1"]').exists()).toBe(false)
      expect(g.find('[data-testid="paper-unknown-kind-line"]').exists()).toBe(true)
    })
  }
  it('paper keeps the tag and Stops', async () => {
    paperReply = doc({ position_kind: 'paper' })
    const g = (await show('/p')).get('[data-testid="paper-group"][data-strategy="1"]')
    expect(g.find('[data-testid="paper-tag"]').exists()).toBe(true)
    expect(g.find('[data-testid="stops-open-1"]').exists()).toBe(true)
  })
})

describe('F2: the link door and the alert door obey the same gate as the buttons', () => {
  const leg = (i) => withPriceTexts({ leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE', strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65,
    entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null })
  const tracking = (kind) => ({ strategies: [withPriceTexts({ strategy_id: 48, name: '"IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)], ...{ position_kind: kind } })], answered_at: '2026-10-28T06:00:00Z' })
  const run = async (kind, path, props) => {
    answers['GET /tracking'] = () => Promise.resolve({ data: tracking(kind) })
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:x(.*)*', component: { template: '<div/>' } }] })
    r.push(path)
    await r.isReady()
    const w = mount(PaperStrategies, { props, global: { plugins: [r, createPinia()] } })
    await flushPromises()
    return w
  }
  it('?exit=48: paper and real open the dialog; unknown, missing and none open nothing and post nothing', async () => {
    for (const [kind, opens] of [['paper', true], ['real', true], ['unknown', false], [null, false], ['none', false]]) {
      posts.length = 0
      const w = await run(kind, '/positions/current-positions?tab=paper&strategy=48&exit=48')
      expect(w.findComponent(PaperConfirmDialog).props('open'), String(kind)).toBe(opens)
      expect(posts).toEqual([])
      w.unmount()
    }
  })
  it('the exit-only door (the Alerts page) follows the same gate', async () => {
    for (const [kind, opens] of [['real', true], ['unknown', false]]) {
      const w = await run(kind, '/x', { exitOnlyFor: '48' })
      expect(w.findComponent(PaperConfirmDialog).props('open'), String(kind)).toBe(opens)
      w.unmount()
    }
  })
  it('a real exit opens a dialog of kind real, never paper', async () => {
    const w = await run('real', '/positions/current-positions?tab=paper&strategy=48&exit=48')
    expect(w.findComponent(PaperConfirmDialog).props('kind')).toBe('real')
    w.unmount()
  })
})

describe('F3: a real exit is never worded as paper', () => {
  it('the done line by kind: real stored, unknown neutral, paper unchanged', () => {
    expect(exitEndText('done', [], { kind: 'real' })).toContain('Not sent to Zerodha')
    expect(exitEndText('done', [], { kind: 'unknown' })).not.toContain('placed on paper')
    expect(exitEndText('done', [], { kind: 'paper', orders: [{ id: 3 }], sent: 1 })).toContain('Exit placed on paper')
  })
})

describe('F5: a real dialog never says order or Orderbook', () => {
  it('unknown outcome on a real exit', () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, kind: 'real', state: 'unknown', orders: [{ key: 'k', contract_id: 5, side: 'SELL', text: 'N', lots: 1, lot_size: 65, price: '0', kind: 'exit' }] }, attachTo: document.body })
    const t = document.body.querySelector('[data-testid="paper-unknown"]').textContent
    expect(t).toContain(REAL_UNKNOWN_TEXT)
    expect(t).not.toMatch(/order/i)
    expect(document.body.querySelector('[data-testid="paper-open-orderbook"]')).toBeNull()
    w.unmount()
  })
})
