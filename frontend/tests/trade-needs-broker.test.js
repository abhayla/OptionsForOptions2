// REQ-015 AC-10 (RD-012, reference screen catalogue 246): with no broker connected the Trade action is shown disabled,
// with its reason, before any click. Answer states of GET /broker/status (standing item d): account_connection stated
// "connected" -> the action is a link; "partial", "disconnected", a missing field, a body that is not an object, a failed
// read -> disabled with the reason (never enabled on a guess).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import { TRADE_NEEDS_BROKER_REASON } from '@/lib/brokerConnected'

let broker = () => Promise.resolve({ data: { account_connection: { state: 'connected', fix: null } } })
let features = () => Promise.resolve({ data: { order_path: 'on' } })
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/broker/status' ? broker() : features()) } }
})

const REASON = 'Log in with Zerodha to trade. Use Connect Zerodha in Settings, then come back.'
const mountActions = async (props = {}) => {
  const w = mount(StrategyActions, { props: { hasLegs: true, savedId: 5, ...props }, global: { stubs: { RouterLink: { template: '<a data-testid="execute-strategy"><slot /></a>' } } } })
  await flushPromises()
  return w
}
const DOWN = [
  ['disconnected', () => Promise.resolve({ data: { account_connection: { state: 'disconnected', fix: 'connect_zerodha' } } })],
  ['partial', () => Promise.resolve({ data: { account_connection: { state: 'partial', fix: null } } })],
  ['field absent', () => Promise.resolve({ data: {} })],
  ['body not an object', () => Promise.resolve({ data: 'connected' })],
  ['upper-case Connected', () => Promise.resolve({ data: { account_connection: { state: 'Connected' } } })],
  ['request failed', () => Promise.reject(new Error('network'))],
]

beforeEach(() => {
  broker = () => Promise.resolve({ data: { account_connection: { state: 'connected', fix: null } } })
  features = () => Promise.resolve({ data: { order_path: 'on' } })
})

describe('AC-10: the Trade action with no broker connected', () => {
  it('the reason is the catalogue sentence', () => {
    expect(TRADE_NEEDS_BROKER_REASON).toBe(REASON)
  })

  it('connected -> the link is there and no disabled stand-in', async () => {
    const w = await mountActions()
    expect(w.find('[data-testid="execute-strategy"]').exists()).toBe(true)
    expect(w.find('[data-testid="execute-strategy-disabled"]').exists()).toBe(false)
  })

  it.each(DOWN)('%s -> disabled with its reason before any click, and no link', async (_n, reply) => {
    broker = reply
    const w = await mountActions()
    const stand = w.find('[data-testid="execute-strategy-disabled"]')
    expect(stand.exists()).toBe(true)
    expect(stand.attributes('disabled')).toBeDefined()
    expect(stand.attributes('title')).toBe(REASON)
    expect(w.find('[data-testid="execute-strategy-reason"]').text()).toBe(REASON)
    expect(w.find('[data-testid="execute-strategy"]').exists()).toBe(false)
  })

  it('order path off -> neither the link nor the disabled stand-in (absent, REQ-073 AC-6)', async () => {
    features = () => Promise.resolve({ data: { order_path: 'off' } })
    broker = DOWN[0][1]
    const w = await mountActions()
    expect(w.find('[data-testid="execute-strategy-disabled"]').exists()).toBe(false)
    expect(w.text()).not.toMatch(/Trade|Execute/)
  })

  it('not saved -> neither', async () => {
    broker = DOWN[0][1]
    const w = await mountActions({ savedId: null })
    expect(w.find('[data-testid="execute-strategy-disabled"]').exists()).toBe(false)
  })
})
