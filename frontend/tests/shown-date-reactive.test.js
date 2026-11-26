// U-Q8 (a), ADR-330 (19), REQ-148 AC-2: a label computed before the shown date arrives recomputes once it is noted.
import { computed } from 'vue'
import { describe, expect, it } from 'vitest'
import { noteShownDate, setShownDate } from '@/lib/displayFormat'
import { strategyListLabel } from '@/lib/saveDraft'

describe('shown date is one reactive value', () => {
  it('a computed list label drops the year after noteShownDate, and keeps it when the date is gone', () => {
    setShownDate(null)
    const label = computed(() => strategyListLabel({ name: '"Bull"', id: 17, expiries: ['2026-12-01'], fallback: 'x' }))
    expect(label.value).toBe('Bull (#17, 1 Dec 2026)')
    noteShownDate({ shown_date: '2026-11-26' })
    expect(label.value).toBe('Bull (#17, 1 Dec)')
    noteShownDate({ strategies: [] }) // a reply without one changes nothing
    expect(label.value).toBe('Bull (#17, 1 Dec)')
    setShownDate(null)
    expect(label.value).toBe('Bull (#17, 1 Dec 2026)')
  })
})
