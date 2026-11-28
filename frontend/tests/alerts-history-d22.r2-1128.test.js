// Lane TB (R2, 28 Nov) I-60: Alerts > History when ONE of its two reads fails. Extends alerts-history-d22.test.js.
// The message must be the whole catalogue sentence (not a cut-off "could not get an answer from the"), must sit under the
// half that failed, and the half that answered must still show its rows.
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

import AlertsPage from '@/pages/AlertsPage.vue'
import { resetOpenRecords, resetActiveAlerts } from '@/lib/paperAlerts'

const STOP = { kind: 'stop', strategy_id: 160, strategy_name: '"Condor C3"', at: '2026-11-23T05:51:58Z', title: 'Paper strategy — Condor C3',
  body: 'Stop-loss on the index: NIFTY crossed above 25,720.00; NIFTY was at 25,721.40 at that moment. A paper exit only: no order was sent to Zerodha.' }
const ANSWERED = { id: 9, strategy_id: 160, strategy_name: '"Condor C3"', text: 'Your stop was close to the index.', fired_line: 'Fired at 11:21', answer_label: 'Keep', answered_at: '2026-11-23T05:55:00Z' }
// R3 join: FC2 (I-86) made the failed-load sentence of every list page ONE shared line with a Retry button (lib/listFailed.js);
// the I-60 intent (the whole sentence, under the half that failed, the other half's rows kept) stands, in FC2's words.
const SENTENCE = 'Could not load this list. Nothing was changed.'

async function mountAt(path) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; resetActiveAlerts(); resetOpenRecords() })

describe('I-60 Alerts > History partial failure message', () => {
  it('I-60: the records read fails, the answered read works: full sentence under the records heading, answered rows still shown', async () => {
    answers['GET /alerts/answered'] = () => Promise.resolve({ data: { items: [ANSWERED] } })
    // no answer for /paper/alerts/records: a dropped connection
    const w = await mountAt('/alerts/history')
    expect(w.findAll('[data-testid="answered-row"]')).toHaveLength(1)
    expect(w.get('[data-testid="records-error-error"]').text()).toBe(SENTENCE)
    expect(w.find('[data-testid="answered-error-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="record-row"]').exists()).toBe(false)
  })

  it('I-60: the answered read fails, the records read works: full sentence under the answered heading, record rows still shown', async () => {
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [STOP] } })
    const w = await mountAt('/alerts/history')
    expect(w.findAll('[data-testid="record-row"]')).toHaveLength(1)
    expect(w.get('[data-testid="answered-error-error"]').text()).toBe(SENTENCE)
    expect(w.find('[data-testid="records-error-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
  })

  it('I-60: both reads fail: each half shows its own full sentence, no "No stops yet" line', async () => {
    const w = await mountAt('/alerts/history')
    expect(w.get('[data-testid="answered-error-error"]').text()).toBe(SENTENCE)
    expect(w.get('[data-testid="records-error-error"]').text()).toBe(SENTENCE)
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
  })
})
