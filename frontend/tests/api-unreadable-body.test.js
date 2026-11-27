// REQ-065 / REQ-162 / ADR-008: the shared API door rejects a 2xx whose body is not JSON, so every caller fails closed.
import { describe, expect, it } from 'vitest'
import api, { hasShape, unreadableBody } from '../src/services/api'

const res = (data, status = 200, config = {}) => ({ status, data, config })
const answer = (data) => async (config) => ({ data, status: 200, statusText: 'OK', headers: {}, config })

describe('unreadableBody', () => {
  it('flags a 2xx with a raw text body (axios could not parse it)', () => {
    expect(unreadableBody(res('<html>gateway</html>'))).toBe(true)
    expect(unreadableBody(res('not json'))).toBe(true)
  })
  it('does not flag objects, arrays, empty bodies (204) or non-JSON response types', () => {
    expect(unreadableBody(res({ strategies: [] }))).toBe(false)
    expect(unreadableBody(res([]))).toBe(false)
    expect(unreadableBody(res('', 204))).toBe(false)
    expect(unreadableBody(res('a,b', 200, { responseType: 'text' }))).toBe(false)
  })
})

describe('the shared client', () => {
  it('rejects a 200 with an HTML body as a failed read, like a network failure', async () => {
    await expect(api.get('/strategies', { adapter: answer('<html>proxy error') })).rejects.toMatchObject({ unreadable: true, status: 200 })
  })
  it('passes a readable body through', async () => {
    await expect(api.get('/strategies', { adapter: answer({ strategies: [] }) })).resolves.toMatchObject({ data: { strategies: [] } })
  })
})

describe('hasShape', () => {
  it('needs a plain object with every key', () => {
    expect(hasShape({ strategies: [] }, ['strategies'])).toBe(true)
    expect(hasShape({ unexpected: true }, ['strategies'])).toBe(false)
    expect(hasShape(null, ['a'])).toBe(false)
    expect(hasShape([], [])).toBe(false)
  })
})
