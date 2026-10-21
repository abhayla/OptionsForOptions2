// W-114 AC-2 (REQ-072 AC-2; REQ-049 AC-4; ADR-077, ADR-008): the Underlying/index view follows the server's pushes
// over /api/market/indices/live, through the preview's same-origin proxy, on the TEST-ONLY replay (APP_ENV=test +
// OUTCOME_REPLAY=1: each connection replays the recorded 2026-10-08 frames in real time, looping). When the socket is
// killed, the page shows the REST fallback's not-live answer and no number. Expected text is read from the server's own
// messages, never typed from memory.
import { test, expect, type Page, type WebSocketRoute } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const PAGE = '/market/underlying-index-view'

/** Intercepts the page's index socket: forwards everything, records the server's pushes, and can kill / refuse it. */
function socketControl(page: Page) {
  const ctl = { pushes: [] as any[], refuse: false, current: null as WebSocketRoute | null,
    server: null as WebSocketRoute | null }
  return {
    ctl,
    install: () => page.routeWebSocket('**/api/market/indices/live', (ws) => {
      if (ctl.refuse) {
        ws.close()
        return
      }
      ctl.current = ws
      const server = ws.connectToServer()
      ctl.server = server
      ws.onMessage((m) => server.send(m))
      server.onMessage((m) => {
        ctl.pushes.push(JSON.parse(String(m)))
        ws.send(m)
      })
    }),
    kill: async () => {
      ctl.refuse = true
      await ctl.server?.close()
      await ctl.current?.close()
      ctl.current = ctl.server = null
    },
  }
}

const nifty = (push: any) => push.indices.find((r: any) => r.underlying === 'NIFTY')

test('AC-2: two pushes with different times are shown as sent; a socket kill shows the not-live state, no number', async ({ page }) => {
  test.setTimeout(60000)
  const sock = socketControl(page)
  await sock.install()
  await page.goto(`${REPLAY_URL}${PAGE}`)
  const panel = page.getByTestId('index-panel-NIFTY')

  // 1. two LIVE pushes whose NIFTY time differs; the panel shows the latest pushed value exactly
  await expect.poll(() => new Set(sock.ctl.pushes.filter((p) => p.state === 'LIVE').map((p) => nifty(p).at)).size,
    { timeout: 20000 }).toBeGreaterThanOrEqual(2)
  const last = sock.ctl.pushes.at(-1)
  await expect(panel.getByTestId('index-value')).toHaveText(nifty(sock.ctl.pushes.at(-1)).value ?? 'Not available')
  expect(last.indices.map((r: any) => r.underlying)).toEqual(['NIFTY', 'SENSEX'])
  await expect(page.getByTestId('index-panel-SENSEX')).toBeVisible()

  // 2. a health word whenever the pushed health is not "available"; none when it is
  const health = nifty(sock.ctl.pushes.at(-1)).health
  if (health === 'available') await expect(panel.getByTestId('index-health')).toHaveCount(0)
  else await expect(panel.getByTestId('index-health')).toHaveText(health)

  // 3. kill the socket: the page asks REST with fallback=true and shows NOT_CONNECTED, no number on either panel
  const fallback = page.waitForResponse((r) => r.url().includes('/api/market/indices?') && r.url().includes('fallback=true'))
  await sock.kill()
  const answer = await (await fallback).json()
  expect(answer.state).toBe('NOT_CONNECTED')
  await expect(page.getByTestId('index-state')).toHaveText('Index values unavailable.')
  await expect(panel.getByTestId('index-value')).toHaveText('Not available')
  await expect(page.getByTestId('index-panel-SENSEX').getByTestId('index-value')).toHaveText('Not available')
})
