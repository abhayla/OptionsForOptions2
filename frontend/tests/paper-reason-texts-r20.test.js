// GC-TP R-20 / R-15 (ADR-210): every dash on the Paper tab shows the reply's own reason sentence, never a code, and the browser
// writes none of it. The sentences are read from spec/decisions/ADR-210.md (the owner-approved text), put into the reply where the
// server puts them (tests/test_paper_reason_texts.py proves the server sends byte-equal text), and must appear beside the dash.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import fs from 'node:fs'
import path from 'node:path'
import REAL from './fixtures/paper-strategies.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { resetPaperAlerts } from '@/lib/paperAlerts'

const adr = fs.readFileSync(path.resolve(process.cwd(), '..', 'spec', 'decisions', 'ADR-210.md'), 'utf8')
const decision = adr.split('\ndecision:')[1].split('\nstatus:')[0].replace(/\s*\r?\n\s*/g, ' ')
const SENTENCES = Object.fromEntries([...decision.replaceAll("''", "'").matchAll(/\(\d\) (\w+): "(.*?)"/g)].map((m) => [m[1], m[2]]))
const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const clone = () => JSON.parse(JSON.stringify(REAL))
const FUTURE = 'future_unlisted_code'
const GENERIC = 'not available' // the server's generic text for a code it has no template for

async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('ADR-210 sentences beside the Paper tab dashes', () => {
  it('the six paper sentences are found in the ADR', () => {
    expect(Object.keys(SENTENCES).sort()).toEqual(['contract_delisted', 'contract_missing', 'contract_retired', 'model_refused', 'not_priced', 'token_reassigned'])
  })

  it('each contract reason: the paused strip, the card Total / Unbooked and the contract LTP show the reply sentence, not the code', async () => {
    for (const code of ['contract_retired', 'contract_delisted', 'token_reassigned', 'contract_missing']) {
      const d = clone()
      Object.assign(d.totals, { total_text: null, total: null, unbooked_text: null, unbooked: null, totals_reason: code, totals_reason_text: SENTENCES[code] })
      const live = d.strategies.find((s) => s.state === 'LIVE')
      Object.assign(live, { total_text: null, unbooked_text: null, pause_reason: code, pause_reason_text: SENTENCES[code] })
      const open = live.positions.find((p) => p.net_quantity !== 0)
      Object.assign(open, { price_state: code, price_state_text: SENTENCES[code], ltp: null, ltp_text: null })
      answers['GET /paper/strategies'] = ok(d)
      const w = await show()
      expect(t(w, 'totals-reason').text()).toBe(SENTENCES[code])
      const card = w.get(`[data-testid="paper-group"][data-strategy="${live.strategy_id}"]`)
      expect(card.get('[data-testid="paper-total-reason"]').text()).toBe(SENTENCES[code])
      expect(card.get('[data-testid="paper-unbooked-reason"]').text()).toBe(SENTENCES[code])
      expect(card.get('[data-testid="paper-ltp-reason"]').text()).toBe(SENTENCES[code])
      expect(w.html()).not.toContain(code) // the raw code never reaches the page
      w.unmount()
    }
  })

  it('not_priced and model_refused: Charges and Decay show the reply sentence', async () => {
    const d = clone()
    Object.assign(d.totals, { charges: null, charges_text: null, charges_reason: 'not_priced', charges_reason_text: SENTENCES.not_priced,
      decay: null, decay_text: null, decay_reason: 'model_refused', decay_reason_text: SENTENCES.model_refused })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-charges-reason').text()).toBe(SENTENCES.not_priced)
    expect(t(w, 'totals-decay-reason').text()).toBe(SENTENCES.model_refused)
    expect(w.html()).not.toMatch(/not_priced|model_refused/)
  })

  it('an unknown future code: the dash and the server\'s generic text; with no text at all just the dash, never blank text or the code', async () => {
    const d = clone()
    Object.assign(d.totals, { charges: null, charges_text: null, charges_reason: FUTURE, charges_reason_text: GENERIC })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-charges').text()).toBe('—')
    expect(t(w, 'totals-charges-reason').text()).toBe(GENERIC)
    expect(w.html()).not.toContain(FUTURE)
    w.unmount()
    const e = clone()
    Object.assign(e.totals, { charges: null, charges_text: null, charges_reason: FUTURE })
    answers['GET /paper/strategies'] = ok(e)
    const w2 = await show()
    expect(t(w2, 'totals-charges').text()).toBe('—')
    expect(w2.find('[data-testid="totals-charges-reason"]').exists()).toBe(false)
    expect(w2.html()).not.toContain(FUTURE)
  })
})

describe('R-15: the old contract-price stale sentence is not the what-if text', () => {
  it('no source file of the what-if block uses the contract-price stale sentence', () => {
    const block = fs.readFileSync(path.resolve(process.cwd(), 'src', 'components', 'strategy', 'TargetBlock.vue'), 'utf8')
    expect(block).not.toContain('healthSentence')
    expect(block).not.toContain('latest price for this contract')
  })
})
