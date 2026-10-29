// W-077 AC-3 / issue #244: three Builder lines that had no test (the Save Draft bar's compact save-error, the saved-draft
// "updated" time, the advanced-details contract name and the picker's lot-size line) and the strict istTime cases.
// Expected text is hand-computed: 06:29:59 UTC + 5:30 = 11:59:59 IST; a NIFTY 13 Oct 22800 CE lot is 65 (the recorded row).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url) => respond('POST', url) } }
})
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import { TIME_UNAVAILABLE, istTime, nameFromPool } from '@/lib/displayFormat'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const LEG = {
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 1,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30',
}

beforeEach(() => {
  answers = { 'GET /strategies': { strategies: [] } }
})

describe('Save Draft bar', () => {
  it('a refused save shows the four catalogue parts in the compact message', async () => {
    const parts = { what_happened: 'A', impact: 'B', what_is_blocked: 'C', next_action: 'D' }
    answers['POST /strategies'] = Object.assign(new Error('x'), { parts })
    const w = mount(SaveDraftBar, { props: { legs: [LEG] } })
    await flushPromises()
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-form').trigger('submit') // REQ-134 AC-1: the first Save asks a name; the POST goes on confirm
    await flushPromises()
    expect(['save-error-what', 'save-error-impact', 'save-error-blocked', 'save-error-next'].map((id) => t(w, id).text()))
      .toEqual(['A', 'B', 'C', 'D'])
  })

  it('a saved draft row shows its updated time in India time', async () => {
    answers['GET /strategies'] = { strategies: [{ id: 7, underlying: 'NIFTY', updated_at: '2026-10-15T06:29:59Z' }] }
    const w = mount(SaveDraftBar, { props: { legs: [] } })
    await flushPromises()
    // GC-UI 6b D-C11: the row is two lines (name, legs); the updated time moved to the row's tooltip
    expect(t(w, 'open-draft-7').attributes('title')).toBe('NIFTY, updated 15 Oct 2026, 11:59:59 IST')
  })

  // W-192 (ADR-193 UI-108, UI-112): Save in the action row, Save As / Rename in the "..." menu, the list in the Saved tab
  it('UI-112: the Saved tab shows 10 rows of the server list, narrowed by a text search on name or underlying', async () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, name: `Plan ${i + 1}`, underlying: i === 11 ? 'SENSEX' : 'NIFTY', updated_at: '2026-10-15T06:29:59Z' }))
    answers['GET /strategies'] = { strategies: rows }
    const w = mount(SaveDraftBar, { props: { legs: [] }, attachTo: document.body })
    await flushPromises()
    expect(t(w, 'tab-panel-saved').isVisible()).toBe(false) // Ready-made is the first tab
    await t(w, 'tab-saved').trigger('click')
    expect(t(w, 'tab-panel-saved').isVisible()).toBe(true)
    expect(w.findAll('[data-testid="saved-draft-row"]').map((r) => r.attributes('data-current'))).toHaveLength(10)
    await t(w, 'saved-search').setValue('sensex')
    expect(w.findAll('[data-testid="saved-draft-name"]').map((r) => r.text())).toEqual(['Plan 12'])
    await t(w, 'saved-search').setValue('no such plan')
    expect(t(w, 'saved-empty').text()).toBe('No saved strategy matches.')
    w.unmount()
  })

  // CI #581 (strategy-save-draft.spec.ts): the server lists by id ASCENDING; with more than 10 stored, the tab showed the 10 OLDEST
  // and a just-saved draft had no Open button. UI-112: the 10 MOST RECENT, newest first.
  it('UI-112: the Saved tab shows the 10 most recent by updated time, newest first, so a just-saved draft is at the top', async () => {
    const at = (min) => `2026-10-15T06:${String(min).padStart(2, '0')}:00Z`
    const rows = Array.from({ length: 16 }, (_, i) => ({ id: i + 1, name: `Plan ${i + 1}`, underlying: 'NIFTY', updated_at: at(i + 10) }))
    rows[0].updated_at = at(59) // the OLDEST id was edited last: recency is updated time, not id
    answers['GET /strategies'] = { strategies: rows }
    answers['POST /strategies'] = { id: 17, revision: 1, name: 'New Strategy' }
    const w = mount(SaveDraftBar, { props: { legs: [LEG] }, attachTo: document.body })
    await flushPromises()
    await t(w, 'tab-saved').trigger('click')
    const ids = () => w.findAll('[data-testid="saved-draft-row"]').map((r) => r.find('button[data-testid^="open-draft-"]').attributes('data-testid'))
    expect(ids()).toEqual(['open-draft-1', ...[16, 15, 14, 13, 12, 11, 10, 9, 8].map((i) => `open-draft-${i}`)])
    // Save: the list re-reads and the new draft (id 17, newest) is the first row with its Open button
    answers['GET /strategies'] = { strategies: [...rows, { id: 17, name: 'New Strategy', underlying: 'NIFTY', updated_at: '2026-10-15T07:00:00Z' }] }
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(ids()[0]).toBe('open-draft-17')
    expect(t(w, 'open-draft-17').exists()).toBe(true)
    expect(ids()).toHaveLength(10)
    w.unmount()
  })

  it('UI-113 / UI-114: the Positions and Tracked tabs show the shared EmptyState with their sentence and name no broker', async () => {
    answers['GET /strategies'] = { strategies: [] }
    const w = mount(SaveDraftBar, { props: { legs: [] } })
    await flushPromises()
    const pos = t(w, 'tab-panel-positions')
    const trk = t(w, 'tab-panel-tracked')
    expect(pos.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(trk.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(pos.get('[data-testid="empty-state-message"]').text()).toBe('Open positions you hold will appear here, to analyse in the Builder.')
    expect(trk.get('[data-testid="empty-state-message"]').text()).toBe('Strategies you track appear in My Strategies.')
    for (const p of [pos, trk]) expect(p.text()).not.toMatch(/zerodha|kite|upstox|dhan|angel|broker/i)
  })

  it('UI-108: Save is in the action row; Save As and Rename open from the "..." menu for an open strategy', async () => {
    const w = mount(SaveDraftBar, { props: { legs: [LEG], current: { id: 3, revision: 1, name: 'Condor' } }, attachTo: document.body })
    await flushPromises()
    expect(t(w, 'action-row').find('[data-testid="save-draft"]').text()).toBe('Save')
    expect(t(w, 'more-menu-panel').isVisible()).toBe(false)
    await t(w, 'more-menu').trigger('click')
    expect(t(w, 'more-menu-panel').isVisible()).toBe(true)
    await t(w, 'rename-open').trigger('click')
    expect(t(w, 'more-menu-panel').isVisible()).toBe(false)
    expect(t(w, 'name-form').attributes('data-mode')).toBe('rename')
    w.unmount()
  })
})

describe('contract names in the advanced details and the picker', () => {
  it('adv-symbol names the contract from its fields, and a leg with none shows the fixed wording, never the id', () => {
    const rows = [{ instrument_id: 'NSE_FO:44624' }, { instrument_id: 'NSE_FO:1' }]
    const pool = [{ instrument_id: 'NSE_FO:44624', underlying: 'NIFTY', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00' }]
    const w = mount(AdvancedDetails, { props: { rows, nameOf: (r) => nameFromPool(r, pool, 'NIFTY') } })
    expect(w.findAll('[data-testid="adv-symbol"]').map((c) => c.text()))
      .toEqual(['NIFTY 13 Oct 22800 CE', 'Contract details not available'])
  })

  it('the Edit form shows the lot-size line with the contract name', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/SENSEX/expiries'] = { underlying: 'SENSEX', expiries: [] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = {
      underlying: 'NIFTY',
      contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }],
    }
    const leg = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: '2026-10-13T09:20:09+05:30', reason_code: null }
    const w = mount(LegPicker, { props: { legs: [leg] } }) // the by-contract form is the Edit path only (D-C31)
    await flushPromises()
    expect(t(w, 'pick-type').exists()).toBe(false)
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'lot-size').text()).toBe('NIFTY 13 Oct 22800 CE, lot size 65')
  })
})

describe('istTime strict parsing (#244)', () => {
  it('an impossible calendar date is not rolled over', () => {
    expect(istTime('2026-02-30T06:29:59Z')).toBe(TIME_UNAVAILABLE)
    expect(istTime('2026-04-31T06:29:59Z')).toBe(TIME_UNAVAILABLE)
  })
  it('a padded string is trimmed', () => {
    expect(istTime(' 2026-10-15T06:29:59Z ')).toBe('15 Oct 2026, 11:59:59 IST')
  })
  it('a fraction of any length and a +hh:mm offset', () => {
    expect(istTime('2026-10-15T11:59:59.362869+05:30')).toBe('15 Oct 2026, 11:59:59 IST')
    expect(istTime('2026-10-15T06:29:59.1Z')).toBe('15 Oct 2026, 11:59:59 IST')
  })
  it('an hour, minute, second or offset out of range, or a missing zone, is refused', () => {
    for (const bad of ['2026-10-15T24:00:00Z', '2026-10-15T06:60:00Z', '2026-10-15T06:29:60Z', '2026-10-15T06:29:59+24:00',
      '2026-10-15T06:29:59', '2026-10-15 06:29:59Z']) {
      expect(istTime(bad)).toBe(TIME_UNAVAILABLE)
    }
  })
})
