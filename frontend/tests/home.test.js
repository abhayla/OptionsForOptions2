// W-115 (REQ-008 AC-2/AC-4/AC-5; ADR-114, ADR-003): the Home overview with a fake GET /strategies and a fake index socket.
// Expected texts come from the fixtures written here and from the spec's wording, never from the page's output.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let strategiesAnswer = null // a list, or an Error to reject with
let indicesAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => {
    if (url === '/strategies') {
      return strategiesAnswer instanceof Error ? Promise.reject(strategiesAnswer)
        : Promise.resolve({ data: { strategies: strategiesAnswer } })
    }
    return Promise.resolve({ data: indicesAnswer })
  } } }
})
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import { routes } from '@/router/routes'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() { this.readyState = 3; this.closed = true }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const row = (underlying, value, at, health = 'available') => ({
  underlying, instrument_id: underlying === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at, health })
const live = (nifty, sensex) => ({ state: 'LIVE', indices: [nifty, sensex], answered_at: '2026-10-19T03:50:01+00:00' })
const notConnected = (at) => ({ state: 'NOT_CONNECTED', answered_at: '2026-10-19T03:50:09+00:00',
  indices: [row('NIFTY', null, at, null), row('SENSEX', null, at, null)] })
const T1 = '2026-10-19T09:20:00+05:30'
const T2 = '2026-10-19T09:20:01+05:30'
const draft = (id, underlying, updated_at) => ({ id, underlying, status: 'draft', revision: 1, created_at: updated_at, updated_at })

async function mountHome() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/home/overview', component: HomeOverviewPage },
    { path: '/:p(.*)*', component: { template: '<div />' } }] })
  router.push('/home/overview')
  await router.isReady()
  const wrapper = mount(HomeOverviewPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  FakeSocket.all = []
  indicesAnswer = notConnected(null)
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

const hrefs = (w, id) => w.findAll(`[data-testid="${id}"] a`).map((a) => a.attributes('href'))

describe('Home states from GET /strategies', () => {
  it('AC-2: no strategies -> new: Welcome, the line, Create / Explore / Learn in that order, the know-my-strategy link', async () => {
    strategiesAnswer = []
    const w = await mountHome()
    expect(w.get('[data-testid="home"]').attributes('data-state')).toBe('new')
    expect(w.text()).toContain('Welcome')
    expect(w.text()).toContain('Plan your trade. Follow your strategy. Then execute.')
    const actions = w.findAll('[data-testid="home-actions"] a')
    expect(actions.map((a) => a.text())).toEqual(['Create Strategy', 'Explore Option Chain', 'Learn'])
    expect(actions.map((a) => a.attributes('href'))).toEqual(['/strategies/create-strategy', '/market/option-chain', '/learn/strategy-education'])
    expect(w.get('[data-testid="action-know"]').text()).toBe('I already know my strategy')
    expect(w.get('[data-testid="action-know"]').attributes('href')).toBe('/strategy/builder')
    expect(w.find('[data-testid="recent-strategies"]').exists()).toBe(false)
  })

  it('AC-2: strategies saved -> has-strategies: My Strategies first, then Create; newest first, at most 3 rows', async () => {
    strategiesAnswer = [
      draft(1, 'NIFTY', '2026-10-15T10:00:00+05:30'),
      draft(2, 'SENSEX', '2026-10-18T10:00:00+05:30'),
      draft(3, 'NIFTY', '2026-10-17T10:00:00+05:30'),
      draft(4, 'NIFTY', '2026-10-16T10:00:00+05:30'),
    ]
    const w = await mountHome()
    expect(w.get('[data-testid="home"]').attributes('data-state')).toBe('has-strategies')
    const actions = w.findAll('[data-testid="home-actions"] a')
    expect(actions.map((a) => a.text())).toEqual(['My Strategies', 'Create Strategy'])
    expect(actions[0].attributes('href')).toBe('/strategies/my-strategies')
    const rows = w.findAll('[data-testid="recent-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('SENSEX, draft, last saved 18 Oct 2026, 10:00:00 IST')
    expect(rows[1].text()).toContain('NIFTY, draft, last saved 17 Oct 2026, 10:00:00 IST')
    expect(rows[2].text()).toContain('NIFTY, draft, last saved 16 Oct 2026, 10:00:00 IST')
    expect(w.find('[data-testid="recent-open-1"]').exists()).toBe(false) // the oldest is not shown
    expect(hrefs(w, 'recent-strategies')).toEqual(['/strategy/builder', '/strategy/builder', '/strategy/builder'])
    expect(w.text()).not.toContain('Welcome')
  })

  it('AC-2: a failed GET /strategies -> error state with the server message, no guessed state, strip still there', async () => {
    const e = new Error('x')
    e.parts = { what_happened: 'Saved strategies could not be read.', impact: 'The list is missing.',
      what_is_blocked: 'Nothing else.', next_action: 'Try again shortly.' }
    strategiesAnswer = e
    const w = await mountHome()
    expect(w.get('[data-testid="home"]').attributes('data-state')).toBe('error')
    expect(w.get('[data-testid="home-error-what"]').text()).toBe('Saved strategies could not be read.')
    expect(w.find('[data-testid="home-new"]').exists()).toBe(false)
    expect(w.find('[data-testid="home-has-strategies"]').exists()).toBe(false)
    expect(w.find('[data-testid="index-strip"]').exists()).toBe(true)
    expect(FakeSocket.all).toHaveLength(1)
  })
})

describe('the live index strip', () => {
  it('AC-4: two pushes from the fake socket show NIFTY 50 and SENSEX values and times; unmount closes the socket', async () => {
    strategiesAnswer = []
    const w = await mountHome()
    const ws = FakeSocket.all[0]
    ws.serverPush(live(row('NIFTY', '25145.50', T1), row('SENSEX', '82010.25', T1)))
    await flushPromises()
    const nifty = () => w.get('[data-testid="strip-NIFTY"]')
    const sensex = () => w.get('[data-testid="strip-SENSEX"]')
    expect(nifty().text()).toContain('NIFTY 50')
    expect(nifty().get('[data-testid="strip-value"]').text()).toBe('25145.50')
    expect(nifty().get('[data-testid="strip-at"]').text()).toBe('19 Oct 2026, 09:20:00 IST')
    ws.serverPush(live(row('NIFTY', '25146.00', T2), row('SENSEX', '82012.75', T2)))
    await flushPromises()
    expect(nifty().get('[data-testid="strip-value"]').text()).toBe('25146.00')
    expect(sensex().get('[data-testid="strip-value"]').text()).toBe('82012.75')
    expect(sensex().get('[data-testid="strip-at"]').text()).toBe('19 Oct 2026, 09:20:01 IST')
    expect(w.find('[data-testid="strip-health"]').exists()).toBe(false)
    expect(w.find('[data-testid="strip-state"]').exists()).toBe(false)
    w.unmount()
    expect(ws.closed).toBe(true)
  })

  it('AC-4: a stale health shows its word; NOT_CONNECTED and a dropped socket show the not-live state and no number', async () => {
    strategiesAnswer = []
    indicesAnswer = live(row('NIFTY', '25145.50', T1, 'stale'), row('SENSEX', '82010.25', T1))
    const w = await mountHome()
    expect(w.get('[data-testid="strip-NIFTY"] [data-testid="strip-health"]').text()).toBe('stale')
    indicesAnswer = notConnected(T1) // the REST fallback after the drop
    FakeSocket.all[0].serverClose()
    await flushPromises()
    expect(w.get('[data-testid="strip-state"]').text()).toBe('Index values unavailable.')
    expect(w.get('[data-testid="strip-NIFTY"] [data-testid="strip-value"]').text()).toBe('Not available')
    expect(w.text()).not.toContain('25145.50')
  })
})

describe('Zerodha only in context', () => {
  it('AC-5: no link to the broker login, no Connect button, in any state; a quiet text line only', async () => {
    for (const list of [[], [draft(1, 'NIFTY', '2026-10-15T10:00:00+05:30')]]) {
      strategiesAnswer = list
      const w = await mountHome()
      expect(w.html()).not.toContain('/broker/zerodha/login')
      expect(w.findAll('button')).toHaveLength(0)
      expect(w.findAll('a').some((a) => /connect/i.test(a.text()))).toBe(false)
      const line = w.get('[data-testid="zerodha-line"]')
      expect(line.element.tagName).toBe('P')
      expect(line.text()).toBe('Already trade with Zerodha? Connect when ready')
      expect(line.find('a, button').exists()).toBe(false)
      expect(w.text()).not.toMatch(/you should|\bbest\b/i)
    }
  })

  it('AC-2: the router maps /home/overview to this page, not the placeholder', async () => {
    const r = routes.find((x) => x.path === '/home/overview')
    expect(String(r.component)).toContain('HomeOverviewPage')
  })
})
