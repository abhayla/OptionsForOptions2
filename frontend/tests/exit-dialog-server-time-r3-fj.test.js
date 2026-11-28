// Lane FJ (R3) item 3 (fd2: server_time on /market/exit-state, /paper/strategies/{id}/exit-risk, /armed-exits): the Exit dialog tells how old its price is
// against the SERVER's clock, not the browser's. Real case: a laptop clock 5 minutes slow made a 5-minute-old price read "fresh". Spec basis: REQ-109 AC-5, ADR-330 (56), (60).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let answers = {}
vi.mock('@/services/api', () => ({ default: { get: (u) => (answers[u] ? Promise.resolve({ data: answers[u] }) : Promise.reject(new Error('no ' + u))), post: () => Promise.resolve({ data: {} }) } }))
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const BROWSER_NOW = '2026-11-27T10:41:25+05:30'
const AT = '2026-11-27T10:41:20+05:30'
const row = { key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 25500 PE', lots: 1, lot_size: 65, price: '42.55', price_at: AT, contract_id: 1 }
const mounted = []
const line = (w) => w.find('[data-testid="paper-price-age"]').text()
async function open(extra = {}) {
  const w = mount(PaperConfirmDialog, { props: { open: true, orders: [row], strategyId: 5, ...extra }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(Date.parse(BROWSER_NOW))
  answers = { '/market/exit-state': { closed: false, sentence: null, next_open_at: null }, '/paper/strategies/5/exit-risk': { state: 'no' }, '/paper/strategies/5/armed-exits': { lines: [] } }
})
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount() })

describe('price age against server_time', () => {
  it('no server_time anywhere: the browser clock, as before', async () => {
    expect(line(await open())).toBe('Price as of 10:41:20 IST, 5 seconds ago.')
  })
  it('exit-state server_time 5 minutes ahead of the browser: the age is told against it', async () => {
    answers['/market/exit-state'] = { closed: false, sentence: null, next_open_at: null, server_time: '2026-11-27T10:46:20+05:30' }
    expect(line(await open())).toBe('Price as of 10:41:20 IST, 5 minutes ago.')
  })
  it('only the exit-risk reply carries it: used', async () => {
    answers['/paper/strategies/5/exit-risk'] = { state: 'no', server_time: '2026-11-27T10:46:20+05:30' }
    expect(line(await open())).toBe('Price as of 10:41:20 IST, 5 minutes ago.')
  })
  it('only the armed-exits reply carries it: used', async () => {
    answers['/paper/strategies/5/armed-exits'] = { lines: [], server_time: '2026-11-27T10:46:20+05:30' }
    expect(line(await open())).toBe('Price as of 10:41:20 IST, 5 minutes ago.')
  })
  it('a server_time that is not a time is ignored: the browser clock', async () => {
    answers['/market/exit-state'] = { closed: false, sentence: null, next_open_at: null, server_time: 'garbage' }
    expect(line(await open())).toBe('Price as of 10:41:20 IST, 5 seconds ago.')
  })
  it('the server clock keeps running between answers (the browser clock only measures the gap)', async () => {
    answers['/market/exit-state'] = { closed: false, sentence: null, next_open_at: null, server_time: '2026-11-27T10:46:20+05:30' }
    const w = await open()
    vi.setSystemTime(Date.parse(BROWSER_NOW) + 15000)
    await vi.advanceTimersByTimeAsync(0)
    w.vm.$.setupState.openedAtMs = Date.now() // the 15 s re-ask tick (it sets this and asks again)
    await flushPromises()
    expect(line(w)).toBe('Price as of 10:41:20 IST, 5 minutes ago.')
  })
})
