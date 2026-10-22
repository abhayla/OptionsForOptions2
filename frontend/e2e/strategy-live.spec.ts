// W-065 AC-4 (REQ-035 AC-4; ADR-068 (2), ADR-077, REQ-049 AC-5; ADR-008): the Strategy Builder's LTP and Unrealized
// P&L follow the server's pushes over /api/strategies/live, through the preview's same-origin proxy, on the TEST-ONLY
// replay (APP_ENV=test + OUTCOME_REPLAY=1: each connection replays the recorded 2026-10-08 frames in real time). When
// the socket is killed, the page shows the REST route's not-live answer (the server's AC-5 text with the last price
// time); when the socket is allowed back, pushes resume. Expected text is always read from the server's own messages.
// Each viewport project uses its own two legs, so the two projects (run in parallel) never release each other's legs,
// and no other spec uses these legs.
import { test, expect, type Page, type APIRequestContext, type WebSocketRoute } from '@playwright/test'
import { findClippedElements, describeClipped } from './clipping-check'
import { AC5 } from './support/ac5'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const CAPTURED_AT = '2026-10-08T09:20:09+05:30'
// NIFTY 13-Oct, 1 lot: desktop a 22850/22950 CE spread, mobile a 22750/22300 PE spread (legs that tick often in the recording)
const LEGS: Record<string, [string, string][]> = {
  'desktop-1280': [['NSE_FO:44626', 'SELL'], ['NSE_FO:44630', 'BUY']],
  'mobile-390': [['NSE_FO:44623', 'SELL'], ['NSE_FO:44599', 'BUY']],
}

/** The draft: each leg's planned entry is its LTP in the replay snapshot, read back from the REST route. */
async function draftFor(request: APIRequestContext, legs: [string, string][]) {
  const probe = { underlying: 'NIFTY', legs: legs.map(([instrument_id, action]) => ({ instrument_id, action, lots: 1, planned_entry: '100.00', captured_at: CAPTURED_AT })) }
  const res = await request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: probe })
  expect(res.ok(), await res.text()).toBeTruthy()
  const out = await res.json()
  // a retry may find the legs released by the previous attempt (REST not live then): fall back to the probe's own value
  return { underlying: 'NIFTY', legs: probe.legs.map((l, i) => ({ ...l, planned_entry: out.legs[i].ltp ?? '100.00' })) }
}

const cell = (page: Page, row: string, col: string) => page.locator(`[data-testid="cell"][data-row="${row}"][data-col="${col}"]`)
const display = (push: any, row: string, col: string) => push.table.rows.find((r: any) => r.row_id === row).cells[col].display

/** Intercepts the page's live socket: forwards everything, records the server's pushes, and can kill / refuse it. */
function socketControl(page: Page) {
  const ctl = { pushes: [] as any[], urls: [] as string[], refuse: false, current: null as WebSocketRoute | null, opened: 0,
    server: null as WebSocketRoute | null }
  return {
    ctl,
    install: () => page.routeWebSocket('**/api/strategies/live', (ws) => {
      ctl.urls.push(ws.url())
      if (ctl.refuse) {
        ws.close() // the browser sees its socket close (as when the network drops)
        return
      }
      ctl.opened += 1
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
      await ctl.server?.close() // the server side first (the API releases the legs), then the page's socket
      await ctl.current?.close()
      ctl.current = ctl.server = null
    },
  }
}

test('AC-4: LTP and Unrealized P&L change with the pushes; a socket kill shows the not-live label; reconnect resumes', async ({ page, request }, testInfo) => {
  test.setTimeout(60000)
  const legs = LEGS[testInfo.project.name]
  expect(legs, `no legs for project ${testInfo.project.name}`).toBeTruthy()
  const sock = socketControl(page)
  await sock.install()
  const draft = await draftFor(request, legs)
  await page.goto(`${REPLAY_URL}/strategy/builder?${new URLSearchParams({ draft: JSON.stringify(draft) })}`)
  const builder = page.getByTestId('strategy-builder')

  // 1. three pushes, each shown exactly as the server sent it: the LTP and P&L cells follow, and they change
  await expect.poll(() => sock.ctl.pushes.length, { timeout: 15000 }).toBeGreaterThanOrEqual(4)
  await expect(builder).toHaveAttribute('data-live', 'live')
  const shownLtp: string[] = []
  const shownPnl: string[] = []
  for (let k = 0; k < 3; k++) {
    const n = sock.ctl.pushes.length
    await expect.poll(() => sock.ctl.pushes.length, { timeout: 5000 }).toBeGreaterThan(n)
    const p = sock.ctl.pushes.at(-1)
    expect(p.state).toBe('COMPUTED')
    // the page may already show a newer push; read both cells and accept only text some push carried for that row
    await expect(cell(page, '1', 'ltp')).toHaveText(display(p, '1', 'ltp'), { timeout: 1500 }).catch(() => {})
    const ltp = (await cell(page, '1', 'ltp').textContent())!.trim()
    const pnl = (await cell(page, 'TOTAL', 'unrealized_pnl').textContent())!.trim()
    expect(sock.ctl.pushes.map((q) => display(q, '1', 'ltp'))).toContain(ltp)
    expect(sock.ctl.pushes.map((q) => display(q, 'TOTAL', 'unrealized_pnl'))).toContain(pnl)
    shownLtp.push(ltp)
    shownPnl.push(pnl)
  }
  const pushedLtp = new Set(sock.ctl.pushes.map((q) => display(q, '1', 'ltp')))
  const pushedPnl = new Set(sock.ctl.pushes.map((q) => display(q, 'TOTAL', 'unrealized_pnl')))
  expect(pushedLtp.size, [...pushedLtp].join(' | ')).toBeGreaterThanOrEqual(3)
  expect(pushedPnl.size, [...pushedPnl].join(' | ')).toBeGreaterThanOrEqual(3)
  expect(new Set([...shownLtp, ...shownPnl]).size).toBeGreaterThan(2) // the screen itself changed, not only the wire
  // no credential or query string on the socket URL; it is the page's own origin
  for (const u of sock.ctl.urls) expect(u).toBe(`${REPLAY_URL.replace(/^http/, 'ws')}/api/strategies/live`)
  expect(await findClippedElements(page), describeClipped('/strategy/builder live', page.viewportSize()!.width, await findClippedElements(page))).toEqual([])

  // 2. kill the socket and refuse reconnects: the REST answer is shown, with the server's not-live label (AC-5 + time).
  // Each drop (the kill, then each refused retry) asks REST; the API may still be closing the old socket when the first
  // one arrives, so wait for the first not-live answer rather than assume it is the first answer.
  const restAnswers: any[] = []
  page.on('response', async (r) => {
    if (r.url().endsWith('/api/strategies/outcome') && r.request().method() === 'POST') restAnswers.push(await r.json())
  })
  await sock.kill()
  await expect.poll(() => restAnswers.some((a) => a.state === 'NOT_CONNECTED'), { timeout: 10000 }).toBe(true)
  const rest = restAnswers.find((a) => a.state === 'NOT_CONNECTED')
  expect(rest.status_label).toMatch(AC5)
  await expect(builder).toHaveAttribute('data-state', 'not-connected')
  await expect(page.getByTestId('status-label')).toHaveText(rest.status_label)
  await expect(builder).toHaveAttribute('data-live', 'down')
  await expect(page.getByTestId('strategy-table')).toHaveCount(0) // no number shown as live (REQ-049 AC-4)
  // ADR-086 item 1 (W-073): the not-live answer names each known contract, so a `draft` query leg shows its name, never
  // the fixed "unavailable" wording and never its instrument id
  await expect(page.getByTestId('draft-legs')).toContainText('NIFTY')
  await expect(page.getByTestId('draft-legs')).not.toContainText('Contract details not available')
  await expect(page.getByTestId('draft-legs')).not.toContainText(draft.legs[0].instrument_id)
  expect(await findClippedElements(page), describeClipped('/strategy/builder not-live', page.viewportSize()!.width, await findClippedElements(page))).toEqual([])

  // 3. allow the socket back: the next backoff attempt reconnects, the strategy is sent again, pushes resume
  const before = sock.ctl.pushes.length
  const opened = sock.ctl.opened
  sock.ctl.refuse = false
  await expect.poll(() => sock.ctl.opened, { timeout: 20000 }).toBeGreaterThan(opened)
  await expect.poll(() => sock.ctl.pushes.length, { timeout: 10000 }).toBeGreaterThan(before + 1)
  await expect(builder).toHaveAttribute('data-live', 'live')
  await expect(builder).toHaveAttribute('data-state', 'computed')
  const latest = sock.ctl.pushes.map((q) => display(q, '1', 'ltp'))
  expect(latest).toContain((await cell(page, '1', 'ltp').textContent())!.trim())
})

test('AC-4 two holders (ADR-077): another socket holds the same legs, this page\'s socket is killed - the page shows the not-live message, never live numbers', async ({ page, context, request }, testInfo) => {
  test.setTimeout(60000)
  const legs = LEGS[testInfo.project.name]
  const sock = socketControl(page)
  await sock.install()
  const draft = await draftFor(request, legs)
  // another browser tab / user: a second socket on the same origin subscribes to the same contracts and stays open
  const other = await context.newPage()
  await other.goto(`${REPLAY_URL}/health`)
  const otherFirst = await other.evaluate((body) => new Promise<string>((resolve, reject) => {
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/strategies/live`)
    ;(window as any).__otherSocket = ws
    ws.onopen = () => ws.send(JSON.stringify(body))
    ws.onmessage = (ev) => resolve(String(ev.data))
    ws.onerror = () => reject(new Error('second socket failed'))
  }), { ...draft, ux_level: 'standard' })
  expect(JSON.parse(otherFirst).state).toBe('COMPUTED') // the second holder is really streaming these legs

  await page.goto(`${REPLAY_URL}/strategy/builder?${new URLSearchParams({ draft: JSON.stringify(draft) })}`)
  const builder = page.getByTestId('strategy-builder')
  await expect(builder).toHaveAttribute('data-live', 'live')
  await expect(builder).toHaveAttribute('data-state', 'computed')

  const restBodies: any[] = []
  const restAnswers: any[] = []
  // Only answers to requests this listener saw being sent count: a non-fallback refresh the page sent before the
  // listener attached can be answered after it, and the server (correctly) answers that one COMPUTED while the other
  // socket still holds the legs (log: ["COMPUTED","NOT_CONNECTED"]). Every request seen is still asserted fallback=true.
  const seenRequests = new Set<unknown>()
  page.on('request', (r) => {
    if (r.url().endsWith('/api/strategies/outcome') && r.method() === 'POST') {
      restBodies.push(r.postDataJSON())
      seenRequests.add(r)
    }
  })
  page.on('response', async (r) => {
    if (seenRequests.has(r.request())) restAnswers.push(await r.json())
  })
  await sock.kill()
  await expect.poll(() => restAnswers.length, { timeout: 10000 }).toBeGreaterThan(0)
  await expect(builder).toHaveAttribute('data-state', 'not-connected')
  await expect(builder).toHaveAttribute('data-live', 'down')
  await expect(page.getByTestId('status-label')).toHaveText(AC5)
  await expect(page.getByTestId('strategy-table')).toHaveCount(0) // no number shown as live (REQ-049 AC-4)
  // every refresh after the drop said so, and every answer was the not-live one, though the other socket still holds the legs
  expect(restBodies.length).toBeGreaterThan(0)
  expect(restBodies.every((b) => b.fallback === true), JSON.stringify(restBodies.map((b) => b.fallback))).toBe(true)
  expect(restAnswers.every((a) => a.state === 'NOT_CONNECTED' && a.table == null), JSON.stringify(restAnswers.map((a) => a.state))).toBe(true)
  expect(await findClippedElements(page), describeClipped('/strategy/builder two holders', page.viewportSize()!.width, await findClippedElements(page))).toEqual([])
  await other.evaluate(() => (window as any).__otherSocket.close())
})
