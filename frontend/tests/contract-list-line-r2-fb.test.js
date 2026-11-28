// Lane FB round 2, I-30 (ADR-330 (61), REQ-053 AC-3): the builder page says, above the leg list, which day's contract list it works on,
// with the SERVER's own sentence (expiries reply `list_notice`); it is gone when the reply carries none, and shown on an empty list too.
// Real case: 27 Nov 08:30, app started 08:07, the builder went empty with "No legs yet" and no word about the list.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const NOTICE = "Contract list of 26 Nov. Today's list loads at about 08:35."
const expiries = (over = {}) => ({ underlying: 'NIFTY', expiries: ['2026-12-01'], expiry_days: [{ expiry: '2026-12-01', days: 4 }], today: '2026-11-27', default_expiry: '2026-12-01',
  list_day: '2026-11-26', list_current: false, list_notice: NOTICE, ...over })
const t = (w, id) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/expiries': expiries() }
})
afterEach(() => vi.useRealTimers())

const mountPage = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push('/strategy/builder')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('I-30: the contract-list line on the builder page', () => {
  it('notice present: the server sentence is shown once, word for word, on an EMPTY list that says "No legs yet"', async () => {
    const w = await mountPage()
    expect(t(w, 'contract-list-notice').exists()).toBe(true)
    expect(t(w, 'contract-list-notice').text()).toBe(NOTICE)
    expect(w.text()).toContain('No legs yet')
    expect(w.findAll('[data-testid="contract-list-notice"]')).toHaveLength(1)
    w.unmount()
  })
  it('notice absent (today\'s list in use): no line', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = expiries({ list_notice: null, list_current: true, list_day: '2026-11-27' })
    const w = await mountPage()
    expect(t(w, 'contract-list-notice').exists()).toBe(false)
    w.unmount()
  })
  it('empty text: no line, no empty box', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = expiries({ list_notice: '   ' })
    const w = await mountPage()
    expect(t(w, 'contract-list-notice').exists()).toBe(false)
    w.unmount()
  })
  it('the expiries call failed: no invented line (the page builds no wording itself) and the page still works', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = new Error('network')
    const w = await mountPage()
    expect(t(w, 'contract-list-notice').exists()).toBe(false)
    expect(w.text()).toContain('No legs yet')
    w.unmount()
  })
  it('the line goes when the next read carries no notice (today\'s list loaded at about 08:35), and a failed re-read keeps it', async () => {
    vi.useFakeTimers()
    const w = await mountPage()
    expect(t(w, 'contract-list-notice').exists()).toBe(true)
    answers['GET /catalogue/NIFTY/expiries'] = new Error('network')
    await vi.advanceTimersByTimeAsync(61000)
    expect(t(w, 'contract-list-notice').text()).toBe(NOTICE) // a failed read says nothing new: the last known line stays
    answers['GET /catalogue/NIFTY/expiries'] = expiries({ list_notice: null, list_current: true, list_day: '2026-11-27' })
    await vi.advanceTimersByTimeAsync(61000)
    expect(t(w, 'contract-list-notice').exists()).toBe(false)
    const n = calls.filter((c) => c.url === '/catalogue/NIFTY/expiries').length
    await vi.advanceTimersByTimeAsync(300000)
    expect(calls.filter((c) => c.url === '/catalogue/NIFTY/expiries').length).toBe(n) // no timer once the line is gone
    w.unmount()
  })
})
