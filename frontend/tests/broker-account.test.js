// REQ-015 AC-13 (RD-013): the Settings account block - masked id, Zerodha's margin exactly as the API string with its
// read time, and the reason for every no-figure state (never 0, never computed). Expected texts are the API strings
// themselves and the reason table in src/lib/brokerAccount.js.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { accountView, maskedId, MARGIN_REASON, ACCOUNT_UNREADABLE } from '@/lib/brokerAccount'

const calls = []
let accountAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        calls.push(url)
        if (url === '/broker/account') return accountAnswer()
        return Promise.resolve({ data: { account_connection: { state: 'connected', fix: null }, live_market_data: { state: 'connected', fix: null }, position_sync: { state: 'connected', fix: null }, order_execution: { state: 'connected', fix: null }, last_successful_sync: null, historical_data: 'not_available' } })
      },
      post: () => Promise.resolve({ data: { disconnected: true } }),
    },
  }
})
import BrokerSettingsPage from '@/pages/BrokerSettingsPage.vue'

const ID = { start: 'AB', hidden: 2, end: '34' }
const READ_AT = '2026-10-23T04:00:00Z' // 09:30 IST
const none = (state) => ({ user_id: ID, margin: { state, available: null, read_at: null } })

describe('AC-13 accountView: every answer state', () => {
  it('AC-13: available -> the API string exactly (no rounding, no parsing) and its read time in IST', () => {
    const v = accountView({ user_id: ID, margin: { state: 'available', available: '12345.67', read_at: READ_AT } })
    expect(v.id).toBe('AB**34')
    expect(v.figure).toBe('12345.67')
    expect(v.readAt).toContain('9:30')
    expect(v.readAt).toContain('IST')
    expect(v.reason).toBeNull()
    expect(accountView({ user_id: ID, margin: { state: 'available', available: '0.10', read_at: READ_AT } }).figure).toBe('0.10')
  })

  for (const state of ['not_connected', 'not_offered', 'empty', 'busy', 'session_expired', 'read_failed']) {
    it(`AC-13: ${state} -> its reason, no figure`, () => {
      const v = accountView(none(state))
      expect(v.figure).toBeNull()
      expect(v.reason).toBe(MARGIN_REASON[state])
      expect(v.reason).not.toMatch(/\b0\b/)
    })
  }

  it('AC-13: an unknown state, a number figure, an empty string or no read time -> the read-failed reason', () => {
    for (const margin of [{ state: 'surprise', available: '1.00', read_at: READ_AT },
      { state: 'available', available: 12345.67, read_at: READ_AT },
      { state: 'available', available: '', read_at: READ_AT },
      { state: 'available', available: '1.00', read_at: null },
      { state: 'available', available: null, read_at: READ_AT }]) {
      const v = accountView({ user_id: ID, margin })
      expect(v.figure).toBeNull()
      expect(v.reason).toBe(MARGIN_REASON.read_failed)
    }
  })

  it('AC-13: a missing body or an array -> could not read, no id', () => {
    for (const body of [null, undefined, [], 'x']) {
      expect(accountView(body)).toEqual({ id: null, figure: null, readAt: null, reason: ACCOUNT_UNREADABLE })
    }
  })

  it('AC-13: the id is built only from the server parts; a short id is all hidden; junk is no id', () => {
    expect(maskedId({ start: null, hidden: 4, end: null })).toBe('****')
    expect(maskedId(null)).toBeNull()
    expect(maskedId({ start: 'AB', hidden: 0, end: '34' })).toBeNull()
    expect(maskedId({ start: 'AB', end: '34' })).toBeNull()
  })
})

describe('AC-13 the Settings page shows the block', () => {
  beforeEach(() => { calls.length = 0 })

  it('AC-13: shows the masked id and the margin string with its read time', async () => {
    accountAnswer = () => Promise.resolve({ data: { user_id: ID, margin: { state: 'available', available: '12345.67', read_at: READ_AT } } })
    const w = mount(BrokerSettingsPage)
    await flushPromises()
    expect(calls).toContain('/broker/account')
    expect(w.get('[data-testid="account-id"]').text()).toBe('AB**34')
    expect(w.get('[data-testid="account-margin-figure"]').text()).toBe('12345.67')
    expect(w.get('[data-testid="account-margin-read-at"]').text()).toContain('IST')
    expect(w.find('[data-testid="account-margin-reason"]').exists()).toBe(false)
  })

  it('AC-13: a failed account read shows the reason and never a figure', async () => {
    accountAnswer = () => Promise.reject(new Error('network'))
    const w = mount(BrokerSettingsPage)
    await flushPromises()
    expect(w.get('[data-testid="account-margin-reason"]').text()).toBe(ACCOUNT_UNREADABLE)
    expect(w.find('[data-testid="account-margin-figure"]').exists()).toBe(false)
    expect(w.get('[data-testid="account-id-none"]').exists()).toBe(true)
  })

  it('AC-13: funds_read off shows its reason', async () => {
    accountAnswer = () => Promise.resolve({ data: none('not_offered') })
    const w = mount(BrokerSettingsPage)
    await flushPromises()
    expect(w.get('[data-testid="account-margin-reason"]').text()).toBe(MARGIN_REASON.not_offered)
  })
})
