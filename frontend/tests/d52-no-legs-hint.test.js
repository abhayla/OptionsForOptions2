// D-52 (docs/process/ic-live-test-2026-11-23-issues.md, condors C1): the empty builder said "start from a ready-made shape
// below" while no shapes were there (the Ready-made tab is a held feature, REQ-079 / Q211; the shapes were only on the
// Create Strategy page). The hint now names the place that exists on the screen being shown: the tab when the server lists
// the held feature, else the Create Strategy page; a failed features read counts as "not listed" (fail closed).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let features
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/features' ? features() : Promise.reject(new Error(`unmocked ${url}`))), post: () => Promise.reject(new Error('unmocked')) } }
})
import LegList from '@/components/strategy/LegList.vue'

const hint = async () => {
  const w = mount(LegList, { props: { legs: [], multiplierMax: 50 } })
  await flushPromises()
  return w.find('[data-testid="no-legs-hint"]').text()
}

describe('D-52: the empty-builder hint points to a place that is on the screen', () => {
  beforeEach(() => { features = () => Promise.resolve({ data: { held: [] } }) })

  it('shapes not listed: the hint says Create Strategy and never says "below"', async () => {
    const text = await hint()
    expect(text).toBe('Pick strikes, or start from a ready-made shape on the Create Strategy page.')
    expect(text).not.toContain('below')
  })

  it('the held feature is listed: the hint names the Ready-made tab', async () => {
    features = () => Promise.resolve({ data: { held: ['platform_strikes'] } })
    expect(await hint()).toBe('Pick strikes, or start from a ready-made shape in the Ready-made tab.')
  })

  it('the features read failed: the Create Strategy wording (fail closed)', async () => {
    features = () => Promise.reject(new Error('down'))
    expect(await hint()).toBe('Pick strikes, or start from a ready-made shape on the Create Strategy page.')
  })

  it('round 2: the hint shows nothing until the features read has finished, then the right wording, in both orders', async () => {
    for (const [held, wording] of [[[], 'on the Create Strategy page.'], [['platform_strikes'], 'in the Ready-made tab.']]) {
      let release
      features = () => new Promise((resolve) => { release = () => resolve({ data: { held } }) })
      const w = mount(LegList, { props: { legs: [], multiplierMax: 50 } })
      await flushPromises()
      expect(w.find('[data-testid="no-legs-hint"]').exists() ? w.get('[data-testid="no-legs-hint"]').text() : '').toBe('')
      release()
      await flushPromises()
      expect(w.get('[data-testid="no-legs-hint"]').text()).toContain(wording)
    }
  })
})
