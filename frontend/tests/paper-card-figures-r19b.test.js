// GC-TP R-19b (Sensibull 090; ADR-207): each paper strategy card shows Breakeven, Max Profit and Max Loss, and a Greeks toggle (off)
// with per-leg and net Greeks. Every reply below is a REAL reply of GET /paper/strategies captured from
// tests_app/test_paper_list_figures.py (R_19B_CAPTURE=1; tests/fixtures/paper-list-r19b/*.json): live, paused (prices stale),
// multi_expiry and exited. The browser computes nothing: each text expected is the reply's own, as sent.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import LIVE from './fixtures/paper-list-r19b/live.json'
import PAUSED from './fixtures/paper-list-r19b/paused.json'
import MULTI from './fixtures/paper-list-r19b/multi_expiry.json'
import EXITED from './fixtures/paper-list-r19b/exited.json'

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
import { PAPER_NO_FIGURE } from '@/lib/paperList'
import { UNREADABLE_TEXT } from '@/lib/tracking'
import { resetPaperAlerts } from '@/lib/paperAlerts'

const ok = (data) => () => Promise.resolve({ data })
const clone = (x) => JSON.parse(JSON.stringify(x))
const CODE = /prices_not_live|multi_expiry|no_iv|model_refused|exited|[a-z]+_[a-z]+_[a-z_]+/

async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const card = (w, id) => w.get(`[data-testid="paper-group"][data-strategy="${id}"]`)
const q = (c, id) => c.get(`[data-testid="${id}"]`)
const open = (reply) => reply.strategies.find((s) => s.state !== 'EXITED')

beforeEach(() => { answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('the card figures (the real reply)', () => {
  it('core: Breakeven, Max Profit and Max Loss are the reply texts as sent', async () => {
    answers['GET /paper/strategies'] = ok(LIVE)
    const s = open(LIVE)
    expect(s.breakevens_text.length).toBeGreaterThan(0)
    const c = card(await show(), s.strategy_id)
    expect(q(c, 'paper-breakeven').text()).toBe(s.breakevens_text.join(', '))
    expect(q(c, 'paper-max-profit').text()).toBe(s.max_profit_text)
    expect(q(c, 'paper-max-loss').text()).toBe(s.max_loss_text)
    expect(c.find('[data-testid="paper-breakeven-reason"]').exists()).toBe(false)
  })

  it('Greeks toggle is off by default, then shows every leg and the net as the reply sends them', async () => {
    answers['GET /paper/strategies'] = ok(LIVE)
    const s = open(LIVE)
    const w = await show()
    const c = card(w, s.strategy_id)
    expect(c.find(`[data-testid="paper-greeks-${s.strategy_id}"]`).exists()).toBe(false)
    expect(q(c, `greeks-toggle-${s.strategy_id}`).attributes('aria-pressed')).toBe('false')
    await q(c, `greeks-toggle-${s.strategy_id}`).trigger('click')
    expect(q(c, `greeks-toggle-${s.strategy_id}`).attributes('aria-pressed')).toBe('true')
    const legs = c.findAll('[data-testid="paper-greeks-leg"]')
    expect(legs).toHaveLength(s.greeks.legs.length)
    legs.forEach((row, i) => {
      for (const k of ['delta', 'gamma', 'theta', 'vega']) expect(row.get(`[data-testid="paper-greeks-leg-${k}"]`).text()).toBe(s.greeks.legs[i][`${k}_text`])
    })
    for (const k of ['delta', 'gamma', 'theta', 'vega']) expect(q(c, `paper-greeks-net-${k}`).text()).toBe(s.greeks.net[`${k}_text`])
  })

  it('multi-expiry: Breakeven, Max Profit and Max Loss are a dash with the existing sentence, never 0', async () => {
    answers['GET /paper/strategies'] = ok(MULTI)
    const s = open(MULTI)
    expect(s.breakevens_reason).toBe('multi_expiry')
    const c = card(await show(), s.strategy_id)
    expect(s.breakevens_reason_text).toBe('Breakeven is exact only for a single-expiry strategy') // the pinned ADR-211 (5) template
    for (const [id, sent] of [['breakeven', s.breakevens_reason_text], ['max-profit', s.extremes_reason_text], ['max-loss', s.extremes_reason_text]]) {
      expect(q(c, `paper-${id}`).text()).toBe(PAPER_NO_FIGURE)
      expect(q(c, `paper-${id}-reason`).text()).toBe(sent) // as sent: the browser writes no sentence
    }
    expect(c.text()).not.toMatch(CODE)
  })

  it('prices not live: Max Profit and Breakeven stay (they need no price); Greeks are a dash with the paused sentence', async () => {
    answers['GET /paper/strategies'] = ok(PAUSED)
    const s = open(PAUSED)
    expect(s.greeks).toBeNull()
    const w = await show()
    const c = card(w, s.strategy_id)
    expect(q(c, 'paper-max-profit').text()).toBe(s.max_profit_text)
    await q(c, `greeks-toggle-${s.strategy_id}`).trigger('click')
    expect(q(c, 'paper-greeks-reason').text()).toContain(PAPER_NO_FIGURE)
    expect(s.greeks_reason_text).toBeTruthy()
    expect(q(c, 'paper-greeks-reason').text()).toContain(s.greeks_reason_text)
    expect(c.text()).not.toMatch(CODE)
  })

  it('a fully exited strategy: every figure is a dash with the Exited sentence, never 0', async () => {
    answers['GET /paper/strategies'] = ok(EXITED)
    const s = EXITED.strategies[0]
    const w = await show()
    await w.get('[data-testid="show-closed"]').setValue(true)
    const c = card(w, s.strategy_id)
    for (const [id, sent] of [['breakeven', s.breakevens_reason_text], ['max-profit', s.extremes_reason_text], ['max-loss', s.extremes_reason_text]]) {
      expect(q(c, `paper-${id}`).text()).toBe(PAPER_NO_FIGURE)
      expect(q(c, `paper-${id}-reason`).text()).toBe(sent)
    }
    expect(s.breakevens_reason_text).toBe('Exited')
    await q(c, `greeks-toggle-${s.strategy_id}`).trigger('click')
    expect(q(c, 'paper-greeks-reason').text()).toContain(s.greeks_reason_text)
  })

  it('an older reply without the new fields: a dash with the unavailable sentence, never 0 and never a code', async () => {
    const old = clone(LIVE)
    for (const s of old.strategies) {
      for (const k of Object.keys(s)) if (/^(breakevens|max_|profit_left|loss_left|extremes_reason|greeks)/.test(k)) delete s[k]
    }
    answers['GET /paper/strategies'] = ok(old)
    const s = open(old)
    const w = await show()
    const c = card(w, s.strategy_id)
    for (const id of ['breakeven', 'max-profit', 'max-loss']) {
      expect(q(c, `paper-${id}`).text()).toBe(PAPER_NO_FIGURE)
      expect(q(c, `paper-${id}-reason`).text()).toBe(UNREADABLE_TEXT)
    }
    await q(c, `greeks-toggle-${s.strategy_id}`).trigger('click')
    expect(q(c, 'paper-greeks-reason').text()).toContain(UNREADABLE_TEXT)
    expect(c.text()).not.toMatch(CODE)
  })

  it('a half-sent Greeks block (a leg without a text) is absent, never a partial table', async () => {
    const bad = clone(LIVE)
    const s = open(bad)
    delete s.greeks.legs[0].vega_text
    answers['GET /paper/strategies'] = ok(bad)
    const w = await show()
    const c = card(w, s.strategy_id)
    await q(c, `greeks-toggle-${s.strategy_id}`).trigger('click')
    expect(c.findAll('[data-testid="paper-greeks-leg"]')).toHaveLength(0)
    expect(q(c, 'paper-greeks-reason').text()).toContain(PAPER_NO_FIGURE)
  })

  it('a failed list request shows no figure at all, no Breakeven and no Greeks toggle', async () => {
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'down', parts: null, status: 500 })
    const w = await show()
    expect(w.find('[data-testid="paper-breakeven"]').exists()).toBe(false)
    expect(w.find('[data-testid="paper-max-profit"]').exists()).toBe(false)
    expect(w.findAll('[data-testid^="greeks-toggle-"]')).toHaveLength(0)
  })
})
