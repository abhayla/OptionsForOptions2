// Lane Y item 1 (REQ-115 AC-4/AC-6; REQ-049 line 38; domain-model line 71): the badge, its reason and since-when on the
// Live Strategies card, Positions row and builder; the server's words only; fail closed to "Health unknown".
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { entryFor, readMonitoring } from '@/lib/monitoringState'

const paused = { strategy_id: 7, status: 'paused', reason: 'workers_down', badge_text: 'Monitoring paused', health_text: 'Health unknown',
  reason_text: 'Not being watched: no worker has reported in the last 2 minutes.', since_text: 'Since 10:55' }
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('MonitoringBadge', () => {
  it('prints the server badge, grey dot, reason and since for a paused trade', () => {
    const w = mount(MonitoringBadge, { props: { entry: paused } })
    expect(t(w, 'monitoring-paused').text()).toBe('⏸ Monitoring paused')
    expect(t(w, 'monitoring-health-dot').text()).toBe('Health unknown')
    expect(t(w, 'monitoring-reason').text()).toBe('Not being watched: no worker has reported in the last 2 minutes. Since 10:55.')
  })
  it('shows nothing for an active trade and nothing before the first answer', () => {
    expect(mount(MonitoringBadge, { props: { entry: { ...paused, status: 'active' } } }).find('[data-testid="monitoring-badge"]').exists()).toBe(false)
    expect(mount(MonitoringBadge, { props: { entry: null } }).find('[data-testid="monitoring-badge"]').exists()).toBe(false)
  })
})

describe('entryFor fails closed', () => {
  it('unknown status, an unnamed id and a failed read are all paused with Health unknown', () => {
    const m = readMonitoring({ strategies: [{ ...paused, status: 'weird' }] })
    expect(entryFor(m, 7).status).toBe('paused')
    expect(entryFor(m, 8).health_text).toBe('Health unknown')
    expect(entryFor(null, 8, true).reason).toBe('unreadable')
    expect(readMonitoring({})).toBeNull()
    expect(readMonitoring({ strategies: [] }).size).toBe(0)
  })
  it('an active answer stays active', () => {
    expect(entryFor(readMonitoring({ strategies: [{ ...paused, status: 'active' }] }), 7).status).toBe('active')
  })
})
