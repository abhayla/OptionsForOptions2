// I-24 (Lane FC, 28 Nov): the exits line of the Plan card is read from ONE paper route (GET /paper/strategies/{id}/triggers). A real-mode trade has no
// such route, so its exits can neither be shown nor said to be "none": the card says so in one plain line. Spec basis: ADR-330 (58), REQ-109 AC-8.
// Cases: paper trade (rows), real trade (the one line, no rows, no failure line), read failed (failure line, never "none"), empty (nothing).
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const LABELS = { plan_entry: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  edit: 'Edit plan', no_plan: 'No plan: nothing is watched for this strategy', set_plan: 'Set plan' }
const PLAN = { strategy_id: 7, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null, labels: LABELS, plan: null,
  playbooks: [{ id: 9, name: 'Mine', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }], prefill: { playbook_id: 9 } }
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: PLAN }), post: () => Promise.resolve({ data: PLAN }), put: () => Promise.resolve({ data: PLAN }) } }
})
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { EXITS_REAL_UNREADABLE_TEXT, exitsViewOf } from '@/lib/paperTriggers'

const X = { id: 31, direction: 'above', level_text: '25,720', state: 'armed' }
async function card(props) {
  const w = mount(PlanEntry, { props: { strategyId: 7, check: null, checkStatus: 'loading', ...props } })
  await flushPromises()
  return w
}
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()

describe('exitsViewOf: one rule for the exits line', () => {
  it('paper: rows, failed, none; real: unreadable whatever else is passed; an unknown mode is read as paper', () => {
    expect(exitsViewOf('paper', [X], false)).toEqual({ kind: 'rows', rows: [X] })
    expect(exitsViewOf('paper', [], false)).toEqual({ kind: 'none', rows: [] })
    expect(exitsViewOf('paper', [], true)).toEqual({ kind: 'failed', rows: [] })
    // FC3 (28 Nov): the real route exists (GET /real/strategies/{id}/triggers): a real trade reads like a paper one; the sentence stays for a FAILED read only
    expect(exitsViewOf('real', [X], false)).toEqual({ kind: 'rows', rows: [X] })
    expect(exitsViewOf('real', [], false)).toEqual({ kind: 'none', rows: [] })
    expect(exitsViewOf('real', [], true)).toEqual({ kind: 'real_unreadable', rows: [] })
    expect(exitsViewOf(undefined, [X], false).kind).toBe('rows')
  })
  it('the sentence', () => expect(EXITS_REAL_UNREADABLE_TEXT).toBe('Exits of a real-mode trade cannot be read here yet.'))
})

describe('PlanEntry exits line by mode', () => {
  it('paper trade: the armed exit line; no real-mode line, no failure line', async () => {
    const w = await card({ exits: [X], exitsMode: 'paper' })
    expect(w.get('[data-testid="plan-entry-exit-31"]').text()).toContain('25,720')
    expect(has(w, 'plan-entry-exits-real-unreadable')).toBe(false)
    expect(has(w, 'plan-entry-exits-failed')).toBe(false)
  })
  it('default mode is paper (the parent that passes none is unchanged)', async () => {
    const w = await card({ exits: [X] })
    expect(has(w, 'plan-entry-exit-31')).toBe(true)
  })
  it('real trade, read fine: the armed exit row, no sentence', async () => {
    const w = await card({ exits: [X], exitsFailed: false, exitsMode: 'real' })
    expect(w.get('[data-testid="plan-entry-exit-31"]').text()).toContain('25,720')
    expect(has(w, 'plan-entry-exits-real-unreadable')).toBe(false)
  })
  it('real trade, read failed: the one plain line; never a row, never "could not read", never silence', async () => {
    const w = await card({ exits: [], exitsFailed: true, exitsMode: 'real' })
    expect(w.get('[data-testid="plan-entry-exits-real-unreadable"]').text()).toBe('Exits of a real-mode trade cannot be read here yet.')
    expect(has(w, 'plan-entry-exits-failed')).toBe(false)
    expect(w.findAll('[data-testid^="plan-entry-exit-"]').filter((e) => /^plan-entry-exit-\d+$/.test(e.attributes('data-testid')))).toHaveLength(0)
  })
  it('read failed (paper): the failure line, no exit rows, no real-mode line', async () => {
    const w = await card({ exits: [], exitsFailed: true, exitsMode: 'paper' })
    expect(has(w, 'plan-entry-exits-failed')).toBe(true)
    expect(has(w, 'plan-entry-exits-real-unreadable')).toBe(false)
  })
  it('empty (paper, read fine): nothing is printed about exits', async () => {
    const w = await card({ exits: [], exitsFailed: false, exitsMode: 'paper' })
    expect(has(w, 'plan-entry-exits-failed')).toBe(false)
    expect(has(w, 'plan-entry-exits-real-unreadable')).toBe(false)
    expect(w.findAll('[data-testid^="plan-entry-exit-"]').filter((e) => /^plan-entry-exit-\d+$/.test(e.attributes('data-testid')))).toHaveLength(0)
  })
})
