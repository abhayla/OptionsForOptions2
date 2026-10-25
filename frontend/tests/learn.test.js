// W-117 (REQ-011 AC-1; REQ-009 AC-4/AC-6; ADR-114, ADR-003): Learn, Alerts and Market context with a fake route reply and a
// fake index socket. Texts shown must equal the fake reply's texts as given; the empty lines are the brief's quoted wording.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let templatesAnswer = null // { templates: [...] } or an Error to reject with
let indicesAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => {
    if (url === '/strategy-templates') {
      return templatesAnswer instanceof Error ? Promise.reject(templatesAnswer) : Promise.resolve({ data: templatesAnswer })
    }
    return Promise.resolve({ data: indicesAnswer })
  } } }
})
import { routes } from '@/router/routes'
import SOURCE from '@/lib/learnContent.js?raw'
import { CONCEPTS, HOW_IT_WORKS, PLATFORM, SHAPES, STRATEGY_PARTS, STRATEGY_TEXT, allLearnText } from '@/lib/learnContent'
import REAL from './fixtures/strategy-templates-real.json'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() { this.readyState = 3 }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const tpl = (id, name, description, level, views) => ({ id, name, description, level, views, objectives: ['directional'] })
const REPLY = { templates: [
  tpl('t_adv', 'Advanced One', 'Advanced words as sent.', 'Advanced', ['volatile']),
  tpl('t_beg', 'Beginner One', 'Beginner words as sent.', 'Beginner', ['bullish', 'range-bound']),
  tpl('t_int', 'Intermediate One', 'Intermediate words as sent.', 'Intermediate', ['bearish']),
  tpl('t_beg2', 'Beginner Two', 'Second beginner words.', 'Beginner', ['bearish']),
] }
const row = (underlying, value, at, health = 'available') => ({
  underlying, instrument_id: underlying === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at, health })
const live = () => ({ state: 'LIVE', answered_at: '2026-10-19T03:50:01+00:00',
  indices: [row('NIFTY', '24500.50', '2026-10-19T09:20:00+05:30'), row('SENSEX', '80100.25', '2026-10-19T09:20:00+05:30')] })
const notConnected = () => ({ state: 'NOT_CONNECTED', answered_at: '2026-10-19T03:50:09+00:00',
  indices: [row('NIFTY', null, null, null), row('SENSEX', null, null, null)] })

async function open(path) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const App = { template: '<router-view />' }
  const wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  FakeSocket.all = []
  templatesAnswer = REPLY
  indicesAnswer = notConnected()
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('Learn', () => {
  it('AC-1: Strategy education shows the cards grouped by level, Beginner first, texts as sent', async () => {
    const w = await open('/learn/strategy-education')
    expect(w.get('[data-testid="learn"]').attributes('data-state')).toBe('list')
    expect(w.findAll('[data-testid="level-title"]').map((e) => e.text())).toEqual(['Beginner', 'Intermediate', 'Advanced'])
    expect(w.findAll('[data-testid="template-name"]').map((e) => e.text()))
      .toEqual(['Beginner One', 'Beginner Two', 'Intermediate One', 'Advanced One'])
    expect(w.findAll('[data-testid="template-description"]').map((e) => e.text())).toEqual([
      'Beginner words as sent.', 'Second beginner words.', 'Intermediate words as sent.', 'Advanced words as sent.'])
    expect(w.findAll('[data-testid="template-views"]')[0].text()).toBe('Market view: bullish, range-bound')
  })

  it('AC-1: an empty catalogue shows the same line', async () => {
    templatesAnswer = { templates: [] }
    const w = await open('/learn/strategy-education')
    expect(w.get('[data-testid="learn-empty"]').text()).toBe('Nothing published here yet.')
  })

  it('AC-1: a failed read shows the server message and no cards', async () => {
    const parts = { what_happened: 'W', impact: 'I', what_is_blocked: 'B', next_action: 'N' }
    templatesAnswer = Object.assign(new Error('x'), { parts })
    const w = await open('/learn/strategy-education')
    expect(w.get('[data-testid="learn"]').attributes('data-state')).toBe('error')
    expect(w.get('[data-testid="learn-error-what"]').text()).toBe('W')
    expect(w.findAll('[data-testid="template-card"]')).toHaveLength(0)
  })

  it('AC-1: an unreadable reply fails closed to an error, not an empty list', async () => {
    templatesAnswer = { nope: 1 }
    const w = await open('/learn/strategy-education')
    expect(w.get('[data-testid="learn"]').attributes('data-state')).toBe('error')
  })

  it('AC-1: no order or execute link on the page (ADR-002)', async () => {
    const w = await open('/learn/strategy-education')
    expect(w.findAll('a').filter((a) => /execute|order/i.test(a.attributes('href') ?? ''))).toHaveLength(0)
  })
})

describe('Learn tabs, content home, strategy page (GC-6 LEARN)', () => {
  const contentText = allLearnText()

  it('AC-1: the three tabs are links in order and the active one is marked', async () => {
    const w = await open('/learn/options-concepts')
    expect(w.findAll('[data-testid="learn-tabs"] a').map((a) => a.text()))
      .toEqual(['Strategy education', 'Options concepts', 'Platform guidance'])
    expect(w.get('[data-testid="tab-options-concepts"]').attributes('aria-current')).toBe('page')
    expect(w.get('[data-testid="tab-strategy-education"]').attributes('aria-current')).toBeUndefined()
  })

  it('AC-1: Options concepts lists the 8 lessons from the content module, titles and summaries as written there', async () => {
    const w = await open('/learn/options-concepts')
    expect(w.findAll('[data-testid="lesson-title"]').map((e) => e.text())).toEqual(CONCEPTS.map((l) => l.title))
    expect(w.findAll('[data-testid="lesson-summary"]').map((e) => e.text())).toEqual(CONCEPTS.map((l) => l.summary))
    expect(CONCEPTS.map((l) => l.id)).toEqual(['call', 'put', 'strike', 'expiry', 'premium', 'lot-size', 'iv', 'greeks'])
  })

  it('AC-1: Platform guidance lists the 5 lessons from the content module', async () => {
    const w = await open('/learn/platform-guidance')
    expect(w.findAll('[data-testid="lesson-title"]').map((e) => e.text())).toEqual(PLATFORM.map((l) => l.title))
    expect(PLATFORM).toHaveLength(5)
  })

  it('AC-1: a lesson opens in a detail view with its lines, and Back returns to the list', async () => {
    const w = await open('/learn/platform-guidance')
    await w.findAll('[data-testid="card-open"]')[2].trigger('click')
    expect(w.get('[data-testid="detail-title"]').text()).toBe('How orders reach Zerodha')
    expect(w.findAll('[data-testid="lesson-line"]').map((e) => e.text())).toEqual(PLATFORM[2].body)
    await w.get('[data-testid="detail-back"]').trigger('click')
    expect(w.findAll('[data-testid="lesson-card"]')).toHaveLength(5)
  })

  it('AC-1: the search box filters by title only and says so when nothing matches', async () => {
    const w = await open('/learn/options-concepts')
    await w.get('[data-testid="learn-search"]').setValue('PUT')
    expect(w.findAll('[data-testid="lesson-title"]').map((e) => e.text())).toEqual(['Put option'])
    await w.get('[data-testid="learn-search"]').setValue('zzzz')
    expect(w.get('[data-testid="learn-no-match"]').text()).toBe('No lesson matches that search.')
    expect(w.findAll('[data-testid="lesson-card"]')).toHaveLength(0)
  })

  it('AC-1: a strategy page for the real Bull Call Spread row shows the server texts and every template part', async () => {
    templatesAnswer = REAL
    const w = await open('/learn/strategy-education')
    const bcs = REAL.templates.find((t) => t.id === 'bull_call_spread')
    const idx = w.findAll('[data-testid="template-name"]').map((e) => e.text()).indexOf(bcs.name)
    await w.findAll('[data-testid="card-open"]')[idx].trigger('click')
    expect(w.get('[data-testid="detail-title"]').text()).toBe(bcs.name)
    expect(w.get('[data-testid="detail-description"]').text()).toBe(bcs.description)
    for (const [key] of STRATEGY_PARTS) expect(w.find(`[data-testid="part-${key}"]`).exists(), key).toBe(true)
    for (const key of ['what', 'when', 'maxProfit', 'maxLoss', 'breakevens', 'risks']) {
      expect(w.get(`[data-testid="part-text-${key}"]`).text()).toBe(STRATEGY_TEXT.bull_call_spread[key])
    }
  })

  it('AC-1: every real server template has text, a known shape, and the page shows Sample on its payoff', async () => {
    templatesAnswer = REAL
    const w = await open('/learn/strategy-education')
    expect(Object.keys(STRATEGY_TEXT).sort()).toEqual(REAL.templates.map((t) => t.id).sort())
    const count = w.findAll('[data-testid="card-open"]').length
    expect(count).toBe(REAL.templates.length)
    for (let i = 0; i < count; i += 1) {
      const name = w.findAll('[data-testid="template-name"]')[i].text()
      const t = REAL.templates.find((x) => x.name === name)
      expect(SHAPES[STRATEGY_TEXT[t.id].shape], t.id).toBeTruthy()
      await w.findAll('[data-testid="card-open"]')[i].trigger('click')
      expect(w.get('[data-testid="sample-label"]').text(), t.id).toBe('Sample')
      expect(w.get('[data-testid="shape-svg"]').attributes('aria-label'), t.id).toContain('Sample')
      await w.get('[data-testid="detail-back"]').trigger('click')
    }
  })

  it('AC-1: a template with no text shows only the server description, no placeholder part', async () => {
    templatesAnswer = { templates: [tpl('t_new', 'New One', 'Server words only.', 'Beginner', ['bullish'])] }
    const w = await open('/learn/strategy-education')
    await w.get('[data-testid="card-open"]').trigger('click')
    expect(w.get('[data-testid="detail-description"]').text()).toBe('Server words only.')
    expect(w.findAll('[data-testid^="part-"]')).toHaveLength(0)
    expect(w.find('[data-testid="sample-label"]').exists()).toBe(false)
  })

  it('ADR-008: no strategy part carries a figure; formulas are words and the numbers come from the outcome table', () => {
    for (const t of Object.values(STRATEGY_TEXT)) {
      for (const [key] of STRATEGY_PARTS.filter(([k]) => k !== 'shape')) expect(t[key]).not.toMatch(/\d|₹|Rs\.?\s/)
    }
  })

  it('ADR-003: no content line reads as advice (normalised, stem-aware, every Learn text)', () => {
    const banned = [/\byou\s+(should|must|ought)\b/, /\bshould\b/, /\bbest\b/, /guarant/, /\bwinning\b/, /\bwinner/,
      /recommend/, /risk[\s-]*free/, /sure[\s-]*shot/, /\bassured\b/, /use it when you/, /\bwill (make|earn|profit)\b/]
    expect(contentText.length).toBeGreaterThan(100)
    for (const raw of contentText) {
      const line = raw.normalize('NFKC').toLowerCase().replace(/[‐-―]/g, '-').replace(/\s+/g, ' ')
      for (const re of banned) expect(line, `${re}: ${raw}`).not.toMatch(re)
    }
  })

  it('W-159 (REQ-085 AC-7): the "How this trade works" bullets are in the scanned text, name only known slots and typed numbers nowhere', () => {
    expect(Object.keys(HOW_IT_WORKS).length).toBeGreaterThan(0)
    const slots = new Set(['buyCE', 'sellCE', 'buyPE', 'sellPE', 'expiry', 'underlying'])
    for (const [id, bullets] of Object.entries(HOW_IT_WORKS)) {
      expect(REAL.templates.map((t) => t.id), id).toContain(id) // a real server template id
      for (const b of bullets) {
        expect(contentText, b).toContain(b) // so the advice scan above covers it
        expect(b, b).not.toMatch(/\d/) // every number comes from the reply's strings
        for (const m of b.matchAll(/\{(\w+)\}/g)) expect(slots.has(m[1]), `${id}: ${m[1]}`).toBe(true)
      }
    }
  })

  it('ADR-003: the wording check catches each banned shape (it can fail)', () => {
    const probe = (s) => /\byou\s+(should|must|ought)\b|\bbest\b|guarant|\bwinning\b|recommend/.test(s.toLowerCase().replace(/\s+/g, ' '))
    for (const bad of ['You  should buy', 'The best strike', 'Guaranteed profit', 'A winning setup', 'Recommended trade']) {
      expect(probe(bad), bad).toBe(true)
    }
  })

  it('REQ-011: the module is marked draft-for-owner-review', () => {
    const head = SOURCE.split(/\r?\n/)[0]
    expect(head).toBe('// status: draft-for-owner-review')
  })

  it('390 px: segmented control of three equal columns, one-column list, no fixed or nowrap widths', async () => {
    templatesAnswer = REAL
    for (const path of ['/learn/strategy-education', '/learn/options-concepts']) {
      const w = await open(path)
      const html = w.html()
      expect(w.get('[data-testid="learn-tabs"]').classes()).toContain('grid-cols-3')
      expect(html).toContain('grid-cols-1')
      expect(html).not.toMatch(/(?:^|[\s"])(?:min-w-|w-\[|whitespace-nowrap|overflow-x-)/)
      await w.get('[data-testid="card-open"]').trigger('click')
      expect(w.html()).not.toMatch(/whitespace-nowrap|min-w-|w-\[/)
    }
  })
})

describe('Alerts', () => {
  it('AC-1: Active and History show the empty line; Notification settings the channels line; nothing else', async () => {
    const noAlerts = 'No alerts yet. Alerts start when strategy monitoring rules are added.'
    for (const [path, line] of [['/alerts/active', noAlerts], ['/alerts/history', noAlerts],
      ['/alerts/notification-settings', 'No notification channels are set up yet.']]) {
      const w = await open(path)
      expect(w.get('[data-testid="alerts-empty"]').text()).toBe(line)
      expect(w.findAll('button')).toHaveLength(0)
      expect(w.findAll('li, tr')).toHaveLength(0)
    }
  })
})

describe('Market context', () => {
  it('AC-1: LIVE answer shows both values and the live status line', async () => {
    indicesAnswer = live()
    const w = await open('/market/market-context')
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are live.')
    expect(w.get('[data-testid="strip-NIFTY"]').text()).toContain('24500.50')
    expect(w.get('[data-testid="strip-SENSEX"]').text()).toContain('80100.25')
  })

  it('AC-1: a not-live answer shows no number and says not live', async () => {
    const w = await open('/market/market-context')
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are not live.')
    expect(w.text()).not.toMatch(/\d{4,}/)
    expect(w.text()).not.toMatch(/PCR|VIX|OI/)
  })

  it('AC-1: after a socket drop the last live number is not kept (finding last-live-answer-kept-after-drop)', async () => {
    indicesAnswer = notConnected()
    const w = await open('/market/market-context')
    FakeSocket.all[0].serverPush(live())
    await flushPromises()
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are live.')
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are not live.')
    expect(w.text()).not.toContain('24500.50')
  })
})
