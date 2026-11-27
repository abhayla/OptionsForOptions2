// ADR-328 (2), narrowed by ADR-329 (3): a builder that already shows legs and receives a REPLACING draft link (a pasted or shared one:
// the `?draft=` watch while the page stays mounted) asks "Replace the N legs in the builder?" (REQ-079 AC-5 shape, replacePrompt).
// Cancel keeps the legs and puts the previous query back. Real page, the recorded condor of outcome-condor.json. The questions that
// need the page's new dialog run once the page names `draft-replace-dialog` (tests/helpers/phase5Wired.js); the "asks nothing"
// rows hold today and stay green throughout.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { WIRED } from './helpers/phase5Wired'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { replacePrompt } from '@/lib/readyMade'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const link = (legs) => JSON.stringify({ underlying: 'NIFTY', legs: legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) })
const THREE = link(real.legs.slice(0, 3))
const ONE = link(real.legs.slice(3, 4))
const rowsOf = (w) => w.findAll('[data-testid="leg-row"]').length
const idsOf = (w) => w.vm.$.setupState.legs.map((l) => l.instrument_id)
let router

beforeEach(() => {
  calls.length = 0
  answers = { 'POST /strategies/outcome': real, 'POST /strategies/leg-edit': () => new Promise(() => {}), 'GET /strategies': { strategies: [] } }
})
async function open(query) {
  router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const pushDraft = async (draft) => {
  await router.push({ path: '/strategy/builder', query: { draft } })
  await flushPromises()
}

describe.runIf(WIRED.draftReplace)('ADR-328 (2): a replacing draft link on a mounted builder asks first', () => {
  it('the dialog says "Replace the 3 legs in the builder?"; Cancel keeps the 3 legs and the URL names the old draft', async () => {
    const w = await open({ draft: THREE })
    expect(rowsOf(w)).toBe(3)
    const before = idsOf(w)
    await pushDraft(ONE)
    expect(t(w, 'draft-replace-dialog').exists()).toBe(true)
    expect(t(w, 'draft-replace-dialog').text()).toContain(replacePrompt(3))
    expect(t(w, 'draft-replace-dialog').text()).toContain('Replace the 3 legs in the builder?')
    expect(rowsOf(w)).toBe(3) // nothing is replaced before the answer
    await t(w, 'draft-replace-cancel').trigger('click')
    await flushPromises()
    expect(idsOf(w)).toEqual(before)
    expect(router.currentRoute.value.query.draft).toBe(THREE)
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
  })
  it('Escape, x and the overlay are Cancel too', async () => {
    for (const close of [(w) => t(w, 'modal-root').trigger('keydown', { key: 'Escape' }), (w) => t(w, 'modal-close').trigger('click'), (w) => t(w, 'modal-overlay').trigger('click')]) {
      const w = await open({ draft: THREE })
      await pushDraft(ONE)
      await close(w)
      await flushPromises()
      expect(rowsOf(w)).toBe(3)
      expect(router.currentRoute.value.query.draft).toBe(THREE)
      w.unmount()
    }
  })
  it('Yes shows the new legs (today\'s path)', async () => {
    const w = await open({ draft: THREE })
    await pushDraft(ONE)
    await t(w, 'draft-replace-yes').trigger('click')
    await flushPromises()
    expect(idsOf(w)).toEqual([real.legs[3].instrument_id])
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
  })
  it('one leg on screen reads "Replace the 1 leg in the builder?"', async () => {
    const w = await open({ draft: ONE })
    await pushDraft(THREE)
    expect(t(w, 'draft-replace-dialog').text()).toContain('Replace the 1 leg in the builder?')
  })
  it('an unreadable ?draft= while legs are shown takes today\'s refusal path: no replace question, the link is refused as today', async () => {
    const w = await open({ draft: THREE })
    await pushDraft(JSON.stringify({ underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:1', action: 'BUY', lots: '2.0' }] })) // a leg that will not canonicalize
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
    expect(w.vm.$.setupState.linkRefused).toBe(true)
    expect(w.vm.$.setupState.state).toBe('error')
  })
})

describe('ADR-328 (2): the cases that ask nothing', () => {
  it('the same draft as shown (an equal link) -> no question, the legs stay', async () => {
    const w = await open({ draft: THREE })
    await pushDraft(THREE)
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
    expect(rowsOf(w)).toBe(3)
  })
  it('a builder with no legs receiving a draft link -> no question, the link\'s legs are shown', async () => {
    const w = await open({})
    expect(rowsOf(w)).toBe(0)
    await pushDraft(THREE)
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
    expect(rowsOf(w)).toBe(3)
  })
  it('a fresh mount with ?draft= (a pasted link, a reload) holds no legs, so it asks nothing', async () => {
    const w = await open({ draft: THREE })
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
    expect(rowsOf(w)).toBe(3)
  })
})
