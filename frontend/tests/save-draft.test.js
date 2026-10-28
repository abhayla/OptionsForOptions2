// W-071 (REQ-038 AC-5, ADR-057, ADR-075, ADR-068 item 1): the Save Draft body and the reopen rebuild. Pure functions.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import {
  STRATEGY_NAME_DEFAULT, buildSaveBody, buildUpdateBody, canSaveLegs, fetchSavedDraft, legsFromSaved, legsLine, noMatchText, plainName,
  saveAsName, searchStrategies, strategyLabel, trackedText,
} from '@/lib/saveDraft'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})
beforeEach(() => {
  calls.length = 0
  answers = {}
})
import { buildDraft } from '@/lib/legPicker'
import { applyEditReply } from '@/lib/legEdit'

const leg = (over = {}) => ({
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 2,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ltp: '999', ...over,
})
const contract = { contract_id: 2381960, exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE',
  expiry: '2026-10-19', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1922800CE' }
const saved = (over = {}) => ({ underlying: 'NIFTY', legs: [{ contract_id: 2381960, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 44624,
  action: 'SELL', instrument: 'CE', strike: '22800', expiry: '2026-10-19', quantity: 130,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ...over }] })

describe('buildSaveBody', () => {
  it('sends exactly contract_id, action, quantity, planned_entry, captured_at per leg', () => {
    const body = buildSaveBody([leg()], '')
    expect(Object.keys(body)).toEqual(['underlying', 'legs'])
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'captured_at', 'contract_id', 'planned_entry', 'quantity'])
    expect(body.legs[0]).toEqual({ contract_id: 2381960, action: 'SELL', quantity: 130, planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
  })
  it('never carries a live price or an instrument_id', () => {
    const text = JSON.stringify(buildSaveBody([leg()], 'tag'))
    expect(text).not.toContain('instrument_id')
    expect(text).not.toContain('ltp')
    expect(text).not.toContain('999')
  })
  it('a leg without an entry sends neither planned_entry nor captured_at; rules_ref only when given', () => {
    const body = buildSaveBody([leg({ planned_entry: null, captured_at: null })], 'e2e_tag')
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'contract_id', 'quantity'])
    expect(body.rules_ref).toBe('e2e_tag')
  })
  it('canSaveLegs needs legs that name their contract and lot size', () => {
    expect(canSaveLegs([])).toBe(false)
    expect(canSaveLegs([leg()])).toBe(true)
    expect(canSaveLegs([leg({ contract_id: undefined })])).toBe(false)
    expect(canSaveLegs([leg({ lot_size: 0 })])).toBe(false)
  })
})

describe('REQ-077 AC-4 the typed mark', () => {
  it('AC-4: a typed leg sends entry_source "typed" with the pair; a captured leg sends none', () => {
    const body = buildSaveBody([leg({ typed: true }), leg({ typed: false, contract_id: 5 })], '')
    expect(body.legs[0]).toEqual({ contract_id: 2381960, action: 'SELL', quantity: 130, planned_entry: '101.25',
      captured_at: '2026-10-14T15:25:00+05:30', entry_source: 'typed' })
    expect(Object.keys(body.legs[1])).not.toContain('entry_source')
  })
  it('AC-4: the mark needs the pair: a typed leg with no entry sends no entry_source', () => {
    expect(Object.keys(buildSaveBody([leg({ typed: true, planned_entry: null, captured_at: null })], '').legs[0]).sort()).toEqual(['action', 'contract_id', 'quantity'])
  })
  it('AC-4/AC-7: reopening a saved typed leg shows it typed with the saved price; a captured one is not typed', () => {
    const [t] = legsFromSaved(saved({ entry_source: 'typed' }), [contract])
    expect(t).toMatchObject({ typed: true, planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
    expect(legsFromSaved(saved({ entry_source: 'captured' }), [contract])[0].typed).toBe(false)
    expect(legsFromSaved(saved(), [contract])[0].typed).toBe(false)
  })
})

describe('legsFromSaved', () => {
  it('rebuilds every field exactly as stored; entry and capture time are not re-captured', () => {
    const [l] = legsFromSaved(saved(), [contract])
    expect(l).toMatchObject({ instrument_id: 'NSE_FO:44624', contract_id: 2381960, action: 'SELL', lots: 2, strike: '22800.00',
      expiry: '2026-10-19', instrument_type: 'CE', planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
  })
  it('a leg saved before ADR-075 reopens without an entry and is flagged for a reprice', () => {
    const [l] = legsFromSaved(saved({ planned_entry: undefined, captured_at: undefined }), [contract])
    expect(l.planned_entry).toBeNull()
    expect(l.captured_at).toBeNull()
    expect(l.reason_code).toBe('needs_reprice')
  })
  it('fails closed: contract missing, token mismatch or not whole lots gives null', () => {
    expect(legsFromSaved(saved(), [])).toBeNull()
    expect(legsFromSaved(saved(), [{ ...contract, exchange_token: 1 }])).toBeNull()
    expect(legsFromSaved(saved({ quantity: 100 }), [contract])).toBeNull()
  })
})

// Issue #500: a saved leg whose stored contract is no longer live comes back with its state and no segment/token. It is
// shown with that reason and never priced: no instrument id, and buildDraft sends no outcome request for the strategy.
describe('a saved leg that is no longer live (issue #500)', () => {
  const NOT_LIVE = ['token_reassigned', 'contract_retired', 'contract_delisted', 'contract_missing']
  for (const state of NOT_LIVE) {
    it(`${state}: the leg has no instrument id, carries its reason, and no outcome request is built`, () => {
      const def = saved({ contract_state: state, exchange_segment: null, exchange_token: null })
      const legs = legsFromSaved(def, [contract]) // even with the same token live in the catalogue answer
      expect(legs).toHaveLength(1)
      expect(legs[0]).toMatchObject({ instrument_id: null, not_live: true, reason_code: state, planned_entry: null,
        strike: '22800', expiry: '2026-10-19' })
      expect(JSON.stringify(legs)).not.toContain('44624')
      expect(buildDraft([...legs, leg()])).toBeNull()
    })
  }
  it('a not-live state that still carries a key, or a leg with no state, is refused (fails closed)', () => {
    expect(legsFromSaved(saved({ contract_state: 'token_reassigned' }), [contract])).toBeNull()
    expect(legsFromSaved(saved({ contract_state: undefined }), [contract])).toBeNull()
  })
  it('a live leg still builds its own key', () => {
    expect(legsFromSaved(saved(), [contract])[0].instrument_id).toBe('NSE_FO:44624')
  })
})

describe('W-148 (REQ-076 AC-7): the tick is never saved', () => {
  it('AC-7: an unticked leg, a Hedge mark and a base-lots count leave the saved body exactly as before', () => {
    const body = buildSaveBody([leg({ included: false, hedge: true, base_lots: 1 })], '')
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'captured_at', 'contract_id', 'planned_entry', 'quantity'])
    const text = JSON.stringify(body)
    for (const word of ['included', 'hedge', 'base_lots']) expect(text).not.toContain(word)
  })
  it('AC-7: an unticked leg is still saved as a leg (the tick does not drop it from the strategy)', () => {
    expect(buildSaveBody([leg(), leg({ included: false })], '').legs).toHaveLength(2)
  })
  it('a leg whose contract the server changed (no contract_id) cannot be saved with a stale one', () => {
    expect(canSaveLegs([leg({ contract_id: null, lot_size: null })])).toBe(false)
  })
})

describe('W-148 (REQ-076 AC-2): a stepped leg is a new contract and stays savable', () => {
  const stepReply = (over = {}) => ({ legs: [{ instrument_id: 'NSE_FO:44625', contract_id: 2381961, lot_size: 65, action: 'SELL', instrument: 'CE',
    strike: '22850.00', expiry: '2026-10-19', lots: 2, base_lots: 2, planned_entry: '88.00', captured_at: '2026-10-14T15:26:00+05:30',
    included: true, hedge: false, price_source: 'captured', ...over }] })
  it('AC-2: step then Save Draft posts the NEW contract id and the new entry, never the old contract', () => {
    const [stepped] = applyEditReply([leg()], stepReply())
    expect(canSaveLegs([stepped])).toBe(true)
    expect(buildSaveBody([stepped], '').legs[0]).toEqual({ contract_id: 2381961, action: 'SELL', quantity: 130, planned_entry: '88.00',
      captured_at: '2026-10-14T15:26:00+05:30' })
    expect(JSON.stringify(buildSaveBody([stepped], ''))).not.toContain('2381960')
  })
  it('AC-2: a reply that names no contract id leaves the leg unsavable, not saved with the old one', () => {
    const [stepped] = applyEditReply([leg()], stepReply({ contract_id: null }))
    expect(canSaveLegs([stepped])).toBe(false)
  })
})

// The REAL reply bodies of part 29b (tests_app/test_strategy_name_app.py: quoted(name) = '"' + name + '"'; the list row of
// test_ac4_the_list_carries_underlying_first_leg_leg_count_and_the_tracked_state: four-leg condor, first leg 22800 CE 2026-10-13).
const quoted = (name) => `"${name}"`
const LIST_ROW = (id, name, over = {}) => ({ id, underlying: 'NIFTY', status: 'draft', created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
  name: quoted(name), leg_count: 4, first_leg: { instrument: 'CE', strike: '22800.00', expiry: '2026-10-13' }, tracked: false, ...over })
const STRATEGY_OUT = (id, name, revision) => ({ id, name: quoted(name), status: 'draft', revision, created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
  definition: { underlying: 'NIFTY', legs: [] }, versions: [] })

describe('REQ-134: the name as the API sends it (quoted user words, ADR-003)', () => {
  it('plainName strips exactly one outer pair of double quotes, keeps inner quote marks, and shows anything else as received', () => {
    expect(plainName(quoted('NIFTY Oct condor'))).toBe('NIFTY Oct condor')
    expect(plainName(quoted('say "hi"'))).toBe('say "hi"') // a name that itself contains quote marks
    expect(plainName(quoted('"x"'))).toBe('"x"') // the name "x" with its own quotes: only the API's pair goes
    expect(plainName('NIFTY Oct condor')).toBe('NIFTY Oct condor') // not wrapped: as received
    expect(plainName('"half')).toBe('"half')
    expect(plainName('""')).toBe('""') // nothing inside the pair: as received, never guessed
    expect(plainName('"')).toBe('"')
    expect(plainName(undefined)).toBeNull()
    expect(plainName(7)).toBeNull()
  })
  it('strategyLabel shows the name, and the old text when the server (older) sent none', () => {
    expect(strategyLabel(LIST_ROW(7, 'Condor wider'), 'Draft 7')).toBe('Condor wider')
    expect(strategyLabel({ id: 7 }, 'Draft 7')).toBe('Draft 7')
  })
  it('buildSaveBody carries the typed name as typed; buildUpdateBody carries the revision and never a name', () => {
    expect(buildSaveBody([leg()], '', 'Condor wider').name).toBe('Condor wider')
    expect(Object.keys(buildSaveBody([leg()], ''))).not.toContain('name')
    const put = buildUpdateBody([leg()], 'tag', 3)
    expect(put.expected_revision).toBe(3)
    expect(Object.keys(put)).not.toContain('name')
    expect(put.legs).toEqual(buildSaveBody([leg()], 'tag').legs)
  })
  it('legsLine writes the first leg and "and N more" from the list row (screen 117); a one-leg strategy has no "and"', () => {
    expect(legsLine(LIST_ROW(7, 'x'))).toBe('NIFTY 13 Oct 22800 CE and 3 more')
    expect(legsLine(LIST_ROW(7, 'x', { leg_count: 1 }))).toBe('NIFTY 13 Oct 22800 CE')
    expect(legsLine({ id: 7, underlying: 'NIFTY' })).toBeNull() // an older server
    expect(legsLine(LIST_ROW(7, 'x', { first_leg: { instrument: 'CE', strike: null, expiry: '2026-10-13' } }))).toBe('Contract details not available')
  })
  it('trackedText: true, false, unknown (null) and absent are four different answers', () => {
    expect([true, false, null, undefined].map(trackedText)).toEqual(['Tracked', 'Not tracked', 'Tracking not known', null])
  })
  it('searchStrategies is case-insensitive on the shown name; an unmatched text keeps nothing; no-match text names the typed text', () => {
    const rows = [LIST_ROW(1, 'NIFTY Oct CONDOR'), LIST_ROW(2, 'Straddle')]
    expect(searchStrategies(rows, 'condor').map((r) => r.id)).toEqual([1])
    expect(searchStrategies(rows, 'STRAD').map((r) => r.id)).toEqual([2])
    expect(searchStrategies(rows, '').map((r) => r.id)).toEqual([1, 2])
    expect(searchStrategies(rows, 'zzz')).toEqual([])
    expect(searchStrategies(rows, '"')).toEqual([]) // the quote marks the API adds are not part of the name
    expect(noMatchText('zzz')).toBe('No saved strategy matches zzz')
  })
  it('fetchSavedDraft returns the name the saved read carried (raw, quoted) and null when an older server sent none', async () => {
    const def = { underlying: 'NIFTY', legs: [{ contract_id: 2381960, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 44624, action: 'SELL',
      instrument: 'CE', strike: '22800', expiry: '2026-10-19', quantity: 130, planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' }] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-19'] = { contracts: [contract] }
    answers['GET /strategies/7'] = { ...STRATEGY_OUT(7, 'Condor wider', 3), definition: def }
    const client = (await import('@/services/api')).default
    expect(await fetchSavedDraft(client, 7)).toMatchObject({ revision: 3, name: quoted('Condor wider') })
    answers['GET /strategies/7'] = { revision: 3, definition: def }
    expect((await fetchSavedDraft(client, 7)).name).toBeNull()
  })
})

// The refusal and conflict texts are the catalogue's (backend/ofo/errors/templates.py strategy_name_empty, strategy_revision_conflict).
const EMPTY_NAME = { what_happened: 'Give the strategy a name', impact: 'The strategy was not saved or renamed.',
  what_is_blocked: 'Saving or renaming this strategy.', next_action: 'Type a name of 1 to 20 characters, then save again.' }
const CONFLICT = { what_happened: 'This strategy was changed by another action after you opened it.', impact: 'The draft was not saved or changed.',
  what_is_blocked: 'Applying your change to the newer version.', next_action: 'Reload the strategy and make the change again.' }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const LEGS = [leg()]
async function bar(props = {}) {
  answers['GET /strategies'] = { strategies: [] }
  const w = mount(SaveDraftBar, { props: { legs: LEGS, rulesRef: '', current: null, ...props } })
  await flushPromises()
  calls.length = 0
  return w
}

describe('REQ-134 AC-1: the first Save of a never-saved strategy asks for a name', () => {
  it('Save opens the name field prefilled "New Strategy" with the 12/20 hint and sends nothing yet', async () => {
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    expect(t(w, 'name-input').element.value).toBe(STRATEGY_NAME_DEFAULT)
    expect(t(w, 'name-input').attributes('maxlength')).toBe('20')
    expect(t(w, 'name-count').text()).toBe('12/20 characters')
    expect(calls).toEqual([])
  })
  it('confirming POSTs the typed name; the saved name is shown without its quotes and the page is told id, revision and name', async () => {
    answers['POST /strategies'] = STRATEGY_OUT(7, 'NIFTY Oct condor', 1)
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-input').setValue('NIFTY Oct condor')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.body.name)).toEqual(['NIFTY Oct condor'])
    expect(t(w, 'save-status').text()).toBe('NIFTY Oct condor saved.')
    expect(t(w, 'save-status').attributes('data-saved-id')).toBe('7')
    expect(w.emitted('saved')).toEqual([[7, 1, quoted('NIFTY Oct condor')]])
    expect(t(w, 'name-form').exists()).toBe(false)
  })
  it('an empty name is sent as typed and the API refusal "Give the strategy a name" is shown; nothing is saved and the field stays', async () => {
    answers['POST /strategies'] = () => Promise.reject({ status: 422, parts: EMPTY_NAME })
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-input').setValue('')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(t(w, 'save-error-what').text()).toBe('Give the strategy a name')
    expect(w.emitted('saved')).toBeUndefined()
    expect(t(w, 'name-form').exists()).toBe(true)
  })
  it('Cancel sends nothing and saves nothing', async () => {
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-cancel').trigger('click')
    expect(t(w, 'name-form').exists()).toBe(false)
    expect(calls).toEqual([])
  })
  it('a markup name is shown as text (no element is made from it)', async () => {
    const markup = '<b>bold</b>'
    answers['POST /strategies'] = STRATEGY_OUT(7, markup, 1)
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-input').setValue(markup)
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(t(w, 'save-status').text()).toBe(`${markup} saved.`)
    expect(t(w, 'save-status').find('b').exists()).toBe(false)
  })
})

describe('REQ-134 AC-2 (attack 1): Save on a saved strategy updates it with the loaded revision and asks nothing', () => {
  const current = { id: 7, revision: 3, name: quoted('NIFTY Oct condor') }
  it('Save sends PUT /strategies/7 with expected_revision 3, no name field, no POST', async () => {
    answers['PUT /strategies/7'] = STRATEGY_OUT(7, 'NIFTY Oct condor', 4)
    const w = await bar({ current })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(t(w, 'name-form').exists()).toBe(false)
    expect(calls.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.url}`)).toEqual(['PUT /strategies/7'])
    const put = calls.find((c) => c.method === 'PUT') // the Undo check reads the history first (row 28f), so the PUT is not calls[0]
    expect(put.body.expected_revision).toBe(3)
    expect(Object.keys(put.body)).not.toContain('name')
    expect(w.emitted('saved')).toEqual([[7, 4, quoted('NIFTY Oct condor')]])
  })
  it('a stale revision (409) shows the conflict message, emits nothing and the legs stay as given', async () => {
    answers['PUT /strategies/7'] = () => Promise.reject({ status: 409, parts: CONFLICT })
    const w = await bar({ current })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(t(w, 'save-error-what').text()).toBe(CONFLICT.what_happened)
    expect(w.emitted('saved')).toBeUndefined()
    expect(w.props('legs')).toEqual(LEGS)
  })
  it('a request failure shows the neutral message and nothing is reported saved', async () => {
    answers['PUT /strategies/7'] = () => Promise.reject(new Error('down'))
    const w = await bar({ current })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(t(w, 'save-error').exists()).toBe(true)
    expect(w.emitted('saved')).toBeUndefined()
    expect(t(w, 'save-status').attributes('data-saved-id')).toBe('')
  })
  it('an answer without an id is refused (fail closed)', async () => {
    answers['PUT /strategies/7'] = { revision: 4 }
    const w = await bar({ current })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(w.emitted('saved')).toBeUndefined()
    expect(t(w, 'save-error').exists()).toBe(true)
  })
})

describe('REQ-134 AC-3: Rename from the builder (saved strategy only)', () => {
  const current = { id: 7, revision: 3, name: quoted('NIFTY Oct condor') }
  // the reply of part 29b's rename route (tests_app/test_strategy_name_app.py): id, quoted name, revision unchanged, updated_at
  const RENAMED = { id: 7, name: quoted('Condor wider'), revision: 3, updated_at: '2026-10-13T05:10:00Z' }
  it('attack 1+3: Rename PATCHes the loaded revision (no extra GET); the shown name comes from the reply, quotes stripped', async () => {
    answers['PATCH /strategies/7/name'] = RENAMED
    const w = await bar({ current })
    expect(t(w, 'current-name').exists()).toBe(false) // GC-UI 3a D-A22: the name is the legs card title (LegList), not repeated here
    await t(w, 'rename-open').trigger('click')
    expect(t(w, 'name-input').element.value).toBe('NIFTY Oct condor')
    await t(w, 'name-input').setValue(' Condor wider ')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    const sent = calls.filter((c) => c.method !== 'GET')
    expect(sent).toEqual([{ method: 'PATCH', url: '/strategies/7/name', body: { name: ' Condor wider ', expected_revision: 3 } }])
    expect(calls.filter((c) => c.method === 'GET' && c.url === '/strategies/7')).toEqual([])
    expect(w.emitted('renamed')).toEqual([[7, quoted('Condor wider')]])
    await w.setProps({ current: { ...current, name: w.emitted('renamed')[0][1] } }) // what the page does with the event
    expect(t(w, 'name-form').exists()).toBe(false)
  })
  it('attack 2: a never-saved strategy shows no Rename (Save asks the name instead)', async () => {
    const w = await bar({ current: null })
    expect(t(w, 'rename-open').exists()).toBe(false)
  })
  it('attack 4: an empty name shows the API refusal text and emits nothing', async () => {
    const EMPTY = { what_happened: 'Give the strategy a name', impact: 'The strategy was not saved or renamed.', what_is_blocked: 'Saving or renaming this strategy.', next_action: 'Type a name of 1 to 20 characters, then save again.' }
    answers['PATCH /strategies/7/name'] = () => Promise.reject({ status: 422, parts: EMPTY })
    const w = await bar({ current })
    await t(w, 'rename-open').trigger('click')
    await t(w, 'name-input').setValue('')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(t(w, 'save-error-what').text()).toBe(EMPTY.what_happened)
    expect(w.emitted('renamed')).toBeUndefined()
  })
  it('a reply without a name is refused (fail closed)', async () => {
    answers['PATCH /strategies/7/name'] = { id: 7, revision: 3 }
    const w = await bar({ current })
    await t(w, 'rename-open').trigger('click')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(w.emitted('renamed')).toBeUndefined()
    expect(t(w, 'save-error').exists()).toBe(true)
  })
})

describe('ADR-192: the Save As pre-fill is the cut original plus " copy", at most 20 characters', () => {
  it.each([
    ['Iron fly', 'Iron fly copy'], // 8
    ['123456789012345', '123456789012345 copy'], // 15 -> exactly 20
    ['1234567890123456', '123456789012345 copy'], // 16: one character cut
    ['NIFTY Oct condor', 'NIFTY Oct condo copy'], // the spec example
    ['x'.repeat(25), `${'x'.repeat(15)} copy`],
    ['x'.repeat(20), `${'x'.repeat(15)} copy`], // a full-length name
  ])('%s -> %s', (name, expected) => {
    const out = saveAsName(name)
    expect(out).toBe(expected)
    expect(out.length).toBeLessThanOrEqual(20)
  })
  it('a cut that ends in a space drops the space', () => {
    expect(saveAsName('abcdefghijklmn opq')).toBe('abcdefghijklmn copy') // cut at 15 leaves a trailing space
  })
  it('counts and cuts by characters (code points), never splitting a surrogate pair', () => {
    expect(saveAsName('NIFTY Oct cond🚀 more')).toBe('NIFTY Oct cond🚀 copy') // 15 characters kept, the emoji whole
    expect(saveAsName('Iron fly 🚀🚀🚀🚀🚀🚀')).toBe('Iron fly 🚀🚀🚀🚀🚀🚀 copy') // 15 characters: not cut
    expect(Array.from(saveAsName('NIFTY Oct cond🚀 more')).length).toBeLessThanOrEqual(20)
  })
  it('no name gives the default name plus the suffix', () => {
    expect(saveAsName(null)).toBe(`${STRATEGY_NAME_DEFAULT} copy`)
    expect(saveAsName(undefined)).toBe('New Strategy copy')
  })
})

describe('REQ-134 AC-2 (attack 2): Save As makes a copy, opens it and never sends the original', () => {
  const current = { id: 7, revision: 3, name: quoted('NIFTY Oct condor') }
  it('Save As prefills "<name> copy" without the API quotes', async () => {
    const w = await bar({ current })
    await t(w, 'save-as').trigger('click')
    expect(t(w, 'name-input').element.value).toBe('NIFTY Oct condo copy') // ADR-192: 20 characters, cut from the end
    expect(t(w, 'name-form').attributes('data-mode')).toBe('save-as')
  })
  it('confirming POSTs a NEW strategy with the typed name and the on-screen legs, then opens the copy; no request names id 7', async () => {
    answers['POST /strategies'] = STRATEGY_OUT(8, 'Condor wider', 1)
    const w = await bar({ current })
    await t(w, 'save-as').trigger('click')
    await t(w, 'name-input').setValue('Condor wider')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    const sent = calls.filter((c) => c.method !== 'GET')
    expect(sent.map((c) => `${c.method} ${c.url}`)).toEqual(['POST /strategies'])
    expect(sent[0].body.name).toBe('Condor wider')
    expect(sent[0].body.legs).toEqual(buildSaveBody(LEGS, '').legs)
    expect(calls.some((c) => c.url.includes('/7'))).toBe(false)
    expect(w.emitted('open')).toEqual([[LEGS, 8, 1, quoted('Condor wider')]])
    expect(w.emitted('saved')).toBeUndefined()
  })
  it('a refused Save As (empty name) leaves everything as it was: nothing opened', async () => {
    answers['POST /strategies'] = () => Promise.reject({ status: 422, parts: EMPTY_NAME })
    const w = await bar({ current })
    await t(w, 'save-as').trigger('click')
    await t(w, 'name-input').setValue('')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(w.emitted('open')).toBeUndefined()
    expect(t(w, 'save-error-what').text()).toBe('Give the strategy a name')
  })
})

describe('G-024: the "..." menu lists only the items that apply, never an empty menu', () => {
  const current = { id: 7, revision: 3, name: quoted('NIFTY Oct condor') }
  const items = (w) => w.findAll('[role="menuitem"]').map((b) => b.attributes('data-testid'))
  const FOUR = [leg({ id: 1 }), leg({ id: 2, contract_id: 11 }), leg({ id: 3, contract_id: 12 }), leg({ id: 4, contract_id: 13 })]
  it('attack 1: an empty builder has the button disabled and no menu item', async () => {
    const w = await bar({ legs: [] })
    expect(t(w, 'more-menu').attributes('disabled')).toBeDefined()
    expect(items(w)).toEqual([])
  })
  it('attack 2: an unsaved 4-leg strategy shows Save and Save As only; Save As asks the ADR-192 pre-fill and POSTs once', async () => {
    answers['POST /strategies'] = STRATEGY_OUT(9, 'Four legs', 1)
    const w = await bar({ legs: FOUR })
    expect(t(w, 'more-menu').attributes('disabled')).toBeUndefined()
    expect(items(w)).toEqual(['menu-save', 'save-as'])
    await t(w, 'more-menu').trigger('click')
    await t(w, 'save-as').trigger('click')
    expect(t(w, 'name-form').attributes('data-mode')).toBe('save-as')
    expect(t(w, 'name-input').element.value).toBe(saveAsName(undefined))
    await t(w, 'name-input').setValue('Four legs')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.url}`)).toEqual(['POST /strategies'])
    expect(w.emitted('open')[0].slice(1, 3)).toEqual([9, 1])
  })
  it('a saved strategy shows Save, Save As and Rename; menu Save sends the PUT with the loaded revision', async () => {
    answers['PUT /strategies/7'] = STRATEGY_OUT(7, 'NIFTY Oct condor', 4)
    const w = await bar({ legs: FOUR, current })
    expect(items(w)).toEqual(['menu-save', 'save-as', 'rename-open'])
    await t(w, 'menu-save').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.method === 'PUT').body.expected_revision).toBe(3)
  })
  it('attack 3: Save As on a saved strategy makes a NEW id; the original id is never written', async () => {
    answers['POST /strategies'] = STRATEGY_OUT(8, 'Copy', 1)
    const w = await bar({ legs: FOUR, current })
    await t(w, 'save-as').trigger('click')
    await t(w, 'name-input').setValue('Copy')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.url}`)).toEqual(['POST /strategies'])
    expect(w.emitted('open')[0].slice(1, 4)).toEqual([8, 1, quoted('Copy')])
  })
  it('attack 4: Rename sends only the name on the same id; empty and 21-character names are refused with the API text', async () => {
    const LONG = { what_happened: 'That name is too long', impact: 'The strategy was not saved or renamed.', what_is_blocked: 'Saving or renaming this strategy.', next_action: 'Type a name of 1 to 20 characters.' }
    answers['PATCH /strategies/7/name'] = (body) => (body.name.length > 20 || body.name === '' ? Promise.reject({ status: 422, parts: body.name === '' ? EMPTY_NAME : LONG }) : Promise.resolve({ data: { id: 7, name: quoted(body.name), revision: 3 } }))
    const w = await bar({ legs: FOUR, current })
    await t(w, 'rename-open').trigger('click')
    await t(w, 'name-input').setValue('')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(t(w, 'save-error-what').text()).toBe('Give the strategy a name')
    await t(w, 'name-input').setValue('x'.repeat(21))
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(t(w, 'save-error-what').text()).toBe(LONG.what_happened)
    expect(w.emitted('renamed')).toBeUndefined()
    await t(w, 'name-input').setValue('Renamed')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(w.emitted('renamed')).toEqual([[7, quoted('Renamed')]])
    expect(calls.filter((c) => c.method === 'POST' || c.method === 'PUT')).toEqual([])
  })
  it('attack 5: Escape closes the menu and choosing an item closes it', async () => {
    const w = mount(SaveDraftBar, { props: { legs: FOUR, current }, attachTo: document.body })
    await flushPromises()
    await t(w, 'more-menu').trigger('click')
    expect(t(w, 'more-menu-panel').isVisible()).toBe(true)
    await t(w, 'more-menu-panel').trigger('keydown', { key: 'Escape' })
    expect(t(w, 'more-menu-panel').isVisible()).toBe(false)
    await t(w, 'more-menu').trigger('click')
    await t(w, 'rename-open').trigger('click')
    expect(t(w, 'more-menu-panel').isVisible()).toBe(false)
    w.unmount()
  })
})

describe('REQ-134: the saved list in the bar shows the name, and the old text when the server sent none', () => {
  it('a named row shows its name without quotes (as text); a row with no name shows "Draft <id>"', async () => {
    answers['GET /strategies'] = { strategies: [LIST_ROW(7, '<i>Condor</i>'), { id: 9, underlying: 'NIFTY', status: 'draft', updated_at: '2026-10-13T05:10:00Z' }] }
    const w = mount(SaveDraftBar, { props: { legs: LEGS } })
    await flushPromises()
    const names = w.findAll('[data-testid="saved-draft-name"]')
    const texts = names.map((n) => n.text())
    expect([...texts].sort()).toEqual(['<i>Condor</i>', 'Draft 9'].sort())
    const condor = names.find((n) => n.text().startsWith('<i>Condor</i>'))
    expect(condor.find('i').exists()).toBe(false)
  })
})

describe('GC-BM F-13: the "..." menu item shows by its own condition, never disables the whole menu', () => {
  const current = { id: 35, revision: 2, name: quoted('NIFTY Oct condor') }
  const NOT_LIVE = [leg({ lot_size: null })] // the saveDraft.js:129 shape of a leg that is not live
  const slotMenu = { slots: { menu: '<button role="menuitem" data-testid="menu-activity">History</button>' } }
  async function barWith(props, options = {}) {
    answers['GET /strategies'] = { strategies: [] }
    const w = mount(SaveDraftBar, { props: { rulesRef: '', ...props }, ...options })
    await flushPromises()
    return w
  }
  it('attack 1: a saved strategy with a not-live leg keeps the menu: Rename and History listed, Save / Save As hidden', async () => {
    const w = await barWith({ legs: NOT_LIVE, current }, slotMenu)
    expect(t(w, 'more-menu').attributes('disabled')).toBeUndefined()
    await t(w, 'more-menu').trigger('click')
    expect(t(w, 'rename-open').exists()).toBe(true)
    expect(t(w, 'menu-activity').exists()).toBe(true)
    expect(t(w, 'menu-save').exists()).toBe(false)
    expect(t(w, 'save-as').exists()).toBe(false)
  })
  it('attack 2: no legs and no saved strategy: the button is disabled and no menu item exists', async () => {
    const w = await barWith({ legs: [], current: null })
    expect(t(w, 'more-menu').attributes('disabled')).toBeDefined()
    expect(['rename-open', 'menu-save', 'save-as'].filter((id) => t(w, id).exists())).toEqual([])
  })
  it('an unsaved strategy with live legs still lists Save and Save As but no Rename', async () => {
    const w = await barWith({ legs: LEGS, current: null })
    expect(t(w, 'more-menu').attributes('disabled')).toBeUndefined()
    expect(t(w, 'menu-save').exists() && t(w, 'save-as').exists()).toBe(true)
    expect(t(w, 'rename-open').exists()).toBe(false)
  })
})
