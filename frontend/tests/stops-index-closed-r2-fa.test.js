// Lane FA r2, I-29 (AF-08 class; REQ-049 AC-4, ADR-330 (56), (58)): with the market closed an index exit rule (a level on NIFTY or
// SENSEX) saves; the panel names the last close as the reference in ONE line and never says "Index values unavailable." for a
// closed market. Stop rules (leg stops) are unchanged: display and save-enable only. Expected texts are written here.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { echoSeq } from './helpers/echoSeq'

const posts = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const trig = { id: 9, kind: 'conditional_exit', direction: 'above', level_text: '26,000.00', state: 'armed' }
  return { ...actual, default: {
    get: (url) => (url.includes('triggers') ? Promise.resolve({ data: { triggers: [] } }) : Promise.reject({ message: 'no answer' })),
    post: (url, body) => { posts.push({ url, body }); return Promise.resolve({ data: { triggers: [trig] } }) },
  } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; FakeSocket.all.push(this) }
  send() {}
  close() {}
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
const CLOSE = '2026-11-27T10:00:00Z' // 15:30:00 IST
const REF = 'The market is closed. A level you save is checked from the next market open; the last close is shown for reference.'
const answer = (state, value, over = {}) => ({ state, market_closed: true, last_price_at: CLOSE, answered_at: CLOSE,
  indices: ['NIFTY', 'SENSEX'].map((u) => ({ underlying: u, instrument_id: u, value, at: value ? CLOSE : null, health: value ? 'available' : null })), ...over })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function open(u, ans, legs = []) {
  const w = mount(PaperStops, { props: { strategyId: 48, underlying: u, legs } })
  await flushPromises()
  FakeSocket.all[0].serverPush(ans)
  await flushPromises()
  return w
}
beforeEach(() => { FakeSocket.all = []; posts.length = 0; vi.stubGlobal('WebSocket', FakeSocket) })
afterEach(() => { vi.unstubAllGlobals() })

describe.each([['NIFTY'], ['SENSEX']])('%s exit rule with the market closed', (u) => {
  it.each([
    ['LIVE answer, closed, with a value', answer('LIVE', '25,607.20')],
    ['NOT_CONNECTED answer, closed, row carries the last value (server fallback)', answer('NOT_CONNECTED', '25,607.20')],
    ['NOT_CONNECTED answer, closed, no value at all', answer('NOT_CONNECTED', null)],
  ])('%s: Save is enabled and posts the level; the reference line is shown', async (_n, ans) => {
    const w = await open(u, ans)
    expect(t(w, 'stops-index').text()).not.toBe('Index values unavailable.')
    expect(t(w, 'stops-reference').text()).toBe(REF)
    await t(w, 'ce-above').setValue('26000')
    expect(t(w, 'ce-save').attributes('disabled')).toBeUndefined()
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(posts).toEqual([{ url: '/paper/strategies/48/triggers', body: { kind: 'conditional_exit', above: '26000' } }])
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 26000')
  })
  it('a closed market with no value says the close is not available, with no digits', async () => {
    const w = await open(u, answer('NOT_CONNECTED', null))
    expect(t(w, 'stops-index').text()).toBe(`${u}: the last close is not available.`)
  })
})

describe('what stays as it was', () => {
  it('never answered (no socket answer): "Index values unavailable." and NO reference line; Save still follows the level only', async () => {
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    expect(t(w, 'stops-index').text()).toBe('Index values unavailable.')
    expect(t(w, 'stops-reference').exists()).toBe(false)
    expect(t(w, 'ce-save').attributes('disabled')).toBeDefined() // no level typed
  })
  it('market open and live: no reference line', async () => {
    const w = await open('NIFTY', { ...answer('LIVE', '25,607.20'), market_closed: false })
    expect(t(w, 'stops-reference').exists()).toBe(false)
    expect(t(w, 'stops-index').text()).toBe('NIFTY now 25,607.20 as of 15:30:00')
  })
  it('an invalid level still disables Save after the close', async () => {
    const w = await open('NIFTY', answer('LIVE', '25,607.20'))
    await t(w, 'ce-above').setValue('26000.03')
    expect(t(w, 'ce-save').attributes('disabled')).toBeDefined()
  })
  it('a leg stop saves after the close and its body is unchanged', async () => {
    const w = await open('NIFTY', answer('LIVE', '25,607.20'), [{ index: 0, label: 'NIFTY 25500 PE', contractId: 501 }])
    await t(w, 'stop-level-0').setValue('30.05')
    expect(t(w, 'stop-save-0').attributes('disabled')).toBeUndefined()
    await t(w, 'stop-save-0').trigger('click')
    await flushPromises()
    expect(posts[0].body).toEqual({ kind: 'leg_stop', contract_id: 501, direction: 'above', level: '30.05' })
  })
})
