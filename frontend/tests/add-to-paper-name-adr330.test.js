// ADR-330 (19) (a): Add to Paper on an UNSAVED strategy asks for a name (the existing name dialog, prefilled with the shape name).
// Confirm saves under the typed name then opens the paper confirm; Cancel sends nothing; a saved strategy asks nothing.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (method === 'POST' && url === '/strategies') return Promise.resolve({ data: { id: 172, revision: 1, name: `"${body.name}"` } })
    return Promise.reject(new Error(`unmocked ${method} ${url}`))
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 1, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function mountBar(props) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p />' } }] })
  const w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'Short Iron Condor', ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return w
}
const saves = () => calls.filter((c) => c.method === 'POST' && c.url === '/strategies')
beforeEach(() => { calls.length = 0; document.body.innerHTML = '' })

describe('ADR-330 (19) (a): Add to Paper asks for a name', () => {
  it('opens the name dialog prefilled with the shape name; nothing is sent yet', async () => {
    const w = await mountBar({})
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(document.querySelector('[data-testid="name-form"]').getAttribute('data-mode')).toBe('paper')
    expect(document.querySelector('[data-testid="name-input"]').value).toBe('Short Iron Condor')
    expect(saves()).toHaveLength(0)
    w.unmount()
  })
  it('typing a name and confirming saves under that name, then opens the paper confirm', async () => {
    const w = await mountBar({})
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    const input = document.querySelector('[data-testid="name-input"]')
    input.value = 'IC Dec wk1'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    document.querySelector('[data-testid="name-confirm"]').click()
    await flushPromises()
    expect(saves()).toHaveLength(1)
    expect(saves()[0].body.name).toBe('IC Dec wk1')
    expect(w.emitted('saved')[0][0]).toBe(172)
    expect(document.querySelector('[data-testid="paper-confirm-button"]')).not.toBeNull()
    w.unmount()
  })
  it('Cancel adds nothing', async () => {
    const w = await mountBar({})
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    document.querySelector('[data-testid="name-cancel"]').click()
    await flushPromises()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    expect(document.querySelector('[data-testid="paper-confirm-button"]')).toBeNull()
    w.unmount()
  })
  it('an already saved strategy asks nothing and goes straight to the paper confirm', async () => {
    const w = await mountBar({ current: { id: 172, revision: 1, name: '"IC Dec wk1"' } })
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(document.querySelector('[data-testid="name-form"]')).toBeNull()
    expect(document.querySelector('[data-testid="paper-confirm-button"]')).not.toBeNull()
    expect(saves()).toHaveLength(0)
    w.unmount()
  })
})
