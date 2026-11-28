// Far-month ruling (Lane FC item 8; REQ-115, REQ-049 line 38, ADR-330 (58)): a trade whose every exit rule reads "not checked" because its expiry kind is
// not known shows the existing "Monitoring paused" badge and its reason, never "watched". The page cannot derive the cause (the rule check names none), so
// the server's monitoring-state entry carries it: watch_state 'paused', reason 'expiry_kind_unknown' (named for Lane FD in RESULTS-lane-fc).
// Cases: stated, absent, active (some rules unchecked: no claim either way), failed read (fail closed), unknown reason text missing.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MonitoringBadge from '@/components/common/MonitoringBadge.vue'
import { entryFor, readMonitoring, MONITORING_UNREAD_BADGE } from '@/lib/monitoringState'

const KIND = { strategy_id: 41, watch_state: 'paused', reason: 'expiry_kind_unknown', badge_text: 'Monitoring paused',
  health_text: 'Health unknown', reason_text: 'Every exit rule is not checked because whether this trade expires weekly or monthly is not known.', since_text: null }
const text = (w, id) => w.find(`[data-testid="${id}"]`)

describe('far-month trade: every exit rule not checked, expiry kind unknown', () => {
  it('stated: Monitoring paused with the reason; never the word watched', () => {
    const entry = entryFor(readMonitoring({ strategies: [KIND] }), 41)
    const w = mount(MonitoringBadge, { props: { entry } })
    expect(text(w, 'monitoring-paused').text()).toContain('Monitoring paused')
    expect(text(w, 'monitoring-reason').text()).toBe(KIND.reason_text)
    expect(w.get('[data-testid="monitoring-badge"]').attributes('data-reason')).toBe('expiry_kind_unknown')
    expect(w.text().toLowerCase()).not.toContain('watched')
  })
  it('stated but the server sent no words: the fail-closed words fill in, still paused', () => {
    const entry = entryFor(readMonitoring({ strategies: [{ strategy_id: 41, watch_state: 'paused', reason: 'expiry_kind_unknown' }] }), 41)
    const w = mount(MonitoringBadge, { props: { entry } })
    expect(text(w, 'monitoring-paused').text()).toContain(MONITORING_UNREAD_BADGE)
    expect(text(w, 'monitoring-reason').text()).not.toBe('')
  })
  it('absent (the answer does not name the trade) is paused, never a claim that it is watched', () => {
    const w = mount(MonitoringBadge, { props: { entry: entryFor(readMonitoring({ strategies: [] }), 41) } })
    expect(text(w, 'monitoring-paused').text()).toContain('Monitoring paused')
  })
  it('read failed: paused even when an earlier answer said active', () => {
    const map = readMonitoring({ strategies: [{ strategy_id: 41, watch_state: 'active' }] })
    const w = mount(MonitoringBadge, { props: { entry: entryFor(map, 41, true) } })
    expect(text(w, 'monitoring-paused').exists()).toBe(true)
  })
  it('mixed: the server says active (some rules checked) - the badge prints nothing, and no "watched" claim is made', () => {
    const w = mount(MonitoringBadge, { props: { entry: entryFor(readMonitoring({ strategies: [{ strategy_id: 41, watch_state: 'active' }] }), 41) } })
    expect(w.find('[data-testid="monitoring-badge"]').exists()).toBe(false)
    expect(w.text()).toBe('')
  })
})
