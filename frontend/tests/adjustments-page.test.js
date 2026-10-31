// GC-ADJ2 step 3 (REQ-160 AC-1..AC-4): the playbook editor page. Answers have the shapes of the playbook routes
// (PlaybookListOut, PlaybookFullOut, TestOut, the catalogue refusal message); the body is the iron condor system body's
// own shape (docs/design/playbook-body-v1.md), cut to the fields the assertions read. Every expected sentence is the
// answer's own text; nothing here computes a figure.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

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
import { summaryLines } from '@/lib/playbookEditor'

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
  answers['GET /playbooks/types'] = { types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] }
  answers['GET /playbooks'] = { playbooks: list }
  for (const p of list) answers[`GET /playbooks/${p.id}`] = { ...p, body: JSON.parse(JSON.stringify(BODY)) }
}
async function open(id = null) {
  const w = mount(AdjustmentsPage)
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

  it('the summary plan line reads the guards of the body', () => {
    const lines = summaryLines(BODY, 'Iron condor', 'monthly')
    expect(lines.find((l) => l.key === 'plan').text).toBe('Plan: target 50% of max profit, stop at 50% of max loss, at most 2 adjustments.')
  })
})
