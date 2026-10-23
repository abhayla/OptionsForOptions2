// W-121 (REQ-073 AC-6, ADR-165): the screens offer no Execute action unless the server says the order path is "on".
// Answer states of GET /features (standing item d): stated "on" -> Execute; stated "off", field absent, any other value,
// body not an object, request failed -> no Execute (absent from the page, not disabled). Routes /strategy/:id/execute and
// /execution/returned redirect to the strategy page with the same sentence unless "on".
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import { ORDER_PATH_OFF_SENTENCE, fetchOrderPathOn, orderPathIsOn, requireOrderPath } from '@/lib/orderPath'
import { routes } from '@/router/routes.js'

let answer = () => Promise.resolve({ data: { order_path: 'on' } })
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); return url === '/broker/status' ? Promise.resolve({ data: { account_connection: { state: 'connected' } } }) : answer() } } }
})

const SENTENCE = 'Placing orders from this app is switched off for now. You can build, save and track strategies.'
const STATES = [
  ['stated off', () => Promise.resolve({ data: { order_path: 'off' } })],
  ['field absent', () => Promise.resolve({ data: {} })],
  ['body empty', () => Promise.resolve({ data: '' })],
  ['body null', () => Promise.resolve({ data: null })],
  ['body not an object', () => Promise.resolve({ data: 'on' })],
  ['upper-case ON', () => Promise.resolve({ data: { order_path: 'ON' } })],
  ['boolean true', () => Promise.resolve({ data: { order_path: true } })],
  ['unknown value', () => Promise.resolve({ data: { order_path: 'maybe' } })],
  ['request failed (mapped error)', () => Promise.reject({ message: 'x', status: 500, parts: null })],
  ['request failed (network)', () => Promise.reject(new Error('network'))],
]

beforeEach(() => {
  calls.length = 0
  answer = () => Promise.resolve({ data: { order_path: 'on' } })
})

describe('AC-6: the order-path read', () => {
  it('only the stated answer "on" is on', async () => {
    expect(orderPathIsOn({ order_path: 'on' })).toBe(true)
    expect(await fetchOrderPathOn()).toBe(true)
    expect(calls).toEqual(['/features'])
  })

  it.each(STATES)('%s -> off', async (_name, reply) => {
    answer = reply
    expect(await fetchOrderPathOn()).toBe(false)
  })

  it('the sentence is the catalogue wording', () => {
    expect(ORDER_PATH_OFF_SENTENCE).toBe(SENTENCE)
  })
})

describe('AC-6: StrategyActions shows no Execute action unless told "on"', () => {
  const mountWith = async (props) => {
    const w = mount(StrategyActions, { props: { hasLegs: true, savedId: 5, ...props }, global: { stubs: { RouterLink: { template: '<a data-testid="execute-strategy"><slot /></a>' } } } })
    await flushPromises()
    return w
  }

  it('on + a saved strategy -> the action is there', async () => {
    expect((await mountWith({})).find('[data-testid="execute-strategy"]').exists()).toBe(true)
  })

  it.each(STATES)('%s -> the action is absent, not disabled', async (_name, reply) => {
    answer = reply
    const w = await mountWith({})
    expect(w.find('[data-testid="execute-strategy"]').exists()).toBe(false)
    expect(w.text()).not.toMatch(/Execute/)
  })

  it('on but not saved -> absent', async () => {
    expect((await mountWith({ savedId: null })).find('[data-testid="execute-strategy"]').exists()).toBe(false)
  })
})

describe('AC-6: the two order routes redirect when the path is not on', () => {
  const guarded = routes.filter((r) => ['execute-strategy', 'execution-returned'].includes(r.name))

  it('both order routes carry the guard', () => {
    expect(guarded.map((r) => r.name).sort()).toEqual(['execute-strategy', 'execution-returned'])
    for (const r of guarded) expect(r.beforeEnter).toBe(requireOrderPath)
  })

  it('on -> allowed', async () => {
    expect(await requireOrderPath()).toBe(true)
  })

  it.each(STATES)('%s -> redirect to the strategy page with the notice', async (_name, reply) => {
    answer = reply
    expect(await requireOrderPath()).toEqual({ path: '/strategy/builder', query: { notice: 'order_path_off' } })
  })

  it('through a real router: navigating to /strategy/1/execute lands on the builder when off', async () => {
    answer = () => Promise.resolve({ data: { order_path: 'off' } })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        ...guarded.map((r) => ({ ...r, component: { template: '<div />' } })),
        { path: '/strategy/builder', name: 'builder', component: { template: '<div />' } },
      ],
    })
    for (const target of ['/strategy/1/execute', '/execution/returned']) {
      await router.push(target)
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/strategy/builder')
      expect(router.currentRoute.value.query.notice).toBe('order_path_off')
    }
  })
})
