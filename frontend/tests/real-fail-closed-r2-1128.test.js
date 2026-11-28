// Lane R2 review fixes (Opus review, 28 Nov). Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens, real actions only stored);
// ADR-016 to ADR-019 (fail closed). A position whose kind is unknown, none, missing or odd keeps Exit, Stops and the link door locked and is
// never worded as paper; a real exit is never worded "placed on paper".
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import FIX from './fixtures/paper-strategies.json'

let paperReply = null
const posts = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => (url === '/paper/strategies' ? Promise.resolve({ data: paperReply }) : Promise.reject({ status: 404, parts: null })),
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
beforeEach(() => { setActivePinia(createPinia()); posts.length = 0 })

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
  it('?exit=1 on an unknown group opens no dialog and posts nothing; on paper it opens', async () => {
    paperReply = doc({ position_kind: 'unknown' })
    const u = await show('/p?tab=paper&strategy=1&exit=1')
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]')).toBeNull()
    expect(posts).toEqual([])
    u.unmount()
    paperReply = doc({ position_kind: 'paper' })
    const p = await show('/p?tab=paper&strategy=1&exit=1')
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]')).not.toBeNull()
    p.unmount()
  })
  it('exit-only door (the Alerts page) on an unknown group draws no dialog', async () => {
    paperReply = doc({ position_kind: 'unknown' })
    const w = await show('/p', { exitOnlyFor: '1' })
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]')).toBeNull()
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
