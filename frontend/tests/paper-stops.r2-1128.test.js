// Lane TB (R2, 28 Nov) I-65. Extends paper-stops.test.js (same mocks, same fixtures).
// (base file header) GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); screens 221-224): arming a Conditional exit or a leg Stop on a paper strategy,
// listing and cancelling its triggers. Levels are sent as typed strings; every figure shown is the server's text.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: String(5000 + i), action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = withPriceTexts({
  strategy_id: 48, name: '"GCTP IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)],
})
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const TRIG = '/paper/strategies/48/triggers'

async function open(triggers = { triggers: [] }) {
  answers['GET /tracking'] = ok({ strategies: [item], answered_at: '2026-10-28T06:00:00Z' })
  answers[`GET ${TRIG}`] = ok(triggers)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  await t(w, 'stops-open-48').trigger('click')
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {} })

describe('I-65 Stops panel: every leg row names its Stop price box', () => {
  it('I-65: each leg row has a direction and a Stop price box, and the box has a visible label and an accessible name', async () => {
    const w = await open()
    const rows = w.findAll('[data-testid^="stop-row-"]')
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      const i = row.attributes('data-testid').replace('stop-row-', '')
      expect(row.find(`[data-testid="stop-direction-${i}"]`).exists()).toBe(true) // the row's direction
      const box = row.get(`[data-testid="stop-box-${i}"]`) // the <label> around the input
      expect(box.element.tagName).toBe('LABEL')
      expect(box.text()).toContain('Stop price') // a visible label, not a placeholder alone
      expect(box.find(`[data-testid="stop-level-${i}"]`).exists()).toBe(true) // and it wraps the box it names
      expect(row.get(`[data-testid="stop-level-${i}"]`).attributes('aria-label')).toMatch(/^Stop price for .+/)
    }
  })
  it('I-65: the label text survives typing (the box keeps its label once it holds a value)', async () => {
    const w = await open()
    const i = w.get('[data-testid^="stop-row-"]').attributes('data-testid').replace('stop-row-', '')
    await t(w, `stop-level-${i}`).setValue('101.5')
    expect(t(w, `stop-box-${i}`).text()).toContain('Stop price')
  })
})
