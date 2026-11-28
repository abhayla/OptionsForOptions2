// Lane FJ r3 (28 Nov 2026), PC W-20 / O-A-07 confirmation on the head: ONE stop shows exactly the three ADR-330 (55) decision lines and no second wording
// beside them (the "sold-leg line is a second wording" complaint); the one-sentence form carries the plan's exact text, date and
// "Sold option with less protection: <contract>" as the server sent them. No fix unless red.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const key = Object.keys(answers).find((k) => k === `${method} ${url}`) ?? Object.keys(answers).find((k) => k.endsWith('*') && `${method} ${url}`.startsWith(k.slice(0, -1)))
    const a = key ? answers[key] : null
    return a ? a(url, body) : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStops from '@/components/strategy/PaperStops.vue'

const TEXT = 'If this stop fires, max loss becomes Rs 12,000 (now Rs 8,500).'
const legs = [{ index: 5000, label: 'NIFTY 22300 PE', contractId: '5000' }, { index: 5001, label: 'NIFTY 22400 PE', contractId: '5001' }]
const ok = (data) => () => Promise.resolve({ data })
const yes = (text = TEXT) => ({ state: 'yes', max_loss_before: null, max_loss_after: null, warning_text: text })

async function open() {
  answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
  const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs }, global: { stubs: {} } })
  await flushPromises()
  return w
}
const type = async (w, i, v) => { await w.get(`[data-testid="stop-level-${i}"]`).setValue(v) }
const wait = async (ms = 450) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
const line = (w, i = 5000) => w.find(`[data-testid="stop-risk-${i}"]`)

beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())
beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

const THREE = ['If this stop fires, the sold NIFTY 1 Dec 25850 PE is left without protection.', 'Max loss now: Rs 7,800.00.',
  'Max loss then: Rs 16,74,725.00 (worst case: NIFTY at zero).']
const SENTENCE = 'If this stop fires, max loss becomes Rs 12,000.00 by 1 Dec 2026. Sold option with less protection: NIFTY 1 Dec 25850 PE.'

describe('one stop, one wording', () => {
  it('three lines: exactly three risk rows, no other risk or sold-leg text in the leg row', async () => {
    answers['GET *'] = ok({ ...yes(THREE.join('\n')), warning_lines: THREE })
    const w = await open()
    await type(w, 5000, '5.00')
    await wait()
    expect(w.findAll('[data-testid^="stop-risk-line-5000-"]').map((r) => r.text())).toEqual(THREE)
    const slot = w.get('[data-testid="stop-risk-slot-5000"]').text()
    expect(slot).toBe(THREE.join(''))
    expect(slot).not.toContain('Sold option with less protection')
    expect(slot).not.toContain('max loss becomes')
    expect(w.findAll('[data-testid^="stop-risk-"]').filter((e) => /^stop-risk-5000$/.test(e.attributes('data-testid')))).toHaveLength(1)
  })
  it('one-sentence form: the sentence is printed exactly as sent, with its date and the sold option naming the contract', async () => {
    answers['GET *'] = ok(yes(SENTENCE))
    const w = await open()
    await type(w, 5000, '5.00')
    await wait()
    expect(line(w).text()).toBe(SENTENCE)
    expect(line(w).text()).toContain('1 Dec 2026')
    expect(line(w).text()).toContain('Sold option with less protection: NIFTY 1 Dec 25850 PE.')
  })
})
