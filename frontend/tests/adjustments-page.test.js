// GC-ADJ2 step 3 (REQ-160 AC-1..AC-4): the playbook editor page. Answers have the shapes of the playbook routes
// (PlaybookListOut, PlaybookFullOut, TestOut, the catalogue refusal message); the body is the iron condor system body's
// own shape (docs/design/playbook-body-v1.md), cut to the fields the assertions read. Every expected sentence is the
// answer's own text; nothing here computes a figure.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routeLocationKey } from 'vue-router'
// the REAL answer of GET /api/playbooks/labels (written from the route by its app test's module, round 2)
import LABELS from './fixtures/playbook-labels.json'

const answers = {}
const calls = []
const refusal = (what) => ({ message: 'refused', status: 409, parts: { what_happened: what, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[`${method} ${url}`]
    if (a instanceof Error || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: typeof a === 'function' ? a(payload) : a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), delete: reply('DELETE') } }
})
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'
import { EXPIRY_KINDS, STEPS, labelMaps, summaryLines } from '@/lib/playbookEditor'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const BODY = {
  schema: 1, strategy_type: 'ic', status: 'approved',
  stages: { weekly: [{ name: 'Early', from: 5, to: null }, { name: 'Middle', from: 2, to: 4 }, { name: 'Last day', from: 0, to: 1 }],
    monthly: [{ name: 'Early', from: 10, to: null }, { name: 'Middle', from: 3, to: 9 }, { name: 'Last 2 days', from: 0, to: 2 }] },
  triggers: {
    'T-01': { on: true, label: 'Spot within this % of a short strike', unit: '%', cmp: 'le', data: 'ok', weekly: ['0.75', '0.5', '0.3'], monthly: ['1.5', '1.0', '0.5'] },
    'T-03': { on: true, label: 'Short delta at or above', unit: '', cmp: 'ge', data: 'ok', weekly: ['0.3', '0.35', '0.4'], monthly: ['0.3', '0.35', '0.4'] },
    'T-20b': { on: false, greyed: 'Needs price history (not in V1)', label: 'IV percentile', unit: '%', cmp: 'ge', data: 'hist', weekly: ['', '', ''], monthly: ['', '', ''] },
  },
  rules: [{ id: 'T-01', any_of: ['T-01'] }, { id: 'T-03', any_of: ['T-03'] }],
  tightened: ['T-01'],
  day_rules: [{ on: true, when: 'beforeWeekend', at: '15:00', action: 0 }],
  situations: [{ id: 'S-01', name: 'Gap at the open', rule: 'Wait until 09:30 before suggesting' }],
  guards: { profit_target_pct_of_max_profit: '50', stop_line_pct_of_max_loss: '50', max_adjustments: 2 },
  approaches: { applicable: ['A-01'], off_in_playbook: ['A-03'], greyed: [{ id: 'A-09', reason: 'Loss already capped' }] },
}
const row = (over) => ({ id: 1, name: 'Iron condor: system', type: 'ic', type_name: 'Iron condor', is_system: true, status: 'approved', draft: false, active: true, version: 1, updated_at: '2026-10-31T09:00:00+05:30', ...over })
const SYSTEM = row({})
const OWN = row({ id: 7, name: '"IC mine"', is_system: false, status: null, active: false, version: 3 })
const DRAFT_STRANGLE = row({ id: 2, name: 'Short strangle: system', type: 'strangle', type_name: 'Short strangle', status: 'draft', draft: true })
const PAST = 'Testing against past expiries is not in this version: it needs licensed historical option data.'

function setUp(list = [SYSTEM, OWN]) {
  answers['GET /playbooks/labels'] = LABELS
  answers['GET /playbooks/types'] = { types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] }
  answers['GET /playbooks'] = { playbooks: list }
  for (const p of list) answers[`GET /playbooks/${p.id}`] = { ...p, body: JSON.parse(JSON.stringify(BODY)) }
}
async function open(id = null, query = {}) {
  const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query } } } })
  await flushPromises()
  if (id != null) { await w.get('[data-testid=pb-pick]').setValue(id); await flushPromises() }
  return w
}

beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 })

describe('playbook editor (REQ-160)', () => {
  it('AC-1: seven steps in order, and a summary beside them', async () => {
    setUp()
    const w = await open()
    expect(w.findAll('[data-testid=pb-steps] button').map((b) => b.text().replace(/^\d+\s*/, ''))).toEqual(
      ['Expiry and stages', 'When to look', 'Approaches to show', 'Days and dates', 'Situations', 'Limits and guards', 'Test on my strategies'])
    expect(w.get('[data-testid=pb-sum-type]').text()).toBe('Iron condor, weekly expiry. Stages: Early (5+ days left), Middle (2-4 days left), Last day (0-1 days left).')
  })

  it('AC-2: the active (system) playbook opens with every value filled in; the own one too', async () => {
    setUp()
    const w = await open()
    await w.get('[data-testid=pb-step-when]').trigger('click')
    expect(w.get('[data-testid=pb-value-T-01-1]').element.value).toBe('0.5')
    expect(w.get('[data-testid=pb-trigger-T-20b]').text()).toContain('Needs price history (not in V1)')
    await w.get('[data-testid=pb-pick] option[value="7"]').setSelected()
    await flushPromises()
    expect(calls.some(([m, u]) => m === 'GET' && u === '/playbooks/7')).toBe(true)
    expect(w.get('[data-testid=pb-owner]').text()).toBe('Yours')
  })

  it('attack 2: Save changes is not offered on a system playbook; on the own one a refusal is shown verbatim', async () => {
    setUp()
    const w = await open()
    expect(w.find('[data-testid=pb-save]').exists()).toBe(false)
    expect(w.find('[data-testid=pb-delete]').exists()).toBe(false)
    await w.get('[data-testid=pb-pick] option[value="7"]').setSelected()
    await flushPromises()
    answers['PUT /playbooks/7'] = refusal('This playbook was changed elsewhere since you opened it.')
    await w.get('[data-testid=pb-step-when]').trigger('click')
    await w.get('[data-testid=pb-value-T-01-1]').setValue('0.4')
    await w.get('[data-testid=pb-save]').trigger('click')
    await flushPromises()
    expect(calls.find(([m]) => m === 'PUT')[2]).toMatchObject({ version: 3 })
    expect(w.get('[data-testid=pb-refusal]').text()).toBe('This playbook was changed elsewhere since you opened it.')
  })

  it('attack 4: Draft shows only on a draft system playbook', async () => {
    setUp([DRAFT_STRANGLE])
    let w = await open()
    expect(w.get('[data-testid=pb-draft]').text()).toBe('Draft')
    setUp([SYSTEM, OWN])
    w = await open()
    expect(w.find('[data-testid=pb-draft]').exists()).toBe(false)
    await w.get('[data-testid=pb-pick] option[value="7"]').setSelected()
    await flushPromises()
    expect(w.find('[data-testid=pb-draft]').exists()).toBe(false)
  })

  it('attack 5: a duplicate name on Save as new shows the server sentence verbatim', async () => {
    setUp()
    answers['POST /playbooks'] = refusal('A playbook named "IC mine" already exists for Iron condor.')
    const w = await open()
    await w.get('[data-testid=pb-new-name]').setValue('IC mine')
    await w.get('[data-testid=pb-save-as]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=pb-refusal]').text()).toBe('A playbook named "IC mine" already exists for Iron condor.')
  })

  it('attack 3: T-01 Middle to 0.3 changes the summary and is what Test sends, before any save', async () => {
    setUp()
    answers['POST /playbooks/test'] = { type: 'ic', type_name: 'Iron condor', none_text: null, past_note: PAST, strategies: [{
      strategy_id: 72, name: '"Iron condor 3 Nov"', stage: { name: 'Middle', index: 1 }, withheld: null, results: [
        { kind: 'flag', rule_id: 'T-03', trigger_id: 'T-03', cmp: 'ge', value: '0.41037', threshold: '0.35', reason: null, wording: null },
        { kind: 'not_checked', rule_id: 'T-16', trigger_id: 'T-16', cmp: null, value: null, threshold: null,
          reason: { what_happened: 'Zerodha has not stated the margin.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }, wording: null }] }] }
    const w = await open()
    const before = w.get('[data-testid=pb-sum-looks]').text()
    await w.get('[data-testid=pb-step-when]').trigger('click')
    await w.get('[data-testid=pb-value-T-01-1]').setValue('0.3')
    expect(w.get('[data-testid=pb-dirty]').text()).toBe('Unsaved changes')
    expect(before).toContain('Spot within this % of a short strike: 0.75 / 0.5 / 0.3 %')
    expect(w.get('[data-testid=pb-sum-looks]').text()).toContain('Spot within this % of a short strike: 0.75 / 0.3 / 0.3 %')
    await w.get('[data-testid=pb-step-test]').trigger('click')
    await w.get('[data-testid=pb-run-test]').trigger('click')
    await flushPromises()
    const sent = calls.find(([m, u]) => m === 'POST' && u === '/playbooks/test')[2]
    expect(sent.type).toBe('ic')
    expect(sent.body.triggers['T-01'].weekly[1]).toBe('0.3')
    expect(calls.some(([m]) => m === 'PUT')).toBe(false)
    expect(w.get('[data-testid=pb-test-row-T-03-T-03]').text()).toBe('Would flagShort delta at or above0.410370.35')
    expect(w.get('[data-testid=pb-test-row-T-16-T-16]').text()).toBe('Not checkedT-16Zerodha has not stated the margin.')
    expect(w.get('[data-testid=pb-test-72]').text()).toContain('"Iron condor 3 Nov" - Middle')
    expect(w.get('[data-testid=pb-past-note]').text()).toBe(PAST)
  })

  it('AC-3: no strategy of the type shows the server sentence; an invalid body shows its refusal', async () => {
    setUp()
    answers['POST /playbooks/test'] = { type: 'ic', type_name: 'Iron condor', none_text: 'No current Iron condor strategy to test against', past_note: PAST, strategies: [] }
    const w = await open()
    await w.get('[data-testid=pb-step-test]').trigger('click')
    await w.get('[data-testid=pb-run-test]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=pb-test-none]').text()).toBe('No current Iron condor strategy to test against')
    answers['POST /playbooks/test'] = refusal('Days 2 to 4 are in both Last and Near (weekly expiries).')
    await w.get('[data-testid=pb-run-test]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=pb-test-refusal]').text()).toBe('Days 2 to 4 are in both Last and Near (weekly expiries).')
  })

  it('a failed read shows the refusal and does not open the editor; an empty list says so', async () => {
    setUp()
    answers['GET /playbooks/1'] = refusal('The playbook was not found.')
    let w = await open()
    expect(w.get('[data-testid=pb-refusal]').text()).toBe('The playbook was not found.')
    expect(w.find('[data-testid=pb-steps]').exists()).toBe(false)
    setUp([])
    w = await open()
    expect(w.find('[data-testid=pb-list-empty]').exists()).toBe(true)
  })

  it('deleting the active own playbook shows the server sentence', async () => {
    setUp([{ ...SYSTEM, active: false }, { ...OWN, active: true }])
    answers['DELETE /playbooks/7'] = { deleted: true, active_now_system: true, message: 'Iron condor: the system playbook is active again' }
    const w = await open()
    await w.get('[data-testid=pb-delete]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=pb-notice]').text()).toBe('Iron condor: the system playbook is active again')
  })

  it('round 2: approach names and day rule words come from the labels answer, not ids or numbers', async () => {
    setUp()
    const w = await open()
    await w.get('[data-testid=pb-step-show]').trigger('click')
    const shown = w.get('[data-testid=pb-body]').text()
    expect(shown).toContain('Roll the untested spread toward spot')
    expect(shown).toContain(LABELS.approaches.find((a) => a.key === 'A-09').text)
    expect(shown).not.toMatch(/A-01|A-09/)
    await w.get('[data-testid=pb-step-days]').trigger('click')
    expect(w.get('[data-testid=pb-body]').text()).toContain('The last session before a weekend')
    expect(w.get('[data-testid=pb-body]').text()).toContain('Run the carry check (overnight margin, gap loss)')
    expect(w.get('[data-testid=pb-sum-days]').text()).toBe('Day rules:The last session before a weekend at 15:00: Run the carry check (overnight margin, gap loss)')
    await w.get('[data-testid=pb-step-test]').trigger('click')
    expect(w.get('[data-testid=pb-past-note]').text()).toBe(PAST)
  })

  it('round 2: no labels answer -> no summary sentence typed by the browser', async () => {
    setUp()
    answers['GET /playbooks/labels'] = { message: 'down', status: 503, parts: { what_happened: 'The labels could not be read.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }
    const w = await open()
    expect(w.find('[data-testid=pb-sum-type]').exists()).toBe(false)
  })

  it('round 2: ?playbook=<id> (the plan sheet link) opens that playbook', async () => {
    setUp()
    const w = await open(null, { playbook: '7' })
    expect(calls.some(([m, u]) => m === 'GET' && u === '/playbooks/7')).toBe(true)
    expect(w.get('[data-testid=pb-owner]').text()).toBe('Yours')
    expect(w.get('[data-testid=pb-pick]').element.value).toBe('7')
  })

  it('the summary plan line reads the guards of the body', () => {
    const lines = summaryLines(BODY, 'Iron condor', 'monthly', labelMaps(LABELS))
    expect(lines.find((l) => l.key === 'plan').text).toBe('Plan: target 50% of max profit, stop at 50% of max loss, at most 2 adjustments.')
  })
})

// GC-ADJ2 step 3 round 3 (owner's browser, 15:40 IST): every REAL system body, read from the shipped file at test time
// (backend/ofo/adjustment/system_playbooks.json), never typed here. T-02, T-18, T-20, T-20b and T-21 carry a null value
// list for both expiry kinds in all 12, which crashed step 2 and left every later handler dead.
const SYSTEM_FILE = resolve(process.cwd(), '../backend/ofo/adjustment/system_playbooks.json') // vitest runs in frontend/
const realEntries = () => JSON.parse(readFileSync(SYSTEM_FILE, 'utf-8')).playbooks
const NULL_LISTS = ['T-02', 'T-18', 'T-20', 'T-20b', 'T-21']
const NO_VALUES = LABELS.no_values.what_happened
const GUARD_WORDS = Object.fromEntries(LABELS.guards.map((g) => [g.key, g.text]))
const reset = () => { for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 }

function setUpReal(entry, id = 1) {
  const pb = row({ id, name: entry.name, type: entry.strategy_type, is_system: true, active: true })
  answers['GET /playbooks/labels'] = LABELS
  answers['GET /playbooks/types'] = { types: [{ key: entry.strategy_type, name: entry.name, active_id: id, has_system: true }] }
  answers['GET /playbooks'] = { playbooks: [pb] }
  answers[`GET /playbooks/${id}`] = { ...pb, body: JSON.parse(JSON.stringify(entry.body)) }
  answers['POST /playbooks/test'] = { type: entry.strategy_type, type_name: entry.name, none_text: 'No current strategy to test against', past_note: PAST, strategies: [] }
}
async function openCaught() {
  const errors = []
  const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query: {} } },
    config: { errorHandler: (err) => { errors.push(err) } } } })
  await flushPromises()
  return { w, errors }
}
const icEntry = () => realEntries().find((e) => e.strategy_type === 'ic')

describe('playbook editor on the 12 real system bodies (round 3)', () => {
  it('the shipped file holds 12 bodies, and the null lists the browser crashed on are really there', () => {
    const entries = realEntries()
    expect(entries).toHaveLength(12)
    expect(icEntry()).toBeTruthy()
    for (const e of entries) for (const id of NULL_LISTS) {
      expect(e.body.triggers[id].weekly).toBeNull()
      expect(e.body.triggers[id].monthly).toBeNull()
    }
  })

  it('attack 3 + 2: every body x every step x both expiry kinds renders with zero Vue errors; Test then posts', async () => {
    for (const entry of realEntries()) {
      reset()
      setUpReal(entry)
      const { w, errors } = await openCaught()
      expect(w.find('[data-testid=pb-body]').exists(), entry.strategy_type).toBe(true)
      for (const [step] of STEPS) {
        await w.get(`[data-testid=pb-step-${step}]`).trigger('click')
        for (const [kind] of EXPIRY_KINDS) {
          await w.get(`[data-testid=pb-kind-${kind}]`).trigger('click')
          expect(w.get('[data-testid=pb-body]').text().length, `${entry.strategy_type} ${step} ${kind}`).toBeGreaterThan(0)
        }
      }
      expect(errors, entry.strategy_type).toEqual([])
      await w.get('[data-testid=pb-run-test]').trigger('click')
      await flushPromises()
      const sent = calls.filter(([m, u]) => m === 'POST' && u === '/playbooks/test')
      expect(sent, entry.strategy_type).toHaveLength(1)
      expect(sent[0][2].type).toBe(entry.strategy_type)
      expect(w.get('[data-testid=pb-test-none]').text()).toBe('No current strategy to test against')
      w.unmount()
    }
  })

  it('attack 1: iron condor step 2 shows the five null-list triggers as no value, with no input', async () => {
    setUpReal(icEntry())
    const { w, errors } = await openCaught()
    await w.get('[data-testid=pb-step-when]').trigger('click')
    for (const [kind] of EXPIRY_KINDS) {
      await w.get(`[data-testid=pb-kind-${kind}]`).trigger('click')
      for (const id of NULL_LISTS) {
        const r = w.get(`[data-testid=pb-trigger-${id}]`)
        expect(r.get(`[data-testid=pb-novalue-${id}]`).text()).toBe(NO_VALUES)
        expect(r.find(`[data-testid^=pb-value-${id}-]`).exists()).toBe(false)
      }
      expect(w.get('[data-testid=pb-value-T-01-1]').element.value).toBe(icEntry().body.triggers['T-01'][kind][1])
    }
    expect(errors).toEqual([])
  })

  it('attack 4: step 6 shows words for every guard key in every real body, never the raw key', async () => {
    const seen = new Set()
    for (const entry of realEntries()) {
      reset()
      setUpReal(entry)
      const { w } = await openCaught()
      await w.get('[data-testid=pb-step-limits]').trigger('click')
      for (const key of Object.keys(entry.body.guards)) {
        seen.add(key)
        expect(GUARD_WORDS[key], `no label for guard ${key}`).toBeTruthy()
        expect(w.get(`[data-testid=pb-guard-label-${key}]`).text()).toBe(GUARD_WORDS[key])
      }
      expect(w.get('[data-testid=pb-body]').text()).not.toMatch(/[a-z]+_[a-z_]+/)
      w.unmount()
    }
    expect(seen.size).toBe(12)
  })

  it('a guard key with no label shows no raw key (the row says the words are missing)', async () => {
    const entry = JSON.parse(JSON.stringify(icEntry()))
    entry.body.guards.brand_new_guard = '5'
    setUpReal(entry)
    const { w, errors } = await openCaught()
    await w.get('[data-testid=pb-step-limits]').trigger('click')
    expect(w.get('[data-testid=pb-guard-label-brand_new_guard]').text()).toBe('')
    expect(w.get('[data-testid=pb-body]').text()).not.toContain('brand_new_guard')
    expect(errors).toEqual([])
  })

  it('attack 5: editing a Middle value and saving as new keeps every null list null', async () => {
    setUpReal(icEntry())
    answers['POST /playbooks'] = (payload) => ({ ...row({ id: 9, name: payload.name, is_system: false, active: false }), body: payload.body })
    const { w } = await openCaught()
    await w.get('[data-testid=pb-step-when]').trigger('click')
    await w.get('[data-testid=pb-value-T-01-1]').setValue('0.4')
    await w.get('[data-testid=pb-new-name]').setValue('IC tighter')
    await w.get('[data-testid=pb-save-as]').trigger('click')
    await flushPromises()
    const body = calls.find(([m, u]) => m === 'POST' && u === '/playbooks')[2].body
    expect(body.triggers['T-01'].weekly[1]).toBe('0.4')
    for (const id of NULL_LISTS) {
      expect(body.triggers[id].weekly).toBeNull()
      expect(body.triggers[id].monthly).toBeNull()
    }
  })

  it('every answer state of a value list: stated, null, missing key, empty list; adding a stage creates no list', async () => {
    const entry = JSON.parse(JSON.stringify(icEntry()))
    const t = entry.body.triggers
    delete t['T-03'].monthly // missing key
    t['T-04'].weekly = [] // empty list
    setUpReal(entry)
    const { w, errors } = await openCaught()
    await w.get('[data-testid=pb-step-when]').trigger('click')
    expect(w.get('[data-testid=pb-value-T-03-0]').element.value).toBe(t['T-03'].weekly[0]) // stated
    expect(w.get('[data-testid=pb-novalue-T-04]').text()).toBe(NO_VALUES) // empty list
    expect(w.get('[data-testid=pb-novalue-T-02]').text()).toBe(NO_VALUES) // null
    await w.get('[data-testid=pb-kind-monthly]').trigger('click')
    expect(w.get('[data-testid=pb-novalue-T-03]').text()).toBe(NO_VALUES) // missing key
    await w.get('[data-testid=pb-step-basics]').trigger('click')
    await w.get('[data-testid=pb-stage-add]').trigger('click')
    await w.get('[data-testid=pb-step-test]').trigger('click')
    await w.get('[data-testid=pb-run-test]').trigger('click')
    await flushPromises()
    expect(errors).toEqual([])
    const sent = calls.find(([m, u]) => m === 'POST' && u === '/playbooks/test')[2].body.triggers
    expect(sent['T-02'].monthly).toBeNull()
    expect('monthly' in sent['T-03']).toBe(false)
    expect(sent['T-01'].monthly).toHaveLength(t['T-01'].monthly.length + 1)
  })

  it('a rule with neither any_of nor all_of, and a body without approaches, guards or stages, render without error', async () => {
    const entry = JSON.parse(JSON.stringify(icEntry()))
    entry.body.rules.push({ id: 'X-1' })
    delete entry.body.approaches
    delete entry.body.guards
    entry.body.stages.monthly = null
    setUpReal(entry)
    const { w, errors } = await openCaught()
    for (const [step] of STEPS) {
      await w.get(`[data-testid=pb-step-${step}]`).trigger('click')
      for (const [kind] of EXPIRY_KINDS) await w.get(`[data-testid=pb-kind-${kind}]`).trigger('click')
    }
    expect(errors).toEqual([])
  })
})
