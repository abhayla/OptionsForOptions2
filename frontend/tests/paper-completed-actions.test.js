// S-28 (ADR-330 (14)): a Completed paper strategy shows "Open in Builder" only, never "Add orders"; a Running one keeps both.
// S-15 screen half (ADR-330 (15)): the Paper total's line "Includes N closed strategies" is the server's closed_text, printed as sent,
// only when served; the browser never builds it.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const clone = () => JSON.parse(JSON.stringify(REAL0))
const ok = (data) => () => Promise.resolve({ data })
async function show(data) {
  answers['GET /paper/strategies'] = ok(data)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {} })

describe('Completed strategy actions (S-28)', () => {
  it('Completed: Open in Builder only; Running: both', async () => {
    const d = clone()
    d.strategies[0].status_word = 'Completed'
    d.strategies[0].open_count = 0
    for (const s of d.strategies.slice(1)) s.status_word = 'Running'
    const w = await show(d)
    await w.get('[data-testid="show-closed"]').setValue(true) // closed rows are listed only with Show closed positions on
    const groups = w.findAll('[data-testid="paper-group"]')
    expect(groups[0].get('[data-testid="paper-status-word"]').text()).toBe('Completed')
    expect(groups[0].find('[data-testid="paper-open-builder"]').exists()).toBe(true)
    expect(groups[0].find('[data-testid="paper-add-orders"]').exists()).toBe(false)
    const running = groups.slice(1)
    expect(running.length).toBeGreaterThan(0)
    for (const g of running) {
      expect(g.get('[data-testid="paper-status-word"]').text()).toBe('Running')
      expect(g.find('[data-testid="paper-add-orders"]').exists()).toBe(true)
      expect(g.find('[data-testid="paper-open-builder"]').exists()).toBe(true)
    }
  })
})

describe('Closed-strategies note under the Paper total (S-15 screen half)', () => {
  it('prints the served closed_text verbatim; absent or blank: no line', async () => {
    const LINE = 'Includes 2 closed strategies'
    const d = clone()
    d.totals.closed_text = LINE
    const w = await show(d)
    expect(w.get('[data-testid="totals-closed-note"]').text()).toBe(LINE)
    const none = clone()
    delete none.totals.closed_text
    expect((await show(none)).find('[data-testid="totals-closed-note"]').exists()).toBe(false)
    const blank = clone()
    blank.totals.closed_text = '  '
    expect((await show(blank)).find('[data-testid="totals-closed-note"]').exists()).toBe(false)
  })
})
