// REQ-117 AC-1, AC-4 (W-132): the browser's flag reader. A flag is on only when the body states exactly `true` for one
// of the seven named flags; everything else, and every failed read, is off.
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))
import api from '@/services/api'
import { CAPABILITY_NAMES, capabilityOn, fetchCapabilities, resetCapabilities } from '@/lib/brokerCapabilities'

const SEVEN = ['basket_page_orders', 'broker_held_triggers', 'intraday_product', 'order_update_stream', 'funds_read',
  'positions_read', 'basket_margin_quote'] // REQ-117 AC-1 wording

beforeEach(() => { vi.clearAllMocks(); resetCapabilities() })

describe('capabilityOn', () => {
  it('AC-1: the closed list is exactly the seven names', () => {
    expect([...CAPABILITY_NAMES]).toEqual(SEVEN)
  })

  it('AC-4: on only for exact true on a named flag', () => {
    const all = Object.fromEntries(SEVEN.map((n) => [n, true]))
    expect(SEVEN.map((n) => capabilityOn(all, n))).toEqual(Array(7).fill(true))
  })

  it.each([null, undefined, 'x', 5, [], [true], {}, { funds_read: 'true' }, { funds_read: 1 }, { funds_read: null }])(
    'AC-4: body %j -> every flag off', (body) => {
      expect(SEVEN.map((n) => capabilityOn(body, n))).toEqual(Array(7).fill(false))
    })

  it('AC-4: an unknown name, an inherited key or a non-string name is off even if the body says true', () => {
    const body = { toString: true, constructor: true, unknown_flag: true, funds_read: true }
    for (const name of ['unknown_flag', 'toString', 'constructor', '', null, undefined, 7, ['funds_read']]) {
      expect(capabilityOn(body, name)).toBe(false)
    }
    expect(capabilityOn(body, 'funds_read')).toBe(true)
  })
})

describe('fetchCapabilities', () => {
  it('reads once and shares the answer', async () => {
    api.get.mockResolvedValue({ data: { funds_read: true } })
    const [a, b] = await Promise.all([fetchCapabilities(), fetchCapabilities()])
    expect(a).toEqual({ funds_read: true })
    expect(b).toBe(a)
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith('/broker/capabilities')
  })

  it('AC-4: a failed read is {} (all off), and the next call reads again', async () => {
    api.get.mockRejectedValueOnce({ status: 500 })
    expect(await fetchCapabilities()).toEqual({})
    api.get.mockResolvedValueOnce({ data: { funds_read: true } })
    expect(await fetchCapabilities()).toEqual({ funds_read: true })
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
