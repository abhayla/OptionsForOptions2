// GC-ICFIX P3 u502 (REQ-134 AC-2; user test note ISSUES.md:149 "#78 Save button turned blue (enabled) again after the 'saved.' message and after
// every reload of an unchanged saved strategy; '0 pending changes'"): Save is enabled only when there is something to save, and the
// "saved." line goes away as soon as the legs are edited. Real SaveDraftBar, the page's own props.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

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
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const leg = (over = {}) => ({
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 2,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ...over,
})
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const saveOff = (w) => t(w, 'save-draft').attributes('disabled') !== undefined
const open = (props) => mount(SaveDraftBar, { props: { legs: [leg()], current: { id: 7, revision: 1, name: 'IC test' }, ...props }, global: { stubs: { RouterLink: true } } })

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'PUT /strategies/7': { id: 7, revision: 2, name: 'IC test' },
  }
})

describe('u502: Save needs something to save', () => {
  it('a saved strategy just opened (a reload of an unchanged one) has Save greyed out', async () => {
    const w = open()
    await flushPromises()
    expect(saveOff(w)).toBe(true)
  })
  it('a never-saved draft with savable legs has Save on', async () => {
    const w = open({ current: null })
    await flushPromises()
    expect(saveOff(w)).toBe(false)
  })
  it('a real edit turns Save on; undoing the edit turns it off again', async () => {
    const w = open()
    await flushPromises()
    await w.setProps({ legs: [leg({ lots: 3 })] })
    expect(saveOff(w)).toBe(false)
    await w.setProps({ legs: [leg()] })
    expect(saveOff(w)).toBe(true)
  })
  it('after Save the "saved." line shows and Save stays off; the next edit removes the line and turns Save on', async () => {
    const w = open({ legs: [leg({ lots: 3 })] })
    await flushPromises()
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
    await w.setProps({ current: { id: 7, revision: 2, name: 'IC test' } }) // the page takes the saved revision
    expect(t(w, 'save-status').text()).toContain('saved.')
    expect(saveOff(w)).toBe(true)
    await w.setProps({ legs: [leg({ lots: 4 })] })
    expect(t(w, 'save-status').text()).toBe('')
    expect(saveOff(w)).toBe(false)
  })
})
