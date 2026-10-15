// W-065: the Strategy Builder opens the live socket (/api/strategies/live) whenever a priced draft is on screen. Specs that
// prove the REST outcome path (W-064 screen states, the table against the REST answer, the leg picker) hold the socket
// open but silent, so no push moves the numbers under their assertions and no socket holds or releases their legs on
// the replay (a released leg makes the replay's REST answer not live, as on the live market). The live path itself is
// proven in strategy-live.spec.ts.
import { test, type Page } from '@playwright/test'

export async function quietLiveSocket(page: Page) {
  await page.routeWebSocket('**/api/strategies/live', () => {}) // never connected to the API: no pushes, no subscription
}

/** Call at the top of a spec file: every test in it gets a silent live socket. */
export function useQuietLiveSocket() {
  test.beforeEach(async ({ page }) => quietLiveSocket(page))
}
