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
    expect(t(w, 'saved-draft-row').text()).toContain('Draft 7, NIFTY, updated 15 Oct 2026, 11:59:59 IST')
  })

  // W-192 (ADR-193 UI-108, UI-112): Save in the action row, Save As / Rename in the "..." menu, the list in the Saved tab
  it('UI-112: the Saved tab shows the 10 first rows of the server list, narrowed by a text search on name or underlying', async () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, name: `Plan ${i + 1}`, underlying: i === 11 ? 'SENSEX' : 'NIFTY', updated_at: '2026-10-15T06:29:59Z' }))
    answers['GET /strategies'] = { strategies: rows }
    const w = mount(SaveDraftBar, { props: { legs: [] }, attachTo: document.body })
    await flushPromises()
    expect(t(w, 'tab-panel-saved').isVisible()).toBe(false) // Ready-made is the first tab
    await t(w, 'tab-saved').trigger('click')
    expect(t(w, 'tab-panel-saved').isVisible()).toBe(true)
    expect(w.findAll('[data-testid="saved-draft-row"]').map((r) => r.attributes('data-current'))).toHaveLength(10)
    await t(w, 'saved-search').setValue('sensex')
    expect(w.findAll('[data-testid="saved-draft-name"]').map((r) => r.text())).toEqual(['Plan 12, SENSEX, updated 15 Oct 2026, 11:59:59 IST'])
    await t(w, 'saved-search').setValue('no such plan')
    expect(t(w, 'saved-empty').text()).toBe('No saved strategy matches.')
    w.unmount()
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

  it('the picker shows the lot-size line with the contract name', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/SENSEX/expiries'] = { underlying: 'SENSEX', expiries: [] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = {
      underlying: 'NIFTY',
      contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }],
    }
    const w = mount(LegPicker, { props: { legs: [] } })
    await flushPromises()
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    await t(w, 'pick-type').setValue('CE')
    await t(w, 'pick-strike').setValue('22800.00')
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
