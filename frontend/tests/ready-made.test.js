// W-125 (REQ-079 AC-2, AC-4, AC-5, AC-7, AC-9; REQ-082 AC-1, AC-3, AC-5): the ready-made panel, the replace prompt, the
// quick picks, the probability figure and the Learn link. Every one is rendered ONLY when GET /features lists its exact
// held name (absent otherwise); the panel computes nothing (the server places strikes).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import PopFigure from '@/components/strategy/PopFigure.vue'
import { VIEW_GROUPS, popText, replacePrompt, templatesInGroup } from '@/lib/readyMade'

let held = ['platform_strikes', 'probability_of_profit']
let loadAnswer
let expiryReply = {} // REQ-135: the server's `expiry_days` rides on the same reply
const gets = []
const posts = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        gets.push(url)
        if (url === '/features') return Promise.resolve({ data: { order_path: 'off', held } })
        if (url === '/strategy-templates') return Promise.resolve({ data: { templates: TEMPLATES } })
        if (url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-10-27', '2026-11-03'], ...expiryReply } })
        return Promise.reject(new Error(url))
      },
      post: (url, body) => { posts.push([url, body]); return loadAnswer(url, body) },
    },
  }
})

const TEMPLATES = [
  { id: 'bull_call_spread', name: 'Bull Call Spread', level: 'Beginner', views: ['bullish'] },
  { id: 'bear_put_spread', name: 'Bear Put Spread', level: 'Beginner', views: ['bearish'] },
  { id: 'iron_condor', name: 'Iron Condor', level: 'Intermediate', views: ['range-bound'] },
  { id: 'long_straddle', name: 'Long Straddle', level: 'Intermediate', views: ['volatile'] },
]
const LABEL = 'Strikes placed by a fixed rule - change them'
const ANSWER = {
  underlying: 'NIFTY',
  legs: [
    { action: 'BUY', instrument: 'CE', strike: '22800.00', expiry: '2026-10-27', instrument_id: 'NSE_FO:1', symbol: 'N22800CE', label: LABEL },
    { action: 'SELL', instrument: 'CE', strike: '23000.00', expiry: '2026-10-27', instrument_id: 'NSE_FO:2', symbol: 'N23000CE', label: LABEL },
  ],
}
const TWO_LEGS = [
  { id: 'a', underlying: 'NIFTY', instrument_id: 'NSE_FO:9', action: 'BUY', lots: 1, planned_entry: '10.00', captured_at: 't' },
  { id: 'b', underlying: 'NIFTY', instrument_id: 'NSE_FO:8', action: 'SELL', lots: 1, planned_entry: '9.00', captured_at: 't' },
]

async function panel(legs = [], query = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
  router.push({ path: '/', query })
  await router.isReady()
  const w = mount(ReadyMadePanel, { props: { legs }, global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => {
  expiryReply = {}
  held = ['platform_strikes', 'probability_of_profit']
  gets.length = 0
  posts.length = 0
  loadAnswer = () => Promise.resolve({ data: ANSWER })
})

describe('REQ-079 AC-2: the list by market view with an expiry picker', () => {
  it('groups the catalogue templates into Bullish / Bearish / Neutral / Other', () => {
    expect(VIEW_GROUPS.map((g) => g.title)).toEqual(['Bullish', 'Bearish', 'Neutral', 'Other'])
    expect(VIEW_GROUPS.map((g) => templatesInGroup(TEMPLATES, g).map((t) => t.id))).toEqual([
      ['bull_call_spread'], ['bear_put_spread'], ['iron_condor'], ['long_straddle']])
  })

  it('shows the panel with the expiry picker and loads the chosen template for the chosen expiry', async () => {
    const w = await panel()
    expect(w.find('[data-testid="ready-made"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="rm-expiry"] option').map((o) => o.text())).toEqual(['27 Oct', '3 Nov']) // REQ-148 AC-2: never raw ISO, even with no day count
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    expect(posts[0]).toEqual(['/strategies/load-template', { underlying: 'NIFTY', template_id: 'bull_call_spread', expiry: '2026-10-27' }])
    const emitted = w.emitted('update:legs')[0][0]
    expect(emitted.map((l) => [l.action, l.instrument_id, l.lots, l.planned_entry])).toEqual([['BUY', 'NSE_FO:1', 1, null], ['SELL', 'NSE_FO:2', 1, null]])
  })
})

const ENTRIES = (rows) => ({ data: { answered_at: 'now', entries: rows } })
const E = (token, price) => ({ exchange_segment: 'NSE_FO', exchange_token: token, planned_entry: price, captured_at: price == null ? null : 'c1', source: 'ltp', reason_code: price == null ? 'no_live_price' : null })
const PE = '/strategies/planned-entry'
const planned = () => posts.filter((p) => p[0] === PE)
const answer = (entries) => (url) => Promise.resolve(url === PE ? entries : { data: ANSWER })

describe('GC-BM F-1: ready-made and quick-pick legs load WITH planned entries (REQ-079 AC-4, REQ-077 AC-1)', () => {
  it('template load: one planned-entry call for all ids; legs carry entries and capture times', async () => {
    loadAnswer = answer(ENTRIES([E('1', '120.50'), E('2', '80.00')]))
    const w = await panel()
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    expect(planned()).toEqual([[PE, { underlying: 'NIFTY', instrument_ids: ['NSE_FO:1', 'NSE_FO:2'] }]])
    const out = w.emitted('update:legs')
    expect(out.length).toBe(1)
    expect(out[0][0].map((l) => [l.instrument_id, l.planned_entry, l.captured_at])).toEqual([['NSE_FO:1', '120.50', 'c1'], ['NSE_FO:2', '80.00', 'c1']])
  })

  it('quick pick: the same capture', async () => {
    loadAnswer = answer(ENTRIES([E('1', '120.50'), E('2', '80.00')]))
    const w = await panel()
    await w.get('[data-testid="rm-strangle-100"]').trigger('click')
    await flushPromises()
    expect(planned().length).toBe(1)
    expect(w.emitted('update:legs')[0][0].map((l) => l.planned_entry)).toEqual(['120.50', '80.00'])
  })

  it('one id with no price: that leg unpriced with its reason, the others priced', async () => {
    loadAnswer = answer(ENTRIES([E('1', '120.50'), E('2', null)]))
    const w = await panel()
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    const legs = w.emitted('update:legs')[0][0]
    expect(legs.map((l) => l.planned_entry)).toEqual(['120.50', null])
    expect(legs[1].captured_at).toBeNull()
    expect(legs[1].reason_code).toBe('no_live_price')
  })

  it('capture call fails: legs still load unpriced and the server message is shown', async () => {
    loadAnswer = (url) => (url === PE
      ? Promise.reject({ message: 'x', status: 503, parts: { what_happened: 'Prices are not available.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
      : Promise.resolve({ data: ANSWER }))
    const w = await panel()
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    const legs = w.emitted('update:legs')[0][0]
    expect(legs.length).toBe(2)
    expect(legs.every((l) => l.planned_entry === null && l.reason_code === 'capture_failed')).toBe(true)
    expect(w.get('[data-testid="rm-error"]').text()).toContain('Prices are not available.')
  })

  it('Replace -> Cancel: no load-template and no planned-entry request', async () => {
    loadAnswer = answer(ENTRIES([E('1', '1.00'), E('2', '2.00')]))
    const w = await panel(TWO_LEGS)
    await w.get('[data-testid="rm-strangle-100"]').trigger('click')
    await w.get('[data-testid="rm-replace-no"]').trigger('click')
    await flushPromises()
    expect(posts).toEqual([])
  })

  it('an older load that finishes after a newer one does not overwrite it', async () => {
    let release
    const slow = new Promise((r) => { release = r })
    let n = 0
    loadAnswer = (url) => {
      if (url === PE) return Promise.resolve(ENTRIES([E('1', '5.00'), E('2', '6.00')]))
      return ++n === 1 ? slow : Promise.resolve({ data: ANSWER })
    }
    const w = await panel()
    await w.get('[data-testid="rm-strangle-100"]').trigger('click')
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    release({ data: ANSWER })
    await flushPromises()
    expect(w.emitted('update:legs').length).toBe(1)
  })
})

describe('REQ-079 AC-4: the fixed-rule label', () => {
  it('every loaded leg carries the server label, shown on the page', async () => {
    const w = await panel()
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    expect(w.emitted('update:legs')[0][0].every((l) => l.fixed_rule_label === LABEL)).toBe(true)
    await w.setProps({ legs: w.emitted('update:legs')[0][0] })
    expect(w.findAll('[data-testid="rm-label"]').map((p) => p.text())).toEqual([LABEL, LABEL])
  })
})

describe('REQ-079 AC-5: replace prompt', () => {
  it('asks before clearing legs; Cancel keeps them and sends nothing', async () => {
    expect(replacePrompt(2)).toBe('Replace the 2 legs in the builder?')
    const w = await panel(TWO_LEGS)
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    expect(w.get('[data-testid="rm-replace-text"]').text()).toBe('Replace the 2 legs in the builder?')
    expect(posts).toEqual([])
    await w.get('[data-testid="rm-replace-no"]').trigger('click')
    await flushPromises()
    expect(posts).toEqual([])
    expect(w.emitted('update:legs')).toBeUndefined()
    expect(w.find('[data-testid="rm-replace"]').exists()).toBe(false)
  })

  it('Replace sends the request and then replaces the legs', async () => {
    const w = await panel(TWO_LEGS)
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await w.get('[data-testid="rm-replace-yes"]').trigger('click')
    await flushPromises()
    expect(posts.filter((p) => p[0] !== PE).length).toBe(1)
    expect(w.emitted('update:legs')[0][0].length).toBe(2)
  })

  it('a refusal shows the server message and leaves the legs alone', async () => {
    loadAnswer = () => Promise.reject({ message: 'x', status: 422, parts: { what_happened: 'The index value is missing or out of date.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const w = await panel()
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="rm-error"]').exists()).toBe(true)
    expect(w.emitted('update:legs')).toBeUndefined()
  })
})

describe('REQ-079 AC-7: quick picks', () => {
  it('offers the underlying distances and posts the user side and distance', async () => {
    const w = await panel()
    expect(w.findAll('[data-testid^="rm-strangle-"]').map((b) => b.text())).toEqual(['50 points', '100 points', '150 points', '200 points'])
    await w.get('[data-testid="rm-side-sell"]').setValue(true)
    await w.get('[data-testid="rm-strangle-100"]').trigger('click')
    await flushPromises()
    expect(posts[0]).toEqual(['/strategies/quick-pick', { underlying: 'NIFTY', kind: 'strangle', distance: 100, side: 'SELL', expiry: '2026-10-27' }])
    await w.get('[data-testid="rm-straddle"]').trigger('click')
    await flushPromises()
    expect(posts.find((p) => p[1].kind === 'straddle')[1]).toEqual({ underlying: 'NIFTY', kind: 'straddle', distance: 0, side: 'SELL', expiry: '2026-10-27' })
  })
})

describe('REQ-079 AC-9: Open in Builder', () => {
  it('?template=<id> loads that template for the nearest expiry', async () => {
    await panel([], { template: 'bull_call_spread' })
    expect(posts[0]).toEqual(['/strategies/load-template', { underlying: 'NIFTY', template_id: 'bull_call_spread', expiry: '2026-10-27' }])
  })
})

describe('AC-1 (both requirements): absent unless the exact name is listed', () => {
  it.each([[[]], [['probability_of_profit']], [['PLATFORM_STRIKES']]])('held=%j: no panel, no list request, no load', async (list) => {
    held = list
    const w = await panel([], { template: 'bull_call_spread' })
    expect(w.find('[data-testid="ready-made"]').exists()).toBe(false)
    expect(w.html()).not.toContain('Ready-made')
    expect(posts).toEqual([])
  })
})

describe('REQ-082 AC-1, AC-3, AC-5: the probability figure', () => {
  it('shows the whole percent with the label only when the switch is on', async () => {
    expect(popText({ percent: 61 })).toBe("Probability of profit: 61% (model estimate from today's prices, not a forecast)")
    const w = mount(PopFigure, { props: { pop: { percent: 61 } } })
    await flushPromises()
    expect(w.get('[data-testid="pop-figure"]').text()).toBe("Probability of profit: 61% (model estimate from today's prices, not a forecast)")
  })

  it('a dash with the reason when the engine gives none; nothing when the figure is absent', async () => {
    expect(popText({ reason: "can't be estimated for legs on different expiries" })).toBe("Probability of profit: - (can't be estimated for legs on different expiries)")
    const none = mount(PopFigure, { props: { pop: null } })
    await flushPromises()
    expect(none.find('[data-testid="pop-figure"]').exists()).toBe(false)
  })

  it('is absent (not a placeholder) when the switch is off', async () => {
    held = ['platform_strikes']
    const w = mount(PopFigure, { props: { pop: { percent: 61 } } })
    await flushPromises()
    expect(w.find('[data-testid="pop-figure"]').exists()).toBe(false)
    expect(w.html()).not.toContain('Probability')
  })
})

describe('REQ-135 AC-2: the expiry picker shows the server\'s day count; the option value stays the ISO date', () => {
  it('labels each expiry with its days and still requests the ISO date', async () => {
    expiryReply = { expiry_days: [{ expiry: '2026-10-27', days: 6 }, { expiry: '2026-11-03', days: 13 }] }
    const w = await panel()
    const opts = w.findAll('[data-testid="rm-expiry"] option')
    expect(opts.map((o) => o.text())).toEqual(['27 Oct (6 days)', '3 Nov (13 days)'])
    expect(opts.map((o) => o.element.value)).toEqual(['2026-10-27', '2026-11-03'])
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    await flushPromises()
    expect(posts.find((p) => p[0] === '/strategies/load-template')[1].expiry).toBe('2026-10-27')
  })

  it('expiry day shows Today (0 days); a null day count shows the date alone', async () => {
    expiryReply = { expiry_days: [{ expiry: '2026-10-27', days: 0 }, { expiry: '2026-11-03', days: null }] }
    const w = await panel()
    expect(w.findAll('[data-testid="rm-expiry"] option').map((o) => o.text())).toEqual(['Today (0 days)', '3 Nov'])
  })
})

describe('W-192 UI-111: the Ready-made tab layout (chips, expiry on the right, 4-per-row cards, Region A underlying)', () => {
  it('has no underlying select of its own and reads the underlying Region A passes', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(ReadyMadePanel, { props: { legs: [], underlying: 'SENSEX' }, global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-testid="rm-underlying"]').exists()).toBe(false)
    expect(gets).toContain('/catalogue/SENSEX/expiries')
    await w.get('[data-testid="rm-template-bull_call_spread"]').trigger('click')
    expect(posts[0]).toEqual(['/strategies/load-template', { underlying: 'SENSEX', template_id: 'bull_call_spread', expiry: '2026-10-27' }])
    gets.length = 0
    await w.setProps({ underlying: 'NIFTY' })
    await flushPromises()
    expect(gets).toContain('/catalogue/NIFTY/expiries')
  })

  it('shows the four view chips with the selected one accent-filled, and the shape cards in a 4-per-row grid by name', async () => {
    const w = await panel()
    const chips = VIEW_GROUPS.map((g) => w.get(`[data-testid="rm-group-${g.key}"]`))
    expect(chips.map((c) => c.text())).toEqual(['Bullish', 'Bearish', 'Neutral', 'Other'])
    expect(chips[0].attributes('aria-pressed')).toBe('true')
    expect(chips[0].classes()).toContain('bg-accent')
    expect(chips[1].classes()).not.toContain('bg-accent')
    await chips[2].trigger('click')
    expect(w.get('[data-testid="rm-group-neutral"]').classes()).toContain('bg-accent')
    expect(w.get('[data-testid="rm-templates"]').classes()).toContain('sm:grid-cols-4')
    expect(w.get('[data-testid="rm-template-iron_condor"]').text()).toBe('Iron Condor')
  })
})
