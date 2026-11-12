// GC-TRACK1 k10 (ADR-292 (1), (3), (4); REQ-109 AC-1): what a held strategy shows in the paper list and the paper book.
// Texts are ADR-292's own words; a plain paper strategy (held null) and an unreadable held block show nothing held.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'

const NOTE = 'Changes you make at your broker are not seen by the app. Record them here.'
const HELD = { source: 'held_elsewhere', entry_at: '2026-11-12T09:20:00+05:30', broker: '"Zerodha"', rules_start_at: '2026-11-12T09:45:00+05:30' }
const leg = (i) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const item = (over = {}) => withPriceTexts({
  strategy_id: 48, name: '"Condor"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)], ...over,
})
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()

async function list(over) {
  answers['GET /tracking'] = () => Promise.resolve({ data: { strategies: [item(over)], answered_at: '2026-10-28T06:00:00Z' } })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {} })

describe('paper list: a held strategy', () => {
  it('shows the label, the entry time (IST, short), "Rules start from", the broker as given, and the record-here line beside the actions', async () => {
    const w = await list({ held: HELD })
    expect(t(w, 'held-label').text()).toBe('Held at my broker')
    expect(t(w, 'held-entry').text()).toBe('Entry 12 Nov 09:20')
    expect(t(w, 'held-rules').text()).toBe('Rules start from 12 Nov 09:45')
    expect(t(w, 'held-broker-name').text()).toBe('"Zerodha"')
    expect(t(w, 'paper-actions').text()).toContain(NOTE)
  })
  it('rules_start_at null -> no "Rules start" line (never a guessed time); no broker -> no broker line', async () => {
    const w = await list({ held: { ...HELD, rules_start_at: null, broker: null } })
    expect(has(w, 'held-entry')).toBe(true)
    expect(has(w, 'held-rules')).toBe(false)
    expect(has(w, 'held-broker-name')).toBe(false)
    expect(w.text()).not.toContain('Rules start')
  })
  it('a plain paper strategy (held null) shows none of it', async () => {
    const w = await list({ held: null })
    expect(has(w, 'held-note')).toBe(false)
    expect(w.text()).not.toContain('Held at my broker')
    expect(w.text()).not.toContain(NOTE)
  })
  it.each([['missing key', undefined], ['a string', 'held'], ['an array', []], ['entry_at unparsable', { ...HELD, entry_at: 'yesterday' }], ['entry_at without an offset', { ...HELD, entry_at: '2026-11-12T09:20:00' }]])(
    'held %s -> nothing held shown, the list still renders', async (_n, held) => {
      const w = await list(held === undefined ? {} : { held })
      expect(has(w, 'paper-group')).toBe(true)
      expect(has(w, 'held-note')).toBe(false)
      expect(w.text()).not.toContain(NOTE)
    })
})

describe('paper book: a held strategy', () => {
  const book = (over = {}) => ({ strategy_id: 48, name: '"Condor"', orders: [], positions: [], total_text: '+0.00', charges_text: '0.00', ...over })
  const mountBook = (b) => mount(PaperBookPanel, { props: { book: b, net: [] } })

  it('shows the label, entry, rules start, broker and the record-here line', () => {
    const w = mountBook(book({ held: HELD }))
    expect(t(w, 'held-label').text()).toBe('Held at my broker')
    expect(t(w, 'held-entry').text()).toBe('Entry 12 Nov 09:20')
    expect(t(w, 'held-rules').text()).toBe('Rules start from 12 Nov 09:45')
    expect(t(w, 'held-broker-name').text()).toBe('"Zerodha"')
    expect(t(w, 'held-record-note').text()).toBe(NOTE)
  })
  it.each([['null', null], ['missing', undefined], ['not an object', 5], ['entry_at unparsable', { ...HELD, entry_at: 'x' }]])('held %s -> none of it, no crash', (_n, held) => {
    const w = mountBook(book(held === undefined ? {} : { held }))
    expect(has(w, 'held-note')).toBe(false)
    expect(has(w, 'book-strip')).toBe(true)
  })
})
