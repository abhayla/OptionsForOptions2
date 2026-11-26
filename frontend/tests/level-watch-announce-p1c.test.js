// P1c NEW-2 (ADR-242 (3), ADR-330 (3b), D-67): a new level-watch record gets exactly one info pop-up and never counts on the
// bell; an actionable alert keeps its single pop-up (M4).
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
import { bellCount, resetActiveAlerts, resetOpenRecords } from '@/lib/paperAlerts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { toasts } from '@/composables/useToast'

const active = (...rows) => () => Promise.resolve({ data: { count: rows.length, alerts: rows } })
const opp = (...recs) => () => Promise.resolve({ data: { groups: [{ group: 'g', strategy_id: 7, strategy_name: 'T', records: recs }] } })
const rec = (id, extra = {}) => ({ id, outcome: 'open', condition: `rule ${id}`, rule_id: 'watch.level.above', ...extra })
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }

async function mountHeader() {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push('/')
  await r.isReady()
  mount(AppHeader, { global: { plugins: [r] } })
  await flushPromises()
}

beforeEach(() => {
  answers = {}
  resetActiveAlerts()
  resetOpenRecords()
  vi.useFakeTimers()
  toasts.splice(0)
})
afterEach(() => { vi.useRealTimers() })

describe('P1c: a level-watch crossing is announced once', () => {
  it('a new level_watch record raises exactly one pop-up and leaves the bell unchanged', async () => {
    answers['GET /alerts/active'] = active()
    answers['GET /adjustment-opportunities'] = opp()
    await mountHeader()
    answers['GET /adjustment-opportunities'] = opp(rec(9))
    await tick()
    expect(toasts).toHaveLength(1)
    expect(bellCount()).toBe(0)
    await tick()
    expect(toasts).toHaveLength(1)
  })
  it('a quiet level-watch record (popup_due false) waits; it raises once when due', async () => {
    answers['GET /alerts/active'] = active()
    answers['GET /adjustment-opportunities'] = opp()
    await mountHeader()
    answers['GET /adjustment-opportunities'] = opp(rec(9, { popup_due: false }))
    await tick()
    expect(toasts).toHaveLength(0)
    answers['GET /adjustment-opportunities'] = opp(rec(9))
    await tick()
    expect(toasts).toHaveLength(1)
  })
  it('an actionable alert that is also an open record still raises one pop-up', async () => {
    answers['GET /alerts/active'] = active()
    answers['GET /adjustment-opportunities'] = opp()
    await mountHeader()
    const row = { id: 5, strategy_id: 7, strategy_name: '"T"', kind: 'plan_loss_stop', text: 'Loss stop reached', fired_at: '2026-11-25T05:32:20Z', fired_line: 'Fired at 11:02', no_longer_true_since: null, no_longer_true_line: null, escalated_at: null, worse_line: null, answers: [] }
    answers['GET /alerts/active'] = active(row)
    answers['GET /adjustment-opportunities'] = opp(rec(5, { rule_id: 'plan.loss_stop' }))
    await tick()
    expect(toasts).toHaveLength(1)
  })
})
