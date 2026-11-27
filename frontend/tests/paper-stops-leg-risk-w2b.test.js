// W2-B (ADR-330 (6), ADR-008): the Stops panel's leg-stop risk line. When a leg and a valid level are typed, the panel reads
// GET /paper/strategies/{id}/leg-stop-risk?contract_id=&level= (debounced) and prints the server's `warning_text` when state is
// "yes", nothing otherwise; it never blocks the save. Real case 26 Nov: NIFTY 22300 PE leg, level 130.00, server line below.
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
const RISK = '/paper/strategies/48/leg-stop-risk?contract_id=5000&level='
const legs = [{ index: 5000, label: 'NIFTY 22300 PE', contractId: '5000' }, { index: 5001, label: 'NIFTY 22400 PE', contractId: '5001' }]
const ok = (data) => () => Promise.resolve({ data })
const yes = (text = TEXT) => ({ state: 'yes', max_loss_before: null, max_loss_after: null, warning_text: text })
const riskCalls = () => calls.filter((c) => c[0] === 'GET' && c[1].includes('leg-stop-risk')).map((c) => c[1])

async function open() {
  answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
  const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs }, global: { stubs: {} } })
  await flushPromises()
  return w
}
const type = async (w, i, v) => { await w.get(`[data-testid="stop-level-${i}"]`).setValue(v) }
const wait = async (ms = 450) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
const line = (w, i = 5000) => w.find(`[data-testid="stop-risk-${i}"]`)
const save = (w, i = 5000) => w.get(`[data-testid="stop-save-${i}"]`)

beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

const THREE = ['If this stop fires, the sold NIFTY 1 Dec 25850 PE is left without protection.', 'Max loss now: Rs 7,800.00.',
  'Max loss then: Rs 16,74,725.00 (worst case: NIFTY at zero).']

const LOADING = 'Working out max loss for this stop...'
const loading = (w, i = 5000) => w.find(`[data-testid="stop-risk-loading-${i}"]`)

describe('UX-A02: a loading line while the stop\'s max loss is being worked out, never an empty gap', () => {
  it('shows the loading line from the moment a valid level is typed until the answer arrives, then the answer replaces it', async () => {
    let release
    answers['GET *'] = () => new Promise((res) => { release = () => res({ data: yes() }) })
    const w = await open()
    expect(loading(w).exists()).toBe(false) // nothing typed: nothing to work out
    await type(w, 5000, '130.00')
    expect(loading(w).text()).toBe(LOADING) // while the debounce waits
    await wait()
    expect(riskCalls()).toHaveLength(1)
    expect(loading(w).text()).toBe(LOADING) // while the server works
    release()
    await flushPromises()
    expect(loading(w).exists()).toBe(false)
    expect(line(w).text()).toBe(TEXT)
  })
  it('an answer of no, cannot_tell or a failed read removes the loading line and prints nothing', async () => {
    for (const reply of [() => Promise.resolve({ data: { state: 'no', warning_text: null } }), () => Promise.reject(new Error('x'))]) {
      calls.length = 0
      answers['GET *'] = reply
      const w = await open()
      await type(w, 5000, '130.00')
      await wait()
      expect(loading(w).exists()).toBe(false)
      expect(line(w).exists()).toBe(false)
    }
  })
  it('an invalid level shows no loading line', async () => {
    answers['GET *'] = ok(yes())
    const w = await open()
    await type(w, 5000, '130.03')
    expect(loading(w).exists()).toBe(false)
  })
})

describe('ADR-330 (55) three lines, each its own line, printed as the server sent them', () => {
  it('prints each of the server\'s lines on its own line, in order, with no figure of its own', async () => {
    answers['GET *'] = ok({ ...yes(THREE.join('\n')), warning_lines: THREE })
    const w = await open()
    await type(w, 5000, '5.00')
    await wait()
    const rows = w.findAll('[data-testid^="stop-risk-line-5000-"]')
    expect(rows.map((r) => r.text())).toEqual(THREE)
    expect(line(w).text()).toBe(THREE.join(''))
  })
  it('a lines list that is not three non-empty texts falls back to the one sentence, never half a list', async () => {
    for (const bad of [[], ['only one'], ['a', '', 'c'], ['a', 1, 'c'], 'text']) {
      answers['GET *'] = ok({ ...yes(), warning_lines: bad })
      const w = await open()
      await type(w, 5000, '5.00')
      await wait()
      expect(w.findAll('[data-testid^="stop-risk-line-5000-"]'), JSON.stringify(bad)).toHaveLength(0)
      expect(line(w).text()).toBe(TEXT)
    }
  })
})

describe('W2-B leg-stop risk line', () => {
  it('yes: prints the server text exactly, asks once with the typed contract and level, Save stays enabled', async () => {
    answers['GET *'] = ok(yes())
    answers['GET /paper/strategies/48/triggers'] = ok({ triggers: [] })
    const w = await open()
    await type(w, 5000, '130.00')
    expect(riskCalls()).toEqual([]) // debounced: nothing yet
    await wait()
    expect(riskCalls()).toEqual([`${RISK}130.00`])
    expect(line(w).text()).toBe(TEXT)
    expect(save(w).attributes('disabled')).toBeUndefined()
  })
  it('no and cannot_tell: nothing printed, Save enabled', async () => {
    for (const state of ['no', 'cannot_tell']) {
      calls.length = 0
      answers['GET /paper/strategies/48/leg-stop-risk*'] = ok({ state, max_loss_before: null, max_loss_after: null, warning_text: null })
      const w = await open()
      await type(w, 5000, '130.00')
      await wait()
      expect(riskCalls()).toHaveLength(1)
      expect(line(w).exists(), state).toBe(false)
      expect(save(w).attributes('disabled')).toBeUndefined()
    }
  })
  it('yes with no text (a reply that breaks its own shape): nothing printed', async () => {
    answers['GET /paper/strategies/48/leg-stop-risk*'] = ok({ state: 'yes', warning_text: null })
    const w = await open()
    await type(w, 5000, '130.00')
    await wait()
    expect(line(w).exists()).toBe(false)
  })
  it('error (network, 404, 422): nothing printed, Save enabled, no retry', async () => {
    for (const status of [null, 404, 422]) {
      calls.length = 0
      answers['GET /paper/strategies/48/leg-stop-risk*'] = () => Promise.reject({ message: 'x', status, parts: null })
      const w = await open()
      await type(w, 5000, '130.00')
      await wait(5000)
      expect(riskCalls(), String(status)).toHaveLength(1)
      expect(line(w).exists()).toBe(false)
      expect(save(w).attributes('disabled')).toBeUndefined()
      expect(w.find('[data-testid="stops-error"]').exists()).toBe(false)
    }
  })
  it('an invalid or empty level asks nothing', async () => {
    answers['GET /paper/strategies/48/leg-stop-risk*'] = ok(yes())
    const w = await open()
    for (const v of ['', '0', '130.03', 'abc', '-5']) { await type(w, 5000, v); await wait() }
    expect(riskCalls()).toEqual([])
    expect(line(w).exists()).toBe(false)
  })
  it('level changed after a yes: the line goes at once, back only with the new answer', async () => {
    answers['GET /paper/strategies/48/leg-stop-risk*'] = (url) => Promise.resolve({ data: yes(url.endsWith('=130.00') ? TEXT : 'If this stop fires, max loss becomes Rs 15,000 (now Rs 8,500).') })
    const w = await open()
    await type(w, 5000, '130.00')
    await wait()
    expect(line(w).text()).toBe(TEXT)
    await type(w, 5000, '140.00')
    expect(line(w).exists()).toBe(false) // before the new answer
    await wait()
    expect(line(w).text()).toBe('If this stop fires, max loss becomes Rs 15,000 (now Rs 8,500).')
    await type(w, 5000, '141')
    await type(w, 5000, '')
    expect(line(w).exists()).toBe(false)
  })
  it('out of order answers: the old answer, arriving last, never shows', async () => {
    const pending = {}
    answers['GET /paper/strategies/48/leg-stop-risk*'] = (url) => new Promise((res) => { pending[url.split('level=')[1]] = res })
    const w = await open()
    await type(w, 5000, '130.00')
    await wait()
    await type(w, 5000, '140.00')
    await wait()
    expect(Object.keys(pending).sort()).toEqual(['130.00', '140.00'])
    pending['140.00']({ data: yes('NEW') })
    await flushPromises()
    expect(line(w).text()).toBe('NEW')
    pending['130.00']({ data: yes('OLD') })
    await flushPromises()
    expect(line(w).text()).toBe('NEW')
  })
  it('an answer for a level no longer in the box is dropped (answer arrives after the box moved on)', async () => {
    const pending = {}
    answers['GET /paper/strategies/48/leg-stop-risk*'] = (url) => new Promise((res) => { pending[url.split('level=')[1]] = res })
    const w = await open()
    await type(w, 5000, '130.00')
    await wait()
    await type(w, 5000, '')
    pending['130.00']({ data: yes('OLD') })
    await flushPromises()
    expect(line(w).exists()).toBe(false)
  })
  it('each leg has its own line; typing in leg 2 does not show leg 1\'s text there', async () => {
    answers['GET /paper/strategies/48/leg-stop-risk*'] = (url) => Promise.resolve({ data: yes(url.includes('contract_id=5000') ? 'ONE' : 'TWO') })
    const w = await open()
    await type(w, 5000, '130.00')
    await type(w, 5001, '131.00')
    await wait()
    expect(line(w, 5000).text()).toBe('ONE')
    expect(line(w, 5001).text()).toBe('TWO')
  })
  it('Save still posts the stop with the line showing (the line never gates it)', async () => {
    answers['GET /paper/strategies/48/leg-stop-risk*'] = ok(yes())
    answers['POST /paper/strategies/48/triggers'] = ok({ triggers: [] })
    const w = await open()
    await type(w, 5000, '130.00')
    await wait()
    await save(w).trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST')).toHaveLength(1)
  })
})
