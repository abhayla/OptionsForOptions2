// ADR-330 (3b): the one info pop-up disappears by itself after INFO_POPUP_MS (6000, one home); a new actionable alert is announced
// once by it (and stays in Active and the bell); the first read announces nothing.
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
import { INFO_POPUP_MS, showInfo } from '@/lib/infoPopup'
import { resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const row = (id, kind = 'plan_loss_stop') => ({ id, strategy_id: 7, strategy_name: '"Trade A"', kind, text: `Loss stop ${id} reached`, fired_line: 'Fired at 11:02', answers: [] })
const active = (...rows) => () => Promise.resolve({ data: { count: rows.length, alerts: rows } })

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  toasts.splice(0)
  vi.useFakeTimers()
})
afterEach(() => { vi.useRealTimers() })

describe('showInfo', () => {
  it('INFO_POPUP_MS is 6000', () => { expect(INFO_POPUP_MS).toBe(6000) })
  it('shows the text, and it is gone after INFO_POPUP_MS and not before', () => {
    showInfo('Paper orders placed')
    expect(toasts.map((t) => t.message)).toEqual(['Paper orders placed'])
    vi.advanceTimersByTime(INFO_POPUP_MS - 1)
    expect(toasts).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(toasts).toHaveLength(0)
  })
})

describe('a new actionable alert is announced once', () => {
  it('nothing on the first read; one pop-up for a new id on a later poll, not again on the next', async () => {
    answers['GET /alerts/active'] = active(row(1))
    answers['GET /adjustment-opportunities'] = () => Promise.resolve({ data: { groups: [] } })
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
    r.push('/')
    await r.isReady()
    mount(AppHeader, { global: { plugins: [r] } })
    await flushPromises()
    expect(toasts).toHaveLength(0)
    answers['GET /alerts/active'] = active(row(1), row(2))
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toBe('Trade A: Loss stop 2 reached')
    toasts.splice(0)
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    expect(toasts).toHaveLength(0)
  })
})
