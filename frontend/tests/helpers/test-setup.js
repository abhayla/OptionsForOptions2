// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/tests/helpers/test-setup.js (ADR-047)
// Shared Vitest helpers. Changed: mockApi401 and the token wording are dropped (no token auth here).
import { beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

/** Standard store test setup: fresh Pinia, cleared mocks, cleared localStorage before each test. */
export function setupStoreTest() {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    if (typeof localStorage !== 'undefined') {
      localStorage.clear()
    }
  })
}

/** Mock a successful API response for one call: mockApiSuccess(api, 'get', { id: 1 }) */
export function mockApiSuccess(apiModule, method, data) {
  apiModule[method].mockResolvedValueOnce({ data })
}

/** Mock a failed API response for one call (defaults to a network error). */
export function mockApiError(apiModule, method, error = new Error('Network Error')) {
  apiModule[method].mockRejectedValueOnce(error)
}
