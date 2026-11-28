// GC-ICLIVE-E D-44 (the Stops list names a leg as the form does), D-58 (zero-price message, held broker without quotes),
// D-49 (the leg column header follows the Lots / Quantity switch). Every new sentence is pending owner read.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

import HeldNote from '@/components/strategy/HeldNote.vue'
import { PAPER_PRICE_REASON, PAPER_PRICE_ZERO_REASON, paperPriceReason } from '@/lib/tracking'
import LegList from '@/components/strategy/LegList.vue'
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
const trig = (id, over = {}) => ({ id, strategy_id: 48, kind: 'conditional_exit', direction: 'above', level: '24500.00',
  level_text: 'Index at or above 24,500.00', contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed',
  created_at: '2026-10-29T05:00:00Z', fired_at: null, cancelled_at: null, ...over })
const ok = (data) => () => Promise.resolve({ data })
const refuse = (what) => () => Promise.reject({ message: 'x', status: 422, parts: { what_happened: what, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const TRIG = '/paper/strategies/48/triggers'
const posts = () => calls.filter((c) => c[0] === 'POST' && c[1] === TRIG)

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

describe('D-44: the Stops list names a leg the way the form does', () => {
  it('a leg stop row reads the same label as the form row, not the raw contract text', async () => {
    const w = await open({ triggers: [trig(1, { kind: 'leg_stop', contract_id: 5000, contract_text: 'NIFTY 22300 PE 2026-11-03', direction: 'above', level: '124.50', level_text: '124.50' })] })
    const formLabel = w.get('[data-testid^="stop-level-"]').element.closest('div').querySelector('span.min-w-40').textContent.trim()
    const listLabel = w.get('[data-testid="trigger-row"] span').text()
    expect(formLabel).toMatch(/^NIFTY 3 Nov 2026 22300 PE$|^NIFTY 3 Nov 22300 PE$/)
    expect(listLabel).toBe(formLabel)
    expect(listLabel).not.toContain('2026-11-03')
  })
  it('a stop on a leg the form no longer lists keeps the server text; a conditional exit keeps its words', async () => {
    const w = await open({ triggers: [trig(1, { kind: 'leg_stop', contract_id: 9999, contract_text: 'NIFTY 22300 PE 2026-11-03' }), trig(2)] })
    const rows = w.findAll('[data-testid="trigger-row"]')
    expect(rows[0].find('span').text()).toBe('NIFTY 22300 PE 3 Nov') // Lane FA r2 (D2): the server text keeps its words; its ISO date reads through the one date rule
    expect(rows[1].find('span').text()).toBe('Conditional exit')
  })
})

describe('D-58: zero price and held broker', () => {
  it('a zero price has its own reason; other bad prices keep the steps reason', () => {
    for (const zero of ['0', '0.00', '0.0', '00']) expect(paperPriceReason(zero), zero).toBe(PAPER_PRICE_ZERO_REASON)
    for (const bad of ['24500.03', 'abc', '-5']) expect(paperPriceReason(bad), bad).toBe(PAPER_PRICE_REASON)
    for (const good of ['24500', '124.50', '0.05']) expect(paperPriceReason(good), good).toBe('')
    expect(PAPER_PRICE_ZERO_REASON).not.toContain('steps of 0.05')
  })
  it('the Stops form shows the zero reason for Above = 0', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('0')
    expect(t(w, 'ce-reason').text()).toBe(PAPER_PRICE_ZERO_REASON)
  })
  it('the held broker name is shown without the API quotes', () => {
    const held = { entry_at: '2026-11-23T04:00:00Z', rules_start_at: null, broker: '"Zerodha"' }
    const w = mount(HeldNote, { props: { held } })
    expect(w.get('[data-testid="held-broker-name"]').text()).toBe('Zerodha')
    expect(mount(HeldNote, { props: { held: { ...held, broker: null } } }).find('[data-testid="held-broker-name"]').exists()).toBe(false)
  })
})

describe('D-49: the leg column header follows the Lots / Quantity switch', () => {
  const row = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:1', action: 'BUY', instrument: 'CE', strike: '25600.00', expiry: '2026-11-23', lots: 2, quantity: 130, price: '10.00' }
  it('says Lots, then Quantity after the switch, then Lots again', async () => {
    const w = mount(LegList, { props: { legs: [row] } })
    expect(w.get('[data-testid="leg-unit-head"]').text()).toBe('Lots')
    await w.setProps({ legUnit: 'quantity' })
    expect(w.get('[data-testid="leg-unit-head"]').text()).toBe('Quantity')
    await w.setProps({ legUnit: 'lots' })
    expect(w.get('[data-testid="leg-unit-head"]').text()).toBe('Lots')
  })
})

describe('D-44: after a successful Save the saved row is brought into view', () => {
  it('scrolls the saved stop row on success, and does nothing on a refusal', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const w = await open()
    const level = w.get('[data-testid^="stop-level-"]')
    const id = level.attributes('data-testid').replace('stop-level-', '')
    await level.setValue('120')
    answers[`POST ${TRIG}`] = () => Promise.reject({ message: 'x', status: 422, parts: { what_happened: 'No', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(scroll).not.toHaveBeenCalled()
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(7, { kind: 'leg_stop', contract_id: 5000, contract_text: 'x', direction: 'above', level: '120.00', level_text: '120.00' })] })
    await level.setValue('120')
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll.mock.contexts[0].getAttribute('data-trigger-id')).toBe('7')
  })
  it('a saved conditional exit scrolls its row too', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(3)] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(scroll.mock.contexts[0].getAttribute('data-trigger-id')).toBe('3')
  })
})
