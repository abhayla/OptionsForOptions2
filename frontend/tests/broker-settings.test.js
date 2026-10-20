// W-089 + GC-6 ZERODHA-CONN (REQ-015 AC-4, ADR-138 (5)): the Broker & Market Data page shows one state, Connected or
// Reconnect, plus the last sync time. Every answer state of GET /broker/status is covered; anything that is not a live
// session (expired, never connected, partial, unknown word, empty, unreadable) is never shown as Connected.
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

  it('live session: Connected plus the last sync time, no Reconnect help, no four-status block', async () => {
    const w = await open({ ...base, last_successful_sync: '2026-10-17T09:05:00Z' })
    expect(calls[0]).toEqual(['get', '/broker/status'])
    expect(t(w, 'connection-state')).toBe('Connected')
    expect(t(w, 'last-sync-time')).toContain('IST')
    expect(w.find('[data-testid="reconnect-help"]').exists()).toBe(false)
    expect(w.find('[data-testid="broker-rows"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Partially connected')
    expect(w.text()).not.toContain('Order-execution readiness')
    expect(t(w, 'broker-reconnect')).toBe('Reconnect Zerodha')
  })

  it('live session with no sync yet: still Connected, says no read is recorded', async () => {
    const w = await open(base)
    expect(t(w, 'connection-state')).toBe('Connected')
    expect(t(w, 'last-sync-none')).toContain('no successful read')
  })

  it('partial feature statuses do not change the single state', async () => {
    const w = await open({ ...base, live_market_data: { state: 'partial', fix: 'live_feed_session_ended' }, position_sync: { state: 'partial', fix: 'no_read_yet' } })
    expect(t(w, 'connection-state')).toBe('Connected')
    expect(w.text()).not.toContain('Partially connected')
  })

  it.each([
    ['expired', { state: 'disconnected', fix: 'session_expired' }],
    ['never connected', { state: 'disconnected', fix: 'connect_zerodha' }],
    ['partial account', { state: 'partial', fix: null }],
    ['unknown word', { state: 'weird', fix: 'nope' }],
    ['empty object', {}],
    ['missing field', undefined],
  ])('%s: Reconnect, never Connected, link to the login route, no Disconnect', async (_name, acct) => {
    const w = await open({ ...base, account_connection: acct, last_successful_sync: null })
    expect(t(w, 'connection-state')).toBe('Reconnect')
    expect(t(w, 'reconnect-help')).toContain('We never ask for your password, PIN or OTP')
    expect(w.get('[data-testid="broker-reconnect"]').attributes('href')).toBe('/api/broker/zerodha/login')
    expect(w.find('[data-testid="broker-disconnect"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Connected')
  })

  it('an empty reply (null body) shows Reconnect', async () => {
    const w = await open(null)
    expect(t(w, 'connection-state')).toBe('Reconnect')
  })

  it('a failed read shows the unavailable state and no connection state', async () => {
    const w = await open(new Error('down'))
    expect(w.find('[data-testid="broker-unavailable"]').exists()).toBe(true)
    expect(w.find('[data-testid="connection-state"]').exists()).toBe(false)
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
    expect(calls.filter((c) => c[0] === 'get').length).toBe(2)
  })
})
