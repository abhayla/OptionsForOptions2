// W-117 (REQ-011 AC-1; REQ-009 AC-4/AC-6; ADR-114, ADR-003): Learn, Alerts and Market context with a fake route reply and a
// fake index socket. Texts shown must equal the fake reply's texts as given; the empty lines are the brief's quoted wording.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() { this.readyState = 3 }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
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

  it('AC-1: Options concepts and Platform guidance each show the one line and no lesson', async () => {
    for (const path of ['/learn/options-concepts', '/learn/platform-guidance']) {
      const w = await open(path)
      expect(w.get('[data-testid="learn-empty"]').text()).toBe('Nothing published here yet.')
      expect(w.findAll('[data-testid="template-card"]')).toHaveLength(0)
    }
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
    expect(w.findAll('button')).toHaveLength(0)
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
