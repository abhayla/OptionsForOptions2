// W-113 AC-5 (REQ-049 AC-4..6; ADR-077, ADR-008): the Live Strategies page follows a SAVED strategy on the platform socket
// and shows the server's pushes (with a changing spot_at), then the server's own not-live answer when the socket drops.
//
// Servers (as in CI): the replay preview (REPLAY_URL, API with OUTCOME_REPLAY=1) serves the page and the live socket from
// the recorded 2026-10-08 frames. The strategy is SAVED through the pinned-catalogue API (SAVE_DRAFT_URL, seeded with the
// recorded instrument list), because the replay API's catalogue sees today's date; the page's catalogue calls are answered
// from that same pinned API, and its strategy list is narrowed to this test's own strategy (other specs' drafts would
// otherwise hold the same legs on the replay). Nothing is faked: every body is a real API answer.
// Each viewport project saves its own two legs so the two projects (run in parallel) never release each other's legs.
import { test, expect, type Page, type APIRequestContext, type WebSocketRoute } from '@playwright/test'
import { AC5 } from './support/ac5'

test.skip(!process.env.SAVE_DRAFT_URL, 'needs the pinned-catalogue API (SAVE_DRAFT_URL): CI sets it; a developer PC points it at a pinned API')

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const PINNED_URL = process.env.SAVE_DRAFT_URL || ''
const EXPIRY = '2026-10-13'
const CAPTURED_AT = '2026-10-08T09:20:09+05:30'
const TAG = 'e2e_w113_live_strategies'
const LEGS: Record<string, [number, string][]> = {
  'desktop-1280': [[44626, 'SELL'], [44630, 'BUY']],
  'mobile-390': [[44623, 'SELL'], [44599, 'BUY']],
}

async function saveStrategy(request: APIRequestContext, legs: [number, string][]): Promise<number> {
  const cat = await (await request.get(`${PINNED_URL}/api/catalogue/NIFTY/contracts?expiry=${EXPIRY}`)).json()
  const body = {
    underlying: 'NIFTY',
    rules_ref: TAG,
    legs: legs.map(([token, action]) => {
      const c = cat.contracts.find((x: any) => x.exchange_token === token)
      expect(c, `token ${token} is in the pinned catalogue`).toBeTruthy()
      return { contract_id: c.contract_id, action, quantity: c.lot_size, planned_entry: '100.00', captured_at: CAPTURED_AT }
    }),
  }
  const res = await request.post(`${PINNED_URL}/api/strategies`, { data: body })
  expect(res.ok(), await res.text()).toBeTruthy()
  return (await res.json()).id
}

async function narrowPage(page: Page, request: APIRequestContext, id: number) {
  await page.route('**/api/catalogue/**', async (route) => {
    const u = new URL(route.request().url())
    route.fulfill({ response: await request.get(`${PINNED_URL}${u.pathname}${u.search}`) })
  })
  await page.route('**/api/strategies', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const real = await request.get(`${PINNED_URL}/api/strategies`)
    const all = await real.json()
    route.fulfill({ json: { strategies: all.strategies.filter((s: any) => s.id === id) } })
  })
  // the page's saved-strategy reads go to the pinned API too (the replay API has its own, different, user rows)
  await page.route(new RegExp(`/api/strategies/${id}$`), async (route) => {
    route.fulfill({ response: await request.get(`${PINNED_URL}/api/strategies/${id}`) })
  })
}

/** Forwards the page's live socket to the replay API, records the server's pushes, and can kill / refuse it. */
function socketControl(page: Page) {
  const ctl = { pushes: [] as any[], refuse: false, current: null as WebSocketRoute | null, server: null as WebSocketRoute | null }
  return {
    ctl,
    install: () => page.routeWebSocket('**/api/strategies/live', (ws) => {
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
    },
  }
}

test('AC-5: a saved strategy shows pushes with different spot_at, then the server\'s not-live message when the socket drops', async ({ page, request }, testInfo) => {
  test.setTimeout(90000)
  const legs = LEGS[testInfo.project.name]
  expect(legs, `no legs for project ${testInfo.project.name}`).toBeTruthy()
  const id = await saveStrategy(request, legs)
  const sock = socketControl(page)
  await sock.install()
  await narrowPage(page, request, id)
  await page.goto(`${REPLAY_URL}/strategies/live-strategies`)
  const card = page.getByTestId('live-strategy-card')
  await expect(card).toHaveCount(1)

  // 1. pushes arrive and the card shows what the server sent: the exact spot_level text, and the push times differ
  await expect.poll(() => sock.ctl.pushes.length, { timeout: 20000 }).toBeGreaterThanOrEqual(2)
  await expect.poll(() => new Set(sock.ctl.pushes.map((p) => p.spot_at)).size, { timeout: 30000 }).toBeGreaterThanOrEqual(2)
  expect(sock.ctl.pushes.every((p) => p.state === 'COMPUTED')).toBe(true)
  const shownSpot = (await card.getByTestId('live-spot').textContent())!.trim()
  expect(sock.ctl.pushes.map((p) => p.spot_level)).toContain(shownSpot)
  await expect(card.getByTestId('live-paused-badge')).toHaveCount(0)

  // 2. kill the socket and refuse reconnects: the card shows the REST route's not-live label, the server's text
  const restAnswers: any[] = []
  page.on('response', async (r) => {
    if (r.url().endsWith('/api/strategies/outcome') && r.request().method() === 'POST') restAnswers.push(await r.json())
  })
  await sock.kill()
  // every leg of the saved strategy has a planned entry, so (REQ-077 AC-9) the answer is FROM_ENTRIES: AC-5's message and
  // the from-your-prices label, both the server's text, and no live number
  await expect.poll(() => restAnswers.some((a) => a.state === 'FROM_ENTRIES'), { timeout: 15000 }).toBe(true)
  const rest = restAnswers.find((a) => a.state === 'FROM_ENTRIES')
  expect(rest.status_label).toMatch(AC5)
  expect(rest.output_label).toBeTruthy()
  expect(rest.legs.every((l: any) => l.ltp == null)).toBe(true)
  await expect(card.getByTestId('live-status-label')).toHaveText(rest.status_label)
  await expect(card.getByTestId('live-output-label')).toHaveText(rest.output_label)
  await expect(card.getByTestId('live-paused-badge')).toBeVisible()
  await expect(card.getByTestId('live-health-dot')).toContainText('Health unknown')
  await expect(card.getByTestId('live-spot')).toHaveCount(0) // no number shown as live (REQ-049 AC-4)
})

test('REQ-049 AC-5 twin: a saved strategy with no planned entry on any leg is never followed: unpriced label, paused, no socket, no figure', async ({ page, request }, testInfo) => {
  // The card sends only legs that carry a planned entry (buildDraft), so NOT_CONNECTED for "a leg without an entry" cannot
  // be reached from the card; what it really shows is the unpriced state with the not-connected draft label and a paused badge.
  const legs = LEGS[testInfo.project.name]
  const cat = await (await request.get(`${PINNED_URL}/api/catalogue/NIFTY/contracts?expiry=${EXPIRY}`)).json()
  const res = await request.post(`${PINNED_URL}/api/strategies`, { data: { underlying: 'NIFTY', rules_ref: TAG, legs: legs.map(([token, action]) => {
    const c = cat.contracts.find((x: any) => x.exchange_token === token)
    expect(c, `token ${token} is in the pinned catalogue`).toBeTruthy()
    return { contract_id: c.contract_id, action, quantity: c.lot_size }
  }) } })
  expect(res.ok(), await res.text()).toBeTruthy()
  const id = (await res.json()).id
  const sock = socketControl(page)
  await sock.install()
  await narrowPage(page, request, id)
  await page.goto(`${REPLAY_URL}/strategies/live-strategies`)
  const card = page.getByTestId('live-strategy-card')
  await expect(card).toHaveCount(1)
  await expect(card).toHaveAttribute('data-state', 'unpriced')
  await expect(card.getByTestId('live-status-label')).toBeVisible()
  await expect(card.getByTestId('live-paused-badge')).toBeVisible()
  await expect(card.getByTestId('live-health-dot')).toContainText('Health unknown')
  await expect(card.getByTestId('live-spot')).toHaveCount(0)
  expect(sock.ctl.pushes).toEqual([])
})

test('REQ-077 AC-9 twin: a saved strategy with one priced leg and one unpriced leg is never followed: unpriced, paused, no socket, no figure', async ({ page, request }, testInfo) => {
  // The card's draft is null when any leg has no planned entry, so the priced leg's own figures are never shown as the strategy's.
  const legs = LEGS[testInfo.project.name]
  const cat = await (await request.get(`${PINNED_URL}/api/catalogue/NIFTY/contracts?expiry=${EXPIRY}`)).json()
  const res = await request.post(`${PINNED_URL}/api/strategies`, { data: { underlying: 'NIFTY', rules_ref: TAG, legs: legs.map(([token, action], i) => {
    const c = cat.contracts.find((x: any) => x.exchange_token === token)
    expect(c, `token ${token} is in the pinned catalogue`).toBeTruthy()
    return i === 0 ? { contract_id: c.contract_id, action, quantity: c.lot_size, planned_entry: '100.00', captured_at: CAPTURED_AT }
      : { contract_id: c.contract_id, action, quantity: c.lot_size }
  }) } })
  expect(res.ok(), await res.text()).toBeTruthy()
  const id = (await res.json()).id
  const sock = socketControl(page)
  await sock.install()
  await narrowPage(page, request, id)
  await page.goto(`${REPLAY_URL}/strategies/live-strategies`)
  const card = page.getByTestId('live-strategy-card')
  await expect(card).toHaveCount(1)
  await expect(card).toHaveAttribute('data-state', 'unpriced')
  await expect(card.getByTestId('live-paused-badge')).toBeVisible()
  await expect(card.getByTestId('live-spot')).toHaveCount(0)
  expect(sock.ctl.pushes).toEqual([])
})
