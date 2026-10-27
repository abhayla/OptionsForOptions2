// Row 28f (REQ-070 AC-3/AC-4/AC-5/AC-6, ADR-118): the history panel, Restore, Undo after a save, and Delete with Undo in the
// Builder's saved list. The fakes copy the key set of the REAL replies read on ofo_dev (core proof, 2026-10-25): a history entry
// has exactly at, change_summary, definition, schema_version, seq; a leg has action, contract_id, contract_state, exchange_segment,
// exchange_token, expiry, instrument, quantity, strike; StrategyOut has created_at, definition, id, name, revision, status,
// updated_at, versions; a list row has can_delete, created_at, first_leg, id, leg_count, name, status, tracked, underlying, updated_at.
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ActivityPanel from '@/components/strategy/ActivityPanel.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { CLEAR_UNDO_MS } from '@/lib/legEdit'
import { DELETE_REFUSED_TEXT, NO_EARLIER_TEXT } from '@/lib/strategyActivity'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    if (typeof a === 'function') return a(body)
    return Promise.resolve({ data: structuredClone(a) })
  }
  return {
    ...actual,
    default: {
      get: (u) => respond('GET', u),
      post: (u, b) => respond('POST', u, b),
      put: (u, b) => respond('PUT', u, b),
      patch: (u, b) => respond('PATCH', u, b),
      delete: (u) => respond('DELETE', u),
    },
  }
})
beforeEach(() => {
  calls.length = 0
  answers = {}
})
afterEach(() => vi.useRealTimers())

const contract = { contract_id: 2381960, exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-27', strike: '23650.00', lot_size: 65, symbol: 'NIFTY26O2723650CE' }
const savedLeg = (over = {}) => ({ action: 'BUY', contract_id: 2381960, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 44624, expiry: '2026-10-27', instrument: 'CE', quantity: 65, strike: '23650.00', ...over })
// `restorable` is the server's per-entry answer (the rule restore() enforces); a test that omits it gets true, a test of the
// missing field uses withoutRestorable().
const entry = (seq, summary, legOver = {}, restorable = true) => ({
  schema_version: 1, seq, at: `2026-10-25T02:3${seq}:58.782625Z`, change_summary: summary, restorable,
  definition: { underlying: 'NIFTY', legs: [savedLeg(legOver)] },
})
const withoutRestorable = (e) => { const { restorable: _r, ...rest } = e; return rest }
const strategyOut = (revision, legOver = {}) => ({
  created_at: '2026-10-25T02:30:00Z', updated_at: '2026-10-25T02:40:00Z', id: 5, name: '"e2e 28f"', revision, status: 'draft', versions: [],
  definition: { underlying: 'NIFTY', legs: [savedLeg(legOver)] },
})
const catalogue = () => { answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-27'] = { contracts: [contract] } }
const SUMMARY_1 = 'removed leg SELL 23750 CE 2026-10-27 x65; added leg SELL 23700 CE 2026-10-27 x65'
const SUMMARY_2 = 'restored entry 1'
const AFTER_EXECUTION = { what_happened: 'This strategy has been executed.', impact: 'It was not changed.', what_is_blocked: 'Restoring.', next_action: 'Make a new strategy.' }
const current = { id: 5, revision: 2, name: '"e2e 28f"' }

async function openPanel(props = { current }) {
  const w = mount(ActivityPanel, { props })
  await w.get('[data-testid="activity-toggle"]').trigger('click')
  await flushPromises()
  return w
}

describe('the history panel (REQ-070 AC-3, AC-5)', () => {
  it('is closed on first render and reads nothing until opened', async () => {
    const w = mount(ActivityPanel, { props: { current } })
    await flushPromises()
    expect(w.find('[data-testid="activity-body"]').exists()).toBe(false)
    expect(calls).toHaveLength(0)
  })

  it('W-192 UI-108: inside the History drawer it has no toggle, reads the history once on mount and lists it', async () => {
    answers['GET /strategies/5/history'] = { entries: [entry(1, SUMMARY_1)] }
    const w = mount(ActivityPanel, { props: { current, inDrawer: true } })
    await flushPromises()
    expect(w.find('[data-testid="activity-toggle"]').exists()).toBe(false)
    expect(calls.filter((c) => c.url === '/strategies/5/history')).toHaveLength(1)
    expect(w.findAll('[data-testid="activity-entry"]').map((r) => r.attributes('data-seq'))).toEqual(['1'])
  })

  it('lists entries newest first with the server summary text, unchanged', async () => {
    answers['GET /strategies/5/history'] = { entries: [entry(1, SUMMARY_1), entry(2, SUMMARY_2, { contract_id: 2381961 })] }
    answers['GET /strategies/5'] = strategyOut(3)
    const w = await openPanel()
    const rows = w.findAll('[data-testid="activity-entry"]')
    expect(rows.map((r) => r.attributes('data-seq'))).toEqual(['2', '1'])
    expect(rows[1].get('[data-testid="activity-summary"]').text()).toBe(SUMMARY_1)
    expect(rows[0].get('[data-testid="activity-summary"]').text()).toBe(SUMMARY_2)
  })

  it('Restore sends the page revision, then hands the reply legs and revision to the Builder', async () => {
    answers['GET /strategies/5/history'] = { entries: [entry(1, SUMMARY_1, { strike: '23650.00' })] }
    answers['GET /strategies/5'] = strategyOut(2, { contract_id: 2381961 })
    answers['POST /strategies/5/restore/1?expected_revision=2'] = strategyOut(3)
    catalogue()
    const w = await openPanel()
    await w.get('[data-testid="restore-1"]').trigger('click')
    await flushPromises()
    const [legs, id, revision] = w.emitted('open')[0]
    expect(id).toBe(5)
    expect(revision).toBe(3)
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ contract_id: 2381960, strike: '23650.00', lots: 1 })
  })

  it('Restore is offered only on restorable === true: false, null and a missing field show none (fail closed)', async () => {
    answers['GET /strategies/5/history'] = { entries: [
      entry(1, SUMMARY_1, {}, true), entry(2, 'renamed', {}, false), entry(3, SUMMARY_1, {}, null), withoutRestorable(entry(4, SUMMARY_1)),
    ] }
    answers['GET /strategies/5'] = strategyOut(2)
    const w = await openPanel()
    expect(w.find('[data-testid="restore-1"]').exists()).toBe(true)
    for (const seq of [2, 3, 4]) expect(w.find(`[data-testid="restore-${seq}"]`).exists()).toBe(false)
    expect(w.findAll('[data-testid="activity-entry"]')).toHaveLength(4) // the entries stay listed
  })

  it('a restorable entry is offered even when its legs equal the saved ones (the screen no longer infers from the legs)', async () => {
    answers['GET /strategies/5/history'] = { entries: [entry(1, SUMMARY_1)] }
    answers['GET /strategies/5'] = strategyOut(2)
    const w = await openPanel()
    expect(w.find('[data-testid="restore-1"]').exists()).toBe(true)
  })

  it('after execution the server refuses: its message is shown, nothing is replaced and the list stays', async () => {
    answers['GET /strategies/5/history'] = { entries: [entry(1, SUMMARY_1, { strike: '23650.00' })] }
    answers['GET /strategies/5'] = strategyOut(2, { contract_id: 2381961 })
    answers['POST /strategies/5/restore/1?expected_revision=2'] = () => Promise.reject({ status: 409, parts: AFTER_EXECUTION })
    const w = await openPanel()
    await w.get('[data-testid="restore-1"]').trigger('click')
    await flushPromises()
    expect(w.emitted('open')).toBeUndefined()
    expect(w.get('[data-testid="activity-error"]').text()).toContain(AFTER_EXECUTION.what_happened)
    expect(w.findAll('[data-testid="activity-entry"]')).toHaveLength(1)
  })

  it('no entries gives the plain "no earlier versions" line', async () => {
    answers['GET /strategies/5/history'] = { entries: [] }
    answers['GET /strategies/5'] = strategyOut(1)
    const w = await openPanel()
    expect(w.get('[data-testid="activity-empty"]').text()).toBe(NO_EARLIER_TEXT)
  })
})

const barLeg = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'BUY', lots: 1, planned_entry: null, captured_at: null }
function barAnswers({ before, after, restorable = true }) {
  catalogue()
  let history = 0
  answers['GET /strategies/5/history'] = () => Promise.resolve({ data: { entries: (history++ === 0 ? before : after).map((s) => {
    const e = entry(s, SUMMARY_1, {}, restorable === 'missing' ? true : restorable)
    return restorable === 'missing' ? withoutRestorable(e) : e
  }) } })
  answers['PUT /strategies/5'] = strategyOut(3)
  answers['GET /strategies'] = { strategies: [] }
  answers['POST /strategies/5/restore/2?expected_revision=3'] = strategyOut(4)
}
async function saveOnce(w) {
  await w.get('[data-testid="save-draft"]').trigger('click')
  await flushPromises()
}

describe('Undo after a meaningful save (REQ-070 AC-4)', () => {
  it('is offered once, restores the entry the save wrote with the revision the save returned', async () => {
    barAnswers({ before: [1], after: [1, 2] })
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await saveOnce(w)
    await w.get('[data-testid="save-undo"]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url)).toEqual(['/strategies/5/restore/2?expected_revision=3'])
    const [legs, id, revision] = w.emitted('open')[0]
    expect([id, revision, legs.length]).toEqual([5, 4, 1])
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
  })

  it('offers no Undo when the newest entry is not restorable (false, or the field missing)', async () => {
    for (const restorable of [false, 'missing']) {
      barAnswers({ before: [1], after: [1, 2], restorable })
      const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
      await flushPromises()
      await saveOnce(w)
      expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
      expect(w.find('[data-testid="save-error"]').exists()).toBe(false)
    }
  })

  it('a save that wrote no entry offers no Undo', async () => {
    barAnswers({ before: [1], after: [1] })
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await saveOnce(w)
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
  })

  it('an unreadable history before the save offers no Undo (fail closed)', async () => {
    barAnswers({ before: [1], after: [1, 2] })
    answers['GET /strategies/5/history'] = () => Promise.reject({ status: 409, parts: AFTER_EXECUTION })
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await saveOnce(w)
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
    expect(w.find('[data-testid="save-error"]').exists()).toBe(false) // the save itself succeeded
  })

  it('expires after the Clear-all window', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    barAnswers({ before: [1], after: [1, 2] })
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await saveOnce(w)
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(true)
    vi.advanceTimersByTime(CLEAR_UNDO_MS - 1)
    await flushPromises()
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(true)
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
  })

  it('is dropped when a new leg list arrives: it can never restore over newer legs', async () => {
    barAnswers({ before: [1], after: [1, 2] })
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await saveOnce(w)
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(true)
    await w.setProps({ legs: [{ ...barLeg, lots: 2 }] })
    expect(w.find('[data-testid="save-undo"]').exists()).toBe(false)
  })
})

const listRow = (id, can_delete) => ({
  id, underlying: 'NIFTY', status: 'draft', name: `"S${id}"`, leg_count: 1, first_leg: { expiry: '2026-10-27', strike: '23650.00', instrument: 'CE' },
  tracked: false, created_at: '2026-10-25T02:30:00Z', updated_at: '2026-10-25T02:40:00Z', ...(can_delete === undefined ? {} : { can_delete }),
})

describe('Delete in the Builder saved list (REQ-070 AC-6)', () => {
  it('offers Delete only when can_delete is true; otherwise the refusal text replaces it; absent counts as false', async () => {
    answers['GET /strategies'] = { strategies: [listRow(5, true), listRow(6, false), listRow(7)] }
    const w = mount(SaveDraftBar, { props: { legs: [], current: null } })
    await flushPromises()
    const rows = w.findAll('[data-testid="saved-draft-row"]')
    const rowOf = (id) => rows.find((r) => r.text().includes(`S${id}`))
    expect(rowOf(5).find('[data-testid="delete-5"]').exists()).toBe(true)
    for (const id of [6, 7]) {
      const row = rowOf(id)
      expect(row.find(`[data-testid="delete-${id}"]`).exists()).toBe(false)
      expect(row.get('[data-testid="delete-refused"]').text()).toBe(DELETE_REFUSED_TEXT)
    }
  })

  it('deleting the strategy open in the Builder tells the Builder (it returns to a new strategy); Undo brings the row back', async () => {
    answers['GET /strategies'] = { strategies: [listRow(5, true)] }
    answers['GET /strategies/5'] = strategyOut(2)
    answers['DELETE /strategies/5?expected_revision=2'] = { id: 5, revision: 2 }
    answers['POST /strategies/5/undelete?expected_revision=2'] = strategyOut(2)
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await w.get('[data-testid="delete-5"]').trigger('click')
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    expect(w.emitted('deleted')[0]).toEqual([5])
    expect(w.find('[data-testid="saved-draft-row"]').exists()).toBe(false)
    await w.get('[data-testid="delete-undo"]').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-testid="saved-draft-row"]')).toHaveLength(1)
    // Undo of the open strategy's delete re-opens it (same id, its revision): the Builder's next Save updates it, not a second one
    expect(w.emitted('saved')[0]).toEqual([5, 2, '"e2e 28f"'])
  })

  it('Undo of a delete of a strategy that was NOT open does not re-open anything', async () => {
    answers['GET /strategies'] = { strategies: [listRow(6, true)] }
    answers['GET /strategies/6'] = { ...strategyOut(2), id: 6 }
    answers['DELETE /strategies/6?expected_revision=2'] = { id: 6, revision: 2 }
    answers['POST /strategies/6/undelete?expected_revision=2'] = { ...strategyOut(2), id: 6 }
    const w = mount(SaveDraftBar, { props: { legs: [barLeg], current } })
    await flushPromises()
    await w.get('[data-testid="delete-6"]').trigger('click')
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    await w.get('[data-testid="delete-undo"]').trigger('click')
    await flushPromises()
    expect(w.emitted('deleted')).toBeUndefined()
    expect(w.emitted('saved')).toBeUndefined()
  })
})
