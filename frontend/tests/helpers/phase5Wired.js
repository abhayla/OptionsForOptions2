// Phase 5 (Lane B): which parts of the page wiring are in StrategyBuilderPage.vue yet. The page commit is Lane A's file until the
// hand-over (PLAN 3.2), so the tests that mount the REAL page and need that wiring run only once the page names the module
// (they turn themselves on in the page commit, no edit needed); `LANE_B_FORCE=1` runs them regardless (the red evidence).
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const page = readFileSync(resolve(__dirname, '../../src/pages/StrategyBuilderPage.vue'), 'utf8')
const force = process.env.LANE_B_FORCE === '1'
export const WIRED = {
  door: force || page.includes('useLegDoor'), // 5.5.4: one door + one dialog + provide
  draftReplace: force || page.includes('draft-replace-dialog'), // ADR-328 (2)
  hold: force || page.includes('useBuilderHold'), // ADR-329 (1): take() on mount, hold on the chain trip, chain-add through the door
  leave: force || page.includes('useLeaveBuilder'), // ADR-329 (2)
}
