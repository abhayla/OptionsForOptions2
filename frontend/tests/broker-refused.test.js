// #163: /broker/refused shows the reviewed catalogue message fetched for the closed code in the query, and the
// neutral message for no code, an unknown code or a failed fetch. The page never renders the code itself.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

// A plain function, not vi.fn(): the spy's own result tracking turns a rejected promise into an unhandled rejection.
const calls = []
let answer = () => Promise.reject(new Error('no answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); return answer(url) } } }
})
import { NEUTRAL_PARTS } from '@/services/api'
import BrokerRefusedPage from '@/pages/BrokerRefusedPage.vue'

const MESSAGE = {
  what_happened: 'Zerodha did not complete this login.',
  impact: 'No Zerodha connection was made.',
  what_is_blocked: 'Anything that needs your Zerodha account.',
  next_action: 'Start the Zerodha login again.',
  code: 'broker_login_not_completed',
  error_class: 'broker_authentication',
}
const NEUTRAL_WHAT = 'The Zerodha login was not completed.'

async function open(query) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/broker/refused', component: BrokerRefusedPage }] })
  await router.push({ path: '/broker/refused', query })
  await router.isReady()
  const wrapper = mount(BrokerRefusedPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

const text = (w, id) => w.get(`[data-testid="${id}"]`).text()

describe('/broker/refused', () => {
  beforeEach(() => { calls.length = 0 })

  it('fetches the message for the code and shows its four parts, not the code', async () => {
    answer = () => Promise.resolve({ data: { code: 'broker_login_not_completed', message: MESSAGE } })
    const w = await open({ code: 'broker_login_not_completed' })
    expect(calls).toEqual(['/broker/refusals/broker_login_not_completed'])
    expect(text(w, 'error-what')).toBe(MESSAGE.what_happened)
    expect(text(w, 'error-impact')).toBe(MESSAGE.impact)
    expect(text(w, 'error-blocked')).toBe(MESSAGE.what_is_blocked)
    expect(text(w, 'error-next')).toBe(MESSAGE.next_action)
    expect(w.text()).not.toContain('broker_login_not_completed')
  })

  it('shows the neutral message and makes no request when there is no code', async () => {
    const w = await open({})
    expect(calls).toEqual([])
    expect(text(w, 'error-what')).toBe(NEUTRAL_WHAT)
    expect(text(w, 'error-next')).toBe(NEUTRAL_PARTS.next_action)
  })

  it('shows the neutral message and makes no request for a code of the wrong shape', async () => {
    for (const code of ['../x', 'Kite Refused', 'request_token=abc', 'x'.repeat(65), ['a', 'b']]) {
      const w = await open({ code })
      expect(text(w, 'error-what')).toBe(NEUTRAL_WHAT)
    }
    expect(calls).toEqual([])
  })

  it('shows the neutral message for an unknown code (the API answers its fixed input error)', async () => {
    answer = () => Promise.reject(Object.assign(new Error('x'), { status: 422, parts: { ...MESSAGE } }))
    const w = await open({ code: 'nope' })
    expect(text(w, 'error-what')).toBe(NEUTRAL_WHAT)
    expect(w.text()).not.toContain(MESSAGE.what_happened)
  })

  it('shows the neutral message when the fetch fails', async () => {
    answer = () => Promise.reject(Object.assign(new Error('network'), { status: null }))
    const w = await open({ code: 'kite_refused' })
    expect(text(w, 'error-what')).toBe(NEUTRAL_WHAT)
  })

  it('shows the neutral message when the body is not a catalogue message', async () => {
    answer = () => Promise.resolve({ data: { code: 'kite_refused', message: { detail: 'Traceback SECRET' } } })
    const w = await open({ code: 'kite_refused' })
    expect(text(w, 'error-what')).toBe(NEUTRAL_WHAT)
    expect(w.text()).not.toContain('SECRET')
  })
})
