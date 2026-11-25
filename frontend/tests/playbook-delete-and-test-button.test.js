// GC-ICLIVE Part E, D-54 (ADR-320 point 6): deleting a playbook asks "Delete this playbook?" first; the "Test this playbook"
// button (it did nothing: testing on past expiries is outside V1, REQ-160) is gone and one line says so where it was.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routeLocationKey } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import LABELS from './fixtures/playbook-labels.json'

const answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[`${method} ${url}`]
    if (a instanceof Error || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), delete: reply('DELETE') } }
})
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'

const BODY = { schema: 1, strategy_type: 'ic', status: 'approved', stages: { weekly: [{ name: 'Early', from: 5, to: null }], monthly: [] },
  triggers: {}, rules: [], day_rules: [], situations: [], guards: {}, approaches: { applicable: [], off_in_playbook: [], greyed: [] } }
const row = (over) => ({ id: 1, name: 'Iron condor: system', type: 'ic', type_name: 'Iron condor', is_system: true, status: 'approved', draft: false, active: true, version: 1, updated_at: '2026-10-31T09:00:00+05:30', ...over })
const OWN = row({ id: 7, name: '"IC mine"', is_system: false, status: null, active: false, version: 3 })
const PAST = 'Testing against past expiries is not in this version: it needs licensed historical option data.'

async function open() {
  answers['GET /playbooks/labels'] = LABELS
  answers['GET /playbooks/types'] = { types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] }
  answers['GET /playbooks'] = { playbooks: [row({}), OWN] }
  for (const p of [row({}), OWN]) answers[`GET /playbooks/${p.id}`] = { ...p, body: JSON.parse(JSON.stringify(BODY)) }
  const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query: {} } } } })
  await flushPromises()
  await w.get('[data-testid=pb-pick] option[value="7"]').setSelected()
  await flushPromises()
  return w
}
const deletes = () => calls.filter(([m]) => m === 'DELETE')
beforeEach(() => { setActivePinia(createPinia()); for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 })

describe('D-54 delete asks first', () => {
  it('the first click shows "Delete this playbook?" and sends nothing', async () => {
    const w = await open()
    await w.get('[data-testid=pb-delete]').trigger('click')
    expect(w.get('[data-testid=pb-delete-confirm]').text()).toContain('Delete this playbook?')
    expect(deletes()).toHaveLength(0)
  })
  it('cancel keeps the playbook and sends nothing', async () => {
    const w = await open()
    await w.get('[data-testid=pb-delete]').trigger('click')
    await w.get('[data-testid=pb-delete-cancel]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid=pb-delete-confirm]').exists()).toBe(false)
    expect(deletes()).toHaveLength(0)
    expect(w.find('[data-testid=pb-delete]').exists()).toBe(true)
  })
  it('confirm deletes that playbook', async () => {
    answers['DELETE /playbooks/7'] = { deleted: true, active_now_system: false, message: null }
    const w = await open()
    await w.get('[data-testid=pb-delete]').trigger('click')
    await w.get('[data-testid=pb-delete-yes]').trigger('click')
    await flushPromises()
    expect(deletes().map((c) => c[1])).toEqual(['/playbooks/7'])
    expect(w.find('[data-testid=pb-delete-confirm]').exists()).toBe(false)
  })
  it('a failed delete says so (the server sentence) and the question is gone', async () => {
    answers['DELETE /playbooks/7'] = { message: 'refused', status: 409, parts: { what_happened: 'The playbook could not be deleted.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }
    const w = await open()
    await w.get('[data-testid=pb-delete]').trigger('click')
    await w.get('[data-testid=pb-delete-yes]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=pb-refusal]').text()).toBe('The playbook could not be deleted.')
    expect(w.find('[data-testid=pb-delete-confirm]').exists()).toBe(false)
  })
  it('a system playbook has no Delete, so no question', async () => {
    const w = await open()
    await w.get('[data-testid=pb-pick] option[value="1"]').setSelected()
    await flushPromises()
    expect(w.find('[data-testid=pb-delete]').exists()).toBe(false)
  })
})

describe('D-54 the Test button is gone, the line says why', () => {
  it('the Test step has the past-expiries line and no Test button', async () => {
    const w = await open()
    await w.get('[data-testid=pb-step-test]').trigger('click')
    expect(w.find('[data-testid=pb-run-test]').exists()).toBe(false)
    expect(w.get('[data-testid=pb-past-note]').text()).toBe(PAST)
    expect(w.text()).not.toMatch(/Test this playbook|Test unsaved changes/)
  })
})
