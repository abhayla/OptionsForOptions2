// W-089 (REQ-015 AC-4): the Broker & Market Data page text for every state the server can send, and the fail-closed
// cases: an unknown state or fix code is never shown as Connected, and a failed read shows the unavailable state.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let answer = () => Promise.reject(new Error('no answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => { calls.push(['get', url]); return answer(url) },
      post: (url) => { calls.push(['post', url]); return Promise.resolve({ data: { disconnected: true } }) },
    },
  }
})
import BrokerSettingsPage from '@/pages/BrokerSettingsPage.vue'

const ok = { state: 'connected', fix: null }
const base = { account_connection: ok, live_market_data: ok, position_sync: ok, order_execution: ok, last_successful_sync: null, historical_data: 'not_available' }
const t = (w, id) => w.get(`[data-testid="${id}"]`).text()
async function open(data) {
  answer = () => (data instanceof Error ? Promise.reject(data) : Promise.resolve({ data }))
  const w = mount(BrokerSettingsPage, { global: { stubs: { ErrorMessage: true } } })
  await flushPromises()
  return w
}

describe('/settings/broker-market-data', () => {
  beforeEach(() => { calls.length = 0 })

  it('connected: four Connected rows and no fix text', async () => {
    const w = await open({ ...base, last_successful_sync: '2026-10-17T09:05:00Z' })
    expect(calls[0]).toEqual(['get', '/broker/status'])
    for (const k of ['account_connection', 'live_market_data', 'position_sync', 'order_execution']) {
      expect(t(w, `status-${k}`)).toBe('Connected')
      expect(w.find(`[data-testid="fix-${k}"]`).exists()).toBe(false)
    }
    expect(t(w, 'last-sync-time')).toContain('IST')
  })

  it('partial: names the fix for each code', async () => {
    const w = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_session_ended' }, position_sync: { state: 'partial', fix: 'no_read_yet' } })
    expect(t(w, 'status-live_market_data')).toBe('Partially connected')
    expect(t(w, 'fix-live_market_data')).toContain('Zerodha ended the live feed')
    expect(t(w, 'fix-position_sync')).toContain('No position read from Zerodha has succeeded')
    expect(t(w, 'last-sync-none')).toContain('no successful read')
  })

  it('partial: the waiting and reconnecting feed fixes read in plain words (REQ-015 AC-4)', async () => {
    const waiting = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_waiting' } })
    expect(t(waiting, 'status-live_market_data')).toBe('Partially connected')
    expect(t(waiting, 'fix-live_market_data')).toContain('no prices have arrived yet')
    const idle = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_idle' } })
    expect(t(idle, 'fix-live_market_data')).toContain('Live prices start when you open a strategy or option chain screen.')
    expect(t(idle, 'fix-live_market_data')).not.toContain('Reconnect')
    const capped = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_capped' } })
    expect(t(capped, 'fix-live_market_data')).toContain("Live prices are not available: Zerodha's connection limit for this app is reached.")
    const back = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_reconnecting' } })
    expect(t(back, 'fix-live_market_data')).toContain('reconnecting')
  })

  it('disconnected: guide text and a Connect button, no Disconnect', async () => {
    const d = { state: 'disconnected', fix: 'session_expired' }
    const w = await open({ ...base, account_connection: d, live_market_data: d, position_sync: d, order_execution: d })
    expect(t(w, 'status-account_connection')).toBe('Disconnected')
    expect(t(w, 'fix-order_execution')).toContain('expired')
    expect(t(w, 'broker-reconnect')).toBe('Connect Zerodha')
    expect(w.find('[data-testid="broker-disconnect"]').exists()).toBe(false)
  })

  it('an unknown state is shown as Disconnected, never Connected', async () => {
    const w = await open({ ...base, account_connection: { state: 'weird', fix: 'nope' } })
    expect(t(w, 'status-account_connection')).toBe('Disconnected')
    expect(t(w, 'fix-account_connection')).toContain('Use Reconnect')
  })

  it('a failed read shows the unavailable state and no rows', async () => {
    const w = await open(new Error('down'))
    expect(w.find('[data-testid="broker-unavailable"]').exists()).toBe(true)
    expect(w.find('[data-testid="broker-rows"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Connected')
  })

  it('states that history is not available in this version', async () => {
    const w = await open(base)
    expect(t(w, 'history-statement')).toBe('Historical market data: not currently available in this version.')
  })

  it('Disconnect posts only after the confirmation and then reloads the status', async () => {
    const w = await open(base)
    await w.get('[data-testid="broker-disconnect"]').trigger('click')
    expect(calls.filter((c) => c[0] === 'post')).toEqual([])
    await w.get('[data-testid="disconnect-yes"]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'post')).toEqual([['post', '/broker/disconnect']])
    // the status is read twice (load + reload); the account block (REQ-015 AC-13) is read after each status read
    expect(calls.filter((c) => c[0] === 'get' && c[1] === '/broker/status').length).toBe(2)
  })
})
