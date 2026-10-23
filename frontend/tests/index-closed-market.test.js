// REQ-114 AC-7 / ADR-015 / ADR-177 (chunk 1 Tier A review round 2, class live-wording-on-a-closed-market): every screen
// that reads the index answer - Market Context (strip with its status line), the Home strip, the Underlying/index view -
// shows the ONE market-closed banner and NO live wording ("Index values are live.", a live "as of" time) when the answer
// says market_closed, whether it arrives by the first-paint read or a socket push, and even if a (forged) answer says
// LIVE with market_closed true. The last value IS shown, as such (REQ-072 AC-2): the number, the stale word and, on the
// index view, "Last updated <time>"; the "unavailable" label is not. An open-market LIVE answer is unchanged. Expected texts are hand-computed:
// 04:31:00 UTC + 5:30 = 10:01:00 IST in the istTime format; the banner wording comes from its one home (sharedStateText).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => (apiAnswer ? Promise.resolve({ data: apiAnswer }) : Promise.reject(new Error('down'))) } }
})
import IndexViewPage from '@/pages/IndexViewPage.vue'
import MarketContextPage from '@/pages/MarketContextPage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import { isLiveIndexAnswer } from '@/composables/useIndexLive'
import { marketClosedText } from '@/lib/sharedStateText'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; FakeSocket.all.push(this) }
  send() {}
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
}

const LAST = '2026-10-24T04:31:00+00:00' // Saturday 10:01:00 IST
const BANNER = marketClosedText('24 Oct 2026, 10:01:00 IST')
const row = (u, value, health) => ({ underlying: u, instrument_id: u === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at: LAST, health })
const answerOf = (state, closed, health) => ({
  state, market_closed: closed, last_price_at: LAST, answered_at: '2026-10-24T04:35:00+00:00',
  indices: [row('NIFTY', '25100.55', health), row('SENSEX', '81000.10', health)] })
const CLOSED = answerOf('NOT_CONNECTED', true, 'stale') // what the server sends on a closed market (index_push.py)
const FORGED = answerOf('LIVE', true, 'available') // a LIVE answer on a closed market (second layer)
const OPEN = answerOf('LIVE', false, 'available')
const LIVE_WORDS = ['Index values are live.', 'as of ']
const UNAVAILABLE_LABEL = 'Index values unavailable.'

const SCREENS = {
  'market context': { component: MarketContextPage, path: '/market/market-context' },
  'home strip': { component: IndexStrip, path: '/' },
  'index view': { component: IndexViewPage, path: '/market/underlying-index-view' },
}

async function mountScreen({ component, path }) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path, component }, { path: '/:p(.*)*', component: { template: '<div />' } }] })
  router.push(path)
  await router.isReady()
  const w = mount(component, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  apiAnswer = null
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('AC-7: index screens on a closed market', () => {
  for (const [name, screen] of Object.entries(SCREENS)) {
    for (const [how, answer] of [['server closed answer', CLOSED], ['forged LIVE + closed', FORGED]]) {
      it(`AC-7: ${name}, ${how} by first paint: the banner, no live wording, no number`, async () => {
        apiAnswer = answer
        const w = await mountScreen(screen)
        expect(w.get('[data-testid="market-closed-text"]').text()).toBe(BANNER)
        for (const word of LIVE_WORDS) expect(w.text()).not.toContain(word)
        expect(w.text()).toContain('25100.55') // the last value, shown as such
        expect(w.text()).not.toContain(UNAVAILABLE_LABEL)
      })
      it(`AC-7: ${name}, ${how} by socket push: the banner, no live wording, no number`, async () => {
        apiAnswer = OPEN // the first paint said open and live; the push says closed
        const w = await mountScreen(screen)
        FakeSocket.all[0].serverOpen()
        FakeSocket.all[0].serverPush(answer)
        await flushPromises()
        expect(w.findAll('[data-testid="market-closed-text"]').map((b) => b.text())).toEqual([BANNER])
        for (const word of LIVE_WORDS) expect(w.text()).not.toContain(word)
        expect(w.text()).toContain('25100.55')
        expect(w.text()).not.toContain(UNAVAILABLE_LABEL)
      })
    }
    it(`AC-7: ${name}, closed answer: each index's last value with the stale word`, async () => {
      apiAnswer = CLOSED
      const w = await mountScreen(screen)
      const panel = name === 'index view' ? 'index-panel' : 'strip'
      const health = name === 'index view' ? 'index-health' : 'strip-health'
      const value = name === 'index view' ? 'index-value' : 'strip-value'
      for (const [u, v] of [['NIFTY', '25100.55'], ['SENSEX', '81000.10']]) {
        expect(w.get(`[data-testid="${panel}-${u}"] [data-testid="${value}"]`).text()).toBe(v)
        expect(w.get(`[data-testid="${panel}-${u}"] [data-testid="${health}"]`).text()).toBe('stale')
      }
    })
    it(`AC-7 negative case: ${name}, open LIVE answer: no banner, the value shown, no stale word`, async () => {
      apiAnswer = OPEN
      const w = await mountScreen(screen)
      expect(w.find('[data-testid="market-closed-banner"]').exists()).toBe(false)
      expect(w.text()).toContain('25100.55')
      expect(w.text()).not.toContain('stale')
    })
  }

  it('AC-7: Market Context status line says not live on a closed market, live on an open one', async () => {
    apiAnswer = CLOSED
    let w = await mountScreen(SCREENS['market context'])
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are not live.')
    apiAnswer = OPEN
    w = await mountScreen(SCREENS['market context'])
    expect(w.get('[data-testid="market-status"]').text()).toBe('Index values are live.')
  })

  it('AC-7: index view times read "Last updated" when closed, "as of" when open', async () => {
    apiAnswer = CLOSED
    let w = await mountScreen(SCREENS['index view'])
    expect(w.get('[data-testid="index-panel-NIFTY"] [data-testid="index-at"]').text()).toBe('Last updated 24 Oct 2026, 10:01:00 IST')
    apiAnswer = OPEN
    w = await mountScreen(SCREENS['index view'])
    expect(w.get('[data-testid="index-panel-NIFTY"] [data-testid="index-at"]').text()).toBe('as of 24 Oct 2026, 10:01:00 IST')
  })

  it('AC-7: the one live rule: LIVE and not closed only', () => {
    expect(isLiveIndexAnswer(OPEN)).toBe(true)
    expect(isLiveIndexAnswer(FORGED)).toBe(false)
    expect(isLiveIndexAnswer(CLOSED)).toBe(false)
    expect(isLiveIndexAnswer(null)).toBe(false)
  })
})
