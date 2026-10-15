// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/tests/setup.js (ADR-047)
// Changed: the import.meta.env stub is dropped (no env-based API URL); the WebSocket stub is an inert socket (W-065).
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

// W-065: the Builder page opens the live socket. Unit tests never reach a network socket: this one never opens, never
// pushes and never closes, so a page left mounted by one test cannot fall back to REST during another. The socket's own
// lifecycle is tested with a scripted fake in tests/strategy-live.test.js.
class InertWebSocket {
  constructor(url) {
    this.url = url
    this.readyState = 0
  }
  send() {}
  close() {
    this.readyState = 3
  }
}
global.WebSocket = InertWebSocket
