// Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens; a real action is only stored, nothing sent to Zerodha); ADR-016 to ADR-019; ADR-281.
// Lane R2: a REAL position's stops and exits are listed and controlled like paper (full Cancel and Keep), each says "Not sent to Zerodha.
// Place it in Kite."; the "real unreadable" and "not applicable: real" branches are gone; a position whose kind is unknown stays locked.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let list = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u.endsWith('/triggers') ? Promise.resolve({ data: { triggers: list } }) : Promise.reject({ status: 404, parts: null })), post: () => Promise.reject({ status: 404 }), delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStops from '@/components/strategy/PaperStops.vue'
import PlanEntry from '@/components/strategy/PlanEntry.vue'
import { NOT_APPLICABLE_TEXT, armedIndexExits, exitsViewOf } from '@/lib/paperTriggers'
import { REAL_STOPS_TEXT } from '@/lib/positionKind'

const NOT_SENT = 'Not sent to Zerodha. Place it in Kite.'
const trig = (over = {}) => ({ id: 7, strategy_id: 48, kind: 'leg_stop', direction: 'below', level: '100.00', level_text: '100.00', contract_id: 'C1',
  contract_text: 'NIFTY 24500 CE', underlying: 'NIFTY', state: 'armed', created_at: '2026-11-20T05:00:00Z', fired_at: null, cancelled_at: null,
  set_before_adjustment: true, adjustment_note: 'n', stored_not_sent: true, ...over })

describe('PaperStops for a real position', () => {
  it('the label is the real sentence; an armed real stop has its state, Cancel, Keep and the not-sent line', async () => {
    list = [trig()]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [], kind: 'real' } })
    await flushPromises()
    expect(w.get('[data-testid="stops-label"]').text()).toBe(REAL_STOPS_TEXT)
    expect(w.get('[data-testid="trigger-state"]').text()).toBe('armed')
    expect(w.find('[data-testid="trigger-cancel-7"]').exists()).toBe(true)
    expect(w.find('[data-testid="trigger-keep-7"]').exists()).toBe(true)
    expect(w.get('[data-testid="trigger-not-sent"]').text()).toBe(NOT_SENT)
    w.unmount()
  })
  it('paper keeps its label and shows no not-sent line', async () => {
    list = [trig({ stored_not_sent: undefined })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    expect(w.get('[data-testid="stops-label"]').text()).toContain('Paper')
    expect(w.find('[data-testid="trigger-not-sent"]').exists()).toBe(false)
    w.unmount()
  })
  it('a fired real stop shows the record line with its price', async () => {
    list = [trig({ state: 'fired', stored_not_sent: true, record: { action: 'stop_fired', stored_at: '2026-11-28T10:32:00+05:30', price: '99.00' } })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [], kind: 'real' } })
    await flushPromises()
    expect(w.get('[data-testid="trigger-not-sent"]').text()).toBe(`Stop reached 10:32:00 at 99.00. ${NOT_SENT}`)
    w.unmount()
  })
  it('an unknown-kind (not_applicable) row stays locked: the sentence only, no Cancel, no Keep, no "real position" wording', async () => {
    list = [trig({ state: 'not_applicable', stored_not_sent: undefined })]
    const w = mount(PaperStops, { props: { strategyId: 48, underlying: 'NIFTY', legs: [] } })
    await flushPromises()
    expect(w.get('[data-testid="trigger-row"]').text()).toBe(NOT_APPLICABLE_TEXT)
    expect(NOT_APPLICABLE_TEXT).not.toContain('real position')
    expect(w.find('[data-testid="trigger-cancel-7"]').exists()).toBe(false)
    expect(w.find('[data-testid="trigger-keep-7"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('Plan card exits', () => {
  it('a real trade lists its exits like paper, with the not-sent line; no "cannot be read here yet" branch', () => {
    const exits = armedIndexExits([trig({ id: 5, kind: 'conditional_exit', level_text: '25,720', direction: 'above' })])
    const w = mount(PlanEntry, { props: { strategyId: 48, exits, check: null } })
    expect(w.get('[data-testid="plan-entry-exit-5"]').text()).toContain('Armed.')
    expect(w.get('[data-testid="plan-entry-exit-not-sent"]').text()).toBe(NOT_SENT)
    expect(w.find('[data-testid="plan-entry-exits-real-unreadable"]').exists()).toBe(false)
    w.unmount()
  })
  it('exitsViewOf: rows, none, failed (a failed read is said so for any trade, never "none")', () => {
    expect(exitsViewOf([{ id: 1 }], false)).toEqual({ kind: 'rows', rows: [{ id: 1 }] })
    expect(exitsViewOf([], false)).toEqual({ kind: 'none', rows: [] })
    expect(exitsViewOf(undefined, false)).toEqual({ kind: 'none', rows: [] })
    expect(exitsViewOf([{ id: 1 }], true)).toEqual({ kind: 'failed', rows: [] })
  })
})
