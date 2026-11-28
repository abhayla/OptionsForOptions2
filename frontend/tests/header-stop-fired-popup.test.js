// W2-A (ADR-330 (3)(b)): a fired stop's informational History row (kind stop_fired, GET /alerts/answered) pops ONCE as a short
// message, from the one header reader on the paper refresh tick; rows already there at the page's first read never pop; a
// failed read pops nothing; the bell is the server's active count and is never touched by these rows.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import AppHeader from '@/components/layout/AppHeader.vue'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const active = (n) => () => Promise.resolve({ data: { count: n, alerts: Array.from({ length: n }, (_, i) => ({ id: 100 + i, strategy_id: 48, kind: 'plan_loss_stop', text: `t${i}`, fired_line: 'Fired at 11:02', answers: [] })) } })
const row = (id, kind = 'stop_fired') => ({ id, strategy_id: 48, strategy_name: '"Condor" (#48, 1 Dec)', kind, text: `Stop-loss ${id}`, fired_line: 'Fired at 11:02' })
const answered = (...rows) => () => Promise.resolve({ data: { items: rows } })

let r
async function header() {
  r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push('/')
  await r.isReady()
  const w = mount(AppHeader, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const popped = () => toasts.map((t) => t.message ?? t.text ?? JSON.stringify(t))
const badge = (w) => w.find('[data-testid="alerts-bell-count"]')

beforeEach(() => {
  answers = { 'GET /alerts/active': active(1), 'GET /adjustment-opportunities': () => Promise.resolve({ data: { groups: [] } }) }
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('a fired stop pops once from the one header reader', () => {
  it('a new stop_fired row after load pops once; the same id on the next tick does not pop again', async () => {
    answers['GET /alerts/answered'] = answered()
    const w = await header()
    answers['GET /alerts/answered'] = answered(row(9))
    await tick()
    expect(popped().filter((m) => m.includes('Stop-loss 9'))).toHaveLength(1)
    expect(popped()[0]).toContain('Condor (#48, 1 Dec)')
    await tick()
    expect(popped().filter((m) => m.includes('Stop-loss 9'))).toHaveLength(1)
    expect(badge(w).text()).toBe('1') // never counted
  })
  it('rows present at the first load do not pop', async () => {
    answers['GET /alerts/answered'] = answered(row(3), row(4))
    await header()
    await tick()
    expect(popped().filter((m) => m.includes('Stop-loss'))).toHaveLength(0)
  })
  it('other informational kinds do not pop here', async () => {
    answers['GET /alerts/answered'] = answered()
    await header()
    answers['GET /alerts/answered'] = answered(row(9, 'settled'))
    await tick()
    expect(popped()).toHaveLength(0)
  })
  it('a failed read pops nothing and keeps the bell as it was', async () => {
    answers['GET /alerts/answered'] = answered()
    const w = await header()
    answers['GET /alerts/answered'] = () => Promise.reject({ message: 'down', parts: null, status: 500 })
    await tick()
    expect(popped()).toHaveLength(0)
    expect(badge(w).text()).toBe('1')
    answers['GET /alerts/answered'] = answered(row(11)) // the next good read still pops the new row once
    await tick()
    expect(popped().filter((m) => m.includes('Stop-loss 11'))).toHaveLength(1)
  })
})
