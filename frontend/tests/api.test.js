import { describe, it, expect } from 'vitest'
import api, { mapError, NEUTRAL_ERROR } from '@/services/api'

describe('api client (ADR-012, same-origin, no token storage)', () => {
  it('uses the same-origin /api base and cookie credentials', () => {
    expect(api.defaults.baseURL).toBe('/api')
    expect(api.defaults.withCredentials).toBe(true)
  })

  it('never reads or writes localStorage when a request is built', async () => {
    const adapter = (config) => Promise.resolve({ data: {}, status: 200, statusText: 'OK', headers: {}, config })
    await api.get('/health', { adapter })
    expect(localStorage.getItem).not.toHaveBeenCalled()
    expect(localStorage.setItem).not.toHaveBeenCalled()
  })

  it('sends no Authorization header', async () => {
    let seen
    const adapter = (config) => {
      seen = config.headers
      return Promise.resolve({ data: {}, status: 200, statusText: 'OK', headers: {}, config })
    }
    await api.get('/health', { adapter })
    expect(seen.Authorization).toBeUndefined()
  })

  it('maps any failure to a neutral message without server detail', async () => {
    const adapter = (config) =>
      Promise.reject(Object.assign(new Error('boom'), { config, response: { status: 500, data: { detail: 'SECRET internals' } } }))
    await expect(api.get('/x', { adapter })).rejects.toEqual({ message: NEUTRAL_ERROR, status: 500 })
    expect(JSON.stringify(mapError(new Error('x')))).not.toMatch(/internals/)
  })

  it('keeps the catalogue code of a catalogue answer, and no parts for a bare 404 (NEW-T66 finish)', () => {
    const body = { code: 'STRATEGY_VALIDATION_523', what_happened: 'a', impact: 'b', what_is_blocked: 'c', next_action: 'd' }
    const out = mapError({ response: { status: 404, data: body } })
    expect(out.error_code).toBe('STRATEGY_VALIDATION_523')
    expect(out.parts).toEqual({ what_happened: 'a', impact: 'b', what_is_blocked: 'c', next_action: 'd' })
    const bare = mapError({ response: { status: 404, data: { detail: 'Not Found' } } })
    expect(bare.error_code).toBeUndefined()
    expect(bare.parts).toBeUndefined() // REQ-065: a bare 404 is the neutral failure; only the catalogue's own body is worded
  })
})
