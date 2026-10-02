// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/tests/setup.js (ADR-047)
// Changed: the WebSocket and import.meta.env stubs are dropped (no WS client, no env-based API URL yet).
import { vi, beforeEach } from 'vitest'
import { config } from '@vue/test-utils'

// Mock localStorage, so a test can prove the app never writes a token to it.
const localStorageMock = {
  store: {},
  getItem: vi.fn((key) => localStorageMock.store[key] || null),
  setItem: vi.fn((key, value) => {
    localStorageMock.store[key] = value
  }),
  removeItem: vi.fn((key) => {
    delete localStorageMock.store[key]
  }),
  clear: vi.fn(() => {
    localStorageMock.store = {}
  }),
}
global.localStorage = localStorageMock

beforeEach(() => {
  localStorageMock.store = {}
  localStorageMock.getItem.mockClear()
  localStorageMock.setItem.mockClear()
  localStorageMock.removeItem.mockClear()
  localStorageMock.clear.mockClear()
})

config.global.mocks = {
  $t: (msg) => msg,
}
