// Lane Y item 1 (REQ-115 AC-4/AC-6; REQ-049 line 38; domain-model line 71): the badge, its reason and since-when on the
// Live Strategies card, Positions row and builder; the server's words only; fail closed to "Health unknown".
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { entryFor, readMonitoring } from '@/lib/monitoringState'

const paused = { strategy_id: 7, watch_state: 'paused', reason: 'workers_down', badge_text: 'Monitoring paused', health_text: 'Health unknown',
  reason_text: 'Not being watched: no worker has reported in the last 2 minutes.', since_text: 'Since 10:55' }
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('MonitoringBadge', () => {
  it('prints the server badge, grey dot, reason and since for a paused trade', () => {
    const w = mount(MonitoringBadge, { props: { entry: paused } })
    expect(t(w, 'monitoring-paused').text()).toBe('⏸ Monitoring paused')
    expect(t(w, 'monitoring-health-dot').text()).toBe('Health unknown')
    expect(t(w, 'monitoring-reason').text()).toBe('Not being watched: no worker has reported in the last 2 minutes.')
    expect(t(w, 'monitoring-since').text()).toBe('Since 10:55')
  })
  it('shows nothing for an active trade and nothing before the first answer', () => {
    expect(mount(MonitoringBadge, { props: { entry: { ...paused, watch_state: 'active' } } }).find('[data-testid="monitoring-badge"]').exists()).toBe(false)
    expect(mount(MonitoringBadge, { props: { entry: null } }).find('[data-testid="monitoring-badge"]').exists()).toBe(false)
  })
})

describe('entryFor fails closed', () => {
  it('unknown status, an unnamed id and a failed read are all paused with Health unknown', () => {
    const m = readMonitoring({ strategies: [{ ...paused, watch_state: 'weird' }] })
    expect(entryFor(m, 7).watch_state).toBe('paused')
    expect(entryFor(m, 8).health_text).toBe('Health unknown')
    expect(entryFor(null, 8, true).reason).toBe('unreadable')
    expect(readMonitoring({})).toBeNull()
    expect(readMonitoring({ strategies: [] }).size).toBe(0)
  })
  it('a failed or old read overrides a cached active entry (never a stale "healthy")', () => {
    const m = readMonitoring({ strategies: [{ ...paused, watch_state: 'active' }] })
    expect(entryFor(m, 7, true).watch_state).toBe('paused')
    expect(entryFor(m, 7, true).health_text).toBe('Health unknown')
  })
  it('an active answer stays active', () => {
    expect(entryFor(readMonitoring({ strategies: [{ ...paused, watch_state: 'active' }] }), 7).watch_state).toBe('active')
  })
})

describe('useMonitoringState asks for the ids it shows', () => {
  it('sends one request with the ids, none for an empty list', async () => {
    const calls = []
    const { vi } = await import('vitest')
    vi.resetModules()
    vi.doMock('@/services/api', () => ({ default: { get: (u, o) => { calls.push([u, o.params.ids]); return Promise.resolve({ data: { strategies: [{ strategy_id: 2, watch_state: 'active', reason: 'active' }] } }) } } }))
    const { useMonitoringState } = await import('@/lib/monitoringState')
    const { mount, flushPromises } = await import('@vue/test-utils')
    const { defineComponent, ref } = await import('vue')
    const ids = ref([3, 2, 3])
    let m
    mount(defineComponent({ setup() { m = useMonitoringState(() => ids.value); return () => null } }))
    await flushPromises()
    expect(calls).toEqual([['/monitoring-state', '2,3']])
    expect(m.entryOf(2).watch_state).toBe('active')
    expect(m.entryOf(3).watch_state).toBe('paused') // named by nobody: not healthy
    ids.value = []
    await flushPromises()
    expect(calls.length).toBe(1)
    vi.doUnmock('@/services/api')
  })
})
