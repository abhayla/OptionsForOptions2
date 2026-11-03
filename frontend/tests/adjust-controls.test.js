// GC-IC1 step 4b (REQ-155): the Compare page's pause (A-38), watch-a-level (A-37) and delta-neutral (A-23) controls against a
// mocked API in the routes' own reply shapes (monitoring_pause.PauseOut, level_watch.WatchOut, AdjustDeltaNeutralOut).
// The server reads the pause end as "HH:MM" and answers `until` as HHMM (monitoring_pause.parse_until / PauseOut.until).
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import AdjustControls from '@/components/strategy/AdjustControls.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const PAUSE_NONE = { strategy_id: 5, label: 'Pause adjustment checks', paused: false, until: null, state_text: 'Adjustment checks are running. Stop-losses and exits always run.' }
const PAUSE_SET = { ...PAUSE_NONE, paused: true, until: '1030', state_text: 'Adjustment checks paused until 10:30. Stop-losses and exits still run.' }
const WATCH_NONE = { strategy_id: 5, above: null, below: null }
const refusal = (reason, status = 422) => Object.assign(new Error('x'), { status, reason })
const KNOWN = { label: 'Delta-neutral figures (a calculation, not a suggestion to trade)', known: true, reason: null, missing_leg: null, net_delta: '-0.42', option_type: 'CE', option_strike: '23800.00', option_lots: 2, option_remaining: '-0.03', future_lots: 1, future_remaining: '0.01' }
const UNKNOWN = { label: KNOWN.label, known: false, reason: 'Net delta is not known: a leg has no implied volatility now.', missing_leg: 'NIFTY2611323800CE' }

function client(over = {}) {
  return {
    get: vi.fn(async (url) => ({ data: url.endsWith('/monitoring-pause') ? PAUSE_NONE : WATCH_NONE })),
    put: vi.fn(async () => ({ data: PAUSE_SET })),
    delete: vi.fn(async () => ({ data: PAUSE_NONE })),
    ...over,
  }
}
async function show(c, deltaNeutral = null) {
  const w = mount(AdjustControls, { props: { strategyId: 5, client: c, deltaNeutral } })
  await flushPromises()
  return w
}

describe('A-38 pause', () => {
  it('reads the state on mount and shows the server\'s texts', async () => {
    const c = client()
    const w = await show(c)
    expect(c.get).toHaveBeenCalledWith('/strategies/5/monitoring-pause')
    expect(t(w, 'pause-label').text()).toBe('Pause adjustment checks')
    expect(t(w, 'pause-state').text()).toBe(PAUSE_NONE.state_text)
  })

  it('setting 10:30 sends PUT with "10:30" (the shape the server reads) and shows "paused until 10:30"', async () => {
    const c = client()
    const w = await show(c)
    await t(w, 'pause-time').setValue('10:30')
    await t(w, 'pause-set').trigger('click')
    await flushPromises()
    expect(c.put).toHaveBeenCalledWith('/strategies/5/monitoring-pause', { until: '10:30' })
    expect(t(w, 'pause-state').text()).toContain('paused until 10:30')
    expect(t(w, 'pause-state').attributes('data-paused')).toBe('true')
  })

  it('clearing sends DELETE and shows the running state again', async () => {
    const c = client({ get: vi.fn(async (u) => ({ data: u.endsWith('pause') ? PAUSE_SET : WATCH_NONE })) })
    const w = await show(c)
    expect(t(w, 'pause-state').text()).toContain('paused until 10:30')
    await t(w, 'pause-clear').trigger('click')
    await flushPromises()
    expect(c.delete).toHaveBeenCalledWith('/strategies/5/monitoring-pause')
    expect(t(w, 'pause-state').text()).toBe(PAUSE_NONE.state_text)
  })

  it('a 422 shows the server\'s reason text and keeps the last state', async () => {
    const c = client({ put: vi.fn(async () => { throw refusal('Pick a time later today than now.') }) })
    const w = await show(c)
    await t(w, 'pause-time').setValue('09:00')
    await t(w, 'pause-set').trigger('click')
    await flushPromises()
    expect(t(w, 'pause-refusal').text()).toBe('Pick a time later today than now.')
    expect(t(w, 'pause-state').text()).toBe(PAUSE_NONE.state_text)
  })

  it('a network failure is named, and the control stays usable', async () => {
    const c = client({ put: vi.fn(async () => { throw new Error('Network Error') }) })
    const w = await show(c)
    await t(w, 'pause-time').setValue('10:30')
    await t(w, 'pause-set').trigger('click')
    await flushPromises()
    expect(t(w, 'pause-failed').exists()).toBe(true)
    expect(t(w, 'pause-refusal').exists()).toBe(false)
    expect(t(w, 'pause-set').attributes('disabled')).toBeUndefined()
  })
})

describe('A-37 watch a level', () => {
  it('shows None, then a watch above 23800 sends PUT .../level-watch/above and shows it', async () => {
    const c = client({ put: vi.fn(async () => ({ data: { ...WATCH_NONE, above: '23800' } })) })
    const w = await show(c)
    expect(c.get).toHaveBeenCalledWith('/strategies/5/level-watch')
    expect(t(w, 'watch-above-now').text()).toBe('None')
    await t(w, 'watch-above-input').setValue('23800')
    await t(w, 'watch-above-set').trigger('click')
    await flushPromises()
    expect(c.put).toHaveBeenCalledWith('/strategies/5/level-watch/above', { level: '23800' })
    expect(t(w, 'watch-above-now').text()).toBe('23800')
    expect(t(w, 'watch-below-now').text()).toBe('None')
  })

  it('below goes to .../below and clearing sends DELETE for that direction', async () => {
    const c = client({
      put: vi.fn(async () => ({ data: { ...WATCH_NONE, below: '23000.5' } })),
      delete: vi.fn(async () => ({ data: WATCH_NONE })),
    })
    const w = await show(c)
    await t(w, 'watch-below-input').setValue('23000.5')
    await t(w, 'watch-below-set').trigger('click')
    await flushPromises()
    expect(c.put).toHaveBeenCalledWith('/strategies/5/level-watch/below', { level: '23000.5' })
    expect(t(w, 'watch-below-now').text()).toBe('23000.5')
    await t(w, 'watch-below-clear').trigger('click')
    await flushPromises()
    expect(c.delete).toHaveBeenCalledWith('/strategies/5/level-watch/below')
    expect(t(w, 'watch-below-now').text()).toBe('None')
  })

  it('a 422 shows the server\'s reason; a network failure is named', async () => {
    const put = vi.fn().mockRejectedValueOnce(refusal('Enter the level as a number above zero, like 23800.')).mockRejectedValueOnce(new Error('Network Error'))
    const w = await show(client({ put }))
    await t(w, 'watch-above-input').setValue('abc')
    await t(w, 'watch-above-set').trigger('click')
    await flushPromises()
    expect(t(w, 'watch-refusal').text()).toBe('Enter the level as a number above zero, like 23800.')
    await t(w, 'watch-above-set').trigger('click')
    await flushPromises()
    expect(t(w, 'watch-refusal').exists()).toBe(false)
    expect(t(w, 'watch-failed').exists()).toBe(true)
  })
})

describe('A-23 delta-neutral block', () => {
  it('shows the server\'s figures as given', async () => {
    const w = await show(client(), KNOWN)
    expect(t(w, 'delta-label').text()).toBe(KNOWN.label)
    expect(t(w, 'delta-net_delta').text()).toBe('-0.42')
    expect(t(w, 'delta-option').text()).toBe('2')
    expect(t(w, 'delta-option_remaining').text()).toBe('-0.03')
    expect(t(w, 'delta-future_lots').text()).toBe('1')
    expect(t(w, 'delta-future_remaining').text()).toBe('0.01')
  })

  it('"not known" shows the server\'s reason and no figure', async () => {
    const w = await show(client(), UNKNOWN)
    expect(t(w, 'delta-reason').text()).toContain(UNKNOWN.reason)
    expect(t(w, 'delta-net_delta').exists()).toBe(false)
  })

  it('absent block (older server) draws nothing', async () => {
    const w = await show(client(), null)
    expect(t(w, 'delta-card').exists()).toBe(false)
  })

  it('computes nothing: the component source has no arithmetic on the block\'s figures', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/components/strategy/AdjustControls.vue'), 'utf8')
    expect(src).not.toMatch(/Number\(|parseFloat|parseInt|Decimal|\.toFixed|\bMath\./)
    expect(src).not.toMatch(/(net_delta|option_remaining|future_remaining|option_lots|future_lots)\s*[-+*/]/)
  })
})
