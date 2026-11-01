// GC-SET step 9 (REQ-169 AC-1..AC-3): the admin's controls for a system playbook in the user's playbook editor.
// Answers have the shapes of routes/system_playbooks.py (SystemHistoryOut, SystemVersionOut, RefusedOut).
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
    if (a instanceof Error || a?.reason || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: typeof a === 'function' ? a(payload) : a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), delete: reply('DELETE') } }
})
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'
import { useViewer } from '@/stores/viewer'

const BODY = {
  schema: 1, strategy_type: 'ic', status: 'approved',
  stages: { weekly: [{ name: 'Early', from: 5, to: null }, { name: 'Last day', from: 0, to: 4 }], monthly: [{ name: 'Early', from: 10, to: null }, { name: 'Last', from: 0, to: 9 }] },
  triggers: {}, rules: [], day_rules: [], situations: [],
  guards: { profit_target_pct_of_max_profit: '50', stop_line_pct_of_max_loss: '50', max_adjustments: 2 },
  approaches: { applicable: ['A-01'], off_in_playbook: [], greyed: [] },
}
const copy = (o) => JSON.parse(JSON.stringify(o))
const ROW = { id: 1, name: 'Iron condor: system', type: 'ic', type_name: 'Iron condor', is_system: true, status: 'approved', draft: false, active: true, version: 1, updated_at: '2026-10-31T09:00:00+05:30' }
const ver = (version, over = {}) => ({ type: 'ic', type_name: 'Iron condor', version, status: 'approved', draft: false, current: false, restored_from: null,
  saved_by: 'owner', saved_at: '2026-10-31T09:00:00+05:30', body: copy(BODY), ...over })

function setUp(row = ROW, versions = [ver(1, { current: true })]) {
  answers['GET /playbooks/labels'] = LABELS
  answers['GET /playbooks/types'] = { types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] }
  answers['GET /playbooks'] = { playbooks: [row] }
  answers[`GET /playbooks/${row.id}`] = { ...row, body: copy(BODY) }
  answers['GET /system-playbooks/ic/versions'] = { versions }
}
async function open({ admin = true } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useViewer().admin = admin
  const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query: {} } } } })
  await flushPromises()
  return w
}
const posts = () => calls.filter((c) => c[0] === 'POST')

beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 })

describe('system playbook admin controls (REQ-169)', () => {
  it('AC-1/AC-2: edit the stop, Save posts body + reason and shows version 2', async () => {
    setUp()
    answers['POST /system-playbooks/ic/versions'] = (p) => ver(2, { current: true, body: p.body })
    const w = await open()
    expect(w.find('[data-testid=sys-edit]').text()).toBe('Edit system playbook')
    await w.get('[data-testid=sys-edit]').trigger('click')
    await w.get('[data-testid=pb-step-limits]').trigger('click')
    await w.get('[data-testid=pb-guard-stop_line_pct_of_max_loss]').setValue('40')
    await w.get('[data-testid=sys-reason]').setValue('Tighter stop')
    answers['GET /system-playbooks/ic/versions'] = { versions: [ver(2, { current: true }), ver(1)] }
    await w.get('[data-testid=sys-save]').trigger('click')
    await flushPromises()
    const [, url, payload] = posts()[0]
    expect(url).toBe('/system-playbooks/ic/versions')
    expect(payload.reason).toBe('Tighter stop')
    expect(payload.base_version).toBe(1)
    expect(payload.body.guards.stop_line_pct_of_max_loss).toBe('40')
    expect(w.get('[data-testid=sys-version]').text()).toBe('Version 2')
    expect(w.get('[data-testid=sys-notice]').text()).toContain('version 2')
  })

  it('AC-1: Save without a reason is refused in the form and posts nothing', async () => {
    setUp()
    const w = await open()
    await w.get('[data-testid=sys-edit]').trigger('click')
    await w.get('[data-testid=sys-save]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=sys-form-error]').text()).toContain('why')
    expect(posts()).toHaveLength(0)
  })

  it('AC-2: Restore this version on version 1 posts to the restore route', async () => {
    setUp(ROW, [ver(2, { current: true }), ver(1)])
    answers['POST /system-playbooks/ic/versions/1/restore'] = ver(3, { current: true, restored_from: 1 })
    const w = await open()
    await w.get('[data-testid=sys-reason]').setValue('Back to the first')
    expect(w.find('[data-testid=sys-restore-2]').exists()).toBe(false)
    expect(w.get('[data-testid=sys-restore-1]').text()).toBe('Restore this version')
    await w.get('[data-testid=sys-restore-1]').trigger('click')
    await flushPromises()
    expect(posts()[0]).toEqual(['POST', '/system-playbooks/ic/versions/1/restore', { reason: 'Back to the first', base_version: 2 }])
  })

  it('AC-3: a Draft shows Approve, which posts with a reason', async () => {
    setUp({ ...ROW, status: 'draft', draft: true }, [ver(1, { current: true, status: 'draft', draft: true })])
    answers['POST /system-playbooks/ic/approve'] = ver(2, { current: true })
    const w = await open()
    await w.get('[data-testid=sys-reason]').setValue('Checked against the spec')
    await w.get('[data-testid=sys-approve]').trigger('click')
    await flushPromises()
    expect(posts()[0]).toEqual(['POST', '/system-playbooks/ic/approve', { reason: 'Checked against the spec', base_version: 1 }])
  })

  it('shows the server sentence when a save is refused', async () => {
    setUp()
    answers['POST /system-playbooks/ic/versions'] = { reason: 'Someone saved a newer version first.' }
    const w = await open()
    await w.get('[data-testid=sys-edit]').trigger('click')
    await w.get('[data-testid=sys-reason]').setValue('x')
    await w.get('[data-testid=sys-save]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid=sys-refusal]').text()).toBe('Someone saved a newer version first.')
  })

  it('with the admin flag off none of the three controls render and no admin read is made', async () => {
    setUp({ ...ROW, status: 'draft', draft: true }, [ver(2, { current: true, status: 'draft', draft: true }), ver(1)])
    const w = await open({ admin: false })
    expect(w.find('[data-testid=sys-edit]').exists()).toBe(false)
    expect(w.find('[data-testid=sys-approve]').exists()).toBe(false)
    expect(w.find('[data-testid=sys-restore-1]').exists()).toBe(false)
    expect(calls.filter((c) => c[1].startsWith('/system-playbooks'))).toHaveLength(0)
  })
})
