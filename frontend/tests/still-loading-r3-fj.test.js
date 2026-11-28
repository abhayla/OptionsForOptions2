// Lane FJ r3: a slow read keeps its loading state, adds ONE plain "still loading" line after 4 s, and shows the failure sentence only on a real failure.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let release
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/alerts/active') return new Promise((res) => { release = () => res({ data: { items: [] } }) })
    return Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get, post: get } }
})
import AlertsPage from '@/pages/AlertsPage.vue'
import { STILL_LOADING_TEXT } from '@/lib/useStillLoading'
import { resetActiveAlerts } from '@/lib/paperAlerts'

beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] }); resetActiveAlerts() })
afterEach(() => vi.useRealTimers())
async function open() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:rest(.*)*', component: { template: '<div/>' } }] })
  r.push('/alerts/active')
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
describe('Alerts Active, a read that is slow', () => {
  it('shows Loading..., then the still-loading line after 4 s, and no failure sentence while the read is open', async () => {
    const w = await open()
    expect(w.text()).toContain('Loading...')
    expect(w.text()).not.toContain(STILL_LOADING_TEXT)
    await vi.advanceTimersByTimeAsync(5000)
    expect(w.text()).toContain(STILL_LOADING_TEXT)
    expect(w.text()).not.toContain('could not get an answer')
    release()
    await flushPromises()
    expect(w.text()).not.toContain(STILL_LOADING_TEXT)
    expect(w.text()).not.toContain('Loading...')
  })
})
