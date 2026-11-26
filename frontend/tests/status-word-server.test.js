// GC-ICLIVE D-28 round 2 (ADR-299 (4)): the browser does not derive the status word; it shows the server's `status_word`.
// Real 23 Nov case: condors 155-157, 159-161 were open legs with has_order true; here the rows carry the server word and
// deliberately disagree with the old derivation, so only reading the server word passes.
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let rows = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u === '/features' ? Promise.resolve({ data: { order_path: 'on' } }) : Promise.resolve({ data: { strategies: rows } })) } }
})
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import { strategyStatusWord, isRunning, isCompleted } from '@/lib/strategyStatus'
import { readPaperStrategy } from '@/lib/paperList'
import { STATUS_UNKNOWN } from '@/lib/sharedStateText'

const base = { id: 161, underlying: 'NIFTY', created_at: '2026-11-23T04:00:00Z', updated_at: '2026-11-23T04:00:00Z' }

describe('the one function returns the server word', () => {
  it('the server word wins over status / has_order; no word is "Status not available", never Draft', () => {
    expect(strategyStatusWord({ ...base, status: 'draft', has_order: false, status_word: 'Running' })).toBe('Running')
    expect(strategyStatusWord({ ...base, status: 'closed', has_order: true, status_word: 'Draft' })).toBe('Draft')
    expect(strategyStatusWord({ ...base, status: 'draft', has_order: true })).toBe(STATUS_UNKNOWN)
    expect(strategyStatusWord({ ...base, status_word: 'Unknown' })).toBe(STATUS_UNKNOWN)
    expect(isRunning({ ...base, status: 'draft', has_order: false, status_word: 'Running' })).toBe(true)
    expect(isCompleted({ ...base, status: 'draft', status_word: 'Completed' })).toBe(true)
  })
})

describe('a paper strategy of /paper/strategies carries the same word', () => {
  it('readPaperStrategy keeps the server word; an absent word is not guessed', () => {
    const s = { strategy_id: 161, state: 'EXITED', positions: [], open_count: 0, position_count: 0, name: '"C7"', underlying: 'NIFTY', status_word: 'Completed' }
    expect(readPaperStrategy(s).statusWord).toBe('Completed')
    expect(readPaperStrategy({ ...s, status_word: undefined }).statusWord).toBe(null)
  })
})

describe('My Strategies shows the server word', () => {
  it('a row the server calls Running reads Running whatever its flags say', async () => {
    setActivePinia(createPinia())
    rows = [{ ...base, status: 'draft', has_order: false, status_word: 'Running' }]
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'My Strategies', parent: 'Strategies' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.get('[data-testid="row-status"]').text()).toBe('Running')
  })
})
