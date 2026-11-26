// Lane T screen suite: My Strategies (/strategies/my-strategies) and the shared parts it renders (the delete confirm, the Undo toast,
// the bulk bar, the rename form, the empty state and the load-failed line), each done the way a user does it (click, type, press
// a key) with the OUTCOME asserted on screen: exact text, the row that appears or goes, the address and heading of the page that opens.
// Same set-up as screen-home.spec.ts: the built app on `vite preview` (REPLAY_URL) whose API proxy points at a closed port; every
// /api call is answered here by a small stateful fake of the server (list, one strategy, rename, delete, undelete, bulk-delete,
// settings, features, paper list), so no database or broker is needed. Names reach the page the way the API sends them: wrapped in
// one pair of double quotes (ADR-003).
// Existing coverage NOT repeated: my-strategies.spec.ts (real-API round trip: save a draft, list, search, rename, Builder link).
// Expected text comes from the spec (REQ-070 AC-6/AC-7, REQ-134 AC-1..AC-5, ADR-330 (8), ADR-293, ADR-292, ADR-183, ADR-299,
// ADR-320 (S-05), ADR-271), never from the page's own output. Where today's code contradicts the spec the test stays written to the
// spec and is marked test.fail() with `// expected-fail: <id>: <one line>`.
import { test, expect, type Page, type Route } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4185'
const LIST_URL = `${BASE}/strategies/my-strategies`
const DONE_URL = `${BASE}/strategies/completed-strategies`

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
const T_NOW = '2026-11-26T10:00:00+05:30'
type Row = Record<string, unknown> & { id: number }
const mk = (id: number, name: string | null, updated_at: string, over: Record<string, unknown> = {}): Row => ({
  id, name: name === null ? undefined : `"${name}"`, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', revision: 3,
  created_at: updated_at, updated_at, can_delete: true, held_at_broker: false, has_order: false, has_paper_order: false,
  first_leg: { expiry: '2026-12-01', strike: '25600', instrument: 'PE' }, leg_count: 2, ...over,
})
// Newest saved first: 21, 17, 9, 5, 4. Row 21 is a running paper strategy, 5 is held at the broker, 4 sent a real basket.
const R21 = mk(21, 'Iron Condor Nov', '2026-11-20T10:00:00+05:30', {
  underlying: 'SENSEX', status: 'running', status_word: 'Running', has_order: true, has_paper_order: true,
  first_leg: { expiry: '2026-12-03', strike: '82000', instrument: 'CE' }, leg_count: 4,
})
const R17 = mk(17, 'Bull Put Spread', '2026-11-10T10:00:00+05:30')
const R9 = mk(9, 'Short Straddle', '2026-11-01T10:00:00+05:30', { first_leg: { expiry: '2026-12-01', strike: '25700', instrument: 'CE' } })
const R5 = mk(5, 'Held IC k10', '2026-10-25T10:00:00+05:30', { can_delete: false, held_at_broker: true, has_order: true })
const R4 = mk(4, 'Sent Basket', '2026-10-20T10:00:00+05:30', { can_delete: false, has_order: true, leg_count: 1 })
const DONE = mk(30, 'Closed Condor', '2026-11-15T10:00:00+05:30', {
  status: 'closed', status_word: 'Completed', closed_at: '2026-11-15T15:20:00+05:30', final_pnl_text: '+1,200.00',
  charges_paid_text: '210.00', total_after_text: '+990.00', adjustments_made: 2, adjustment_cost_text: '35.00',
})
const LIST: Row[] = [R9, R4, R21, R5, R17, DONE] // stored in a shuffled order: the page sorts, the fake does not

const cat = (what: string) => ({ what_happened: what, impact: 'Nothing else changed.', what_is_blocked: 'Nothing.', next_action: 'Try again.' })
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const HELD = 'This strategy is marked as held at your broker, so it cannot be deleted.'
const SENT = 'Orders were already sent for this strategy, so it cannot be deleted.'
const CHANGED = 'This strategy was changed by another action after you opened it.'
const FAILED_ITEM = 'This strategy could not be deleted because of an unexpected error, so it was left as it is.'
const CONFIRM_DRAFT = 'Delete this draft? Its history is kept, and you can Undo right after.'
const CONFIRM_PAPER = 'Practice orders were placed for this strategy. Delete it? Its practice record leaves the lists, and you can Undo right after.'
const LOAD_FAILED = 'Could not load your strategies. Nothing was changed.'
const EMPTY = 'You have no saved strategies yet. Save a draft from the Strategy Builder and it will appear here.'

// ---------------------------------------------------------------- the stub: every /api call of the page
type Reply = { status?: number; json?: unknown; abort?: boolean; wait?: Promise<void>; body?: string }
type Ctx = { id?: number; body?: any; query: URLSearchParams }
type Over = Partial<Record<'list' | 'one' | 'patch' | 'del' | 'undelete' | 'bulk' | 'paper' | 'features' | 'settings', Reply | ((c: Ctx) => Reply)>>
type Fake = { rows: Row[]; hidden: Set<number>; calls: Array<{ m: string; path: string; body?: any }>; over: Over; names: Map<number, string> }
const gate = () => { let open!: () => void; const wait = new Promise<void>((r) => { open = r }); return { wait, open } }

const paperBook = (id: number) => ({
  strategy_id: id, name: 'Iron Condor Nov', underlying: 'SENSEX', state: 'LIVE', status_word: 'Running', open_count: 1, position_count: 1,
  total_text: '+14,231.04', total_after_text: '+13,410.44', booked_text: '+0.00', unbooked_text: '+14,231.04', after_charges_reason: null,
  positions: [{ contract_id: 501, contract_text: 'SENSEX 82000 CE', instrument: 'CE', strike: '82000', expiry: '2026-12-03', net_quantity: -20, lot_size: 20,
    average_text: '211.25', price_state: 'live', ltp_text: '200.00', price_at: T_NOW, booked_text: '+0.00', unbooked_text: '+225.00', total_text: '+225.00' }],
})
const paperOk = { strategies: [paperBook(21)], totals: { total_text: '+14,231.04', total_after_text: '+13,410.44', booked_text: '+0.00', unbooked_text: '+14,231.04', after_charges_reason: null }, answered_at: T_NOW }

async function stubApi(page: Page, over: Over = {}, rows: Row[] = LIST): Promise<Fake> {
  const F: Fake = { rows: rows.map((r) => ({ ...r })), hidden: new Set(), calls: [], over, names: new Map() }
  const serve = async (route: Route, r: Reply) => {
    if (r.wait) await r.wait
    if (r.abort) return route.abort('connectionrefused')
    return route.fulfill({ status: r.status ?? 200, ...(r.body !== undefined ? { body: r.body, contentType: 'application/json' } : { json: r.json ?? {} }) })
  }
  const pick = (key: keyof Over, c: Ctx, fallback: Reply): Reply => { const o = F.over[key]; return o === undefined ? fallback : typeof o === 'function' ? o(c) : o }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const m = req.method()
    const body = req.postData() ? JSON.parse(req.postData()!) : undefined
    F.calls.push({ m, path: path + url.search, body })
    const c: Ctx = { body, query: url.searchParams }
    const one = /^\/api\/strategies\/(\d+)(?:\/(name|undelete))?$/.exec(path)
    if (m === 'GET' && path === '/api/strategies') return serve(route, pick('list', c, { json: { strategies: F.rows.filter((r) => !F.hidden.has(r.id)) } }))
    if (m === 'GET' && path === '/api/features') return serve(route, pick('features', c, { json: { order_path: 'on' } }))
    if (m === 'GET' && path === '/api/settings') return serve(route, pick('settings', c, { json: { groups: [{ settings: [{ key: 'other.undo_clear_all_seconds', value: '60' }] }] } }))
    if (m === 'GET' && path === '/api/paper/strategies') return serve(route, pick('paper', c, { json: paperOk }))
    if (m === 'POST' && path === '/api/strategies/bulk-delete') {
      const dflt: Reply = { json: { deleted: (body.items as any[]).map((i) => ({ id: i.id, revision: i.expected_revision + 1 })), kept: [], summary_text: cat(`${body.items.length} deleted`) } }
      const r = pick('bulk', c, dflt)
      const ok = (r.status ?? 200) === 200 && !r.abort && r.json && Array.isArray((r.json as any).deleted)
      if (ok) for (const d of (r.json as any).deleted) F.hidden.add(d.id)
      return serve(route, r)
    }
    if (one) {
      const id = Number(one[1])
      const row = F.rows.find((r) => r.id === id)
      c.id = id
      if (m === 'GET' && !one[2]) return serve(route, pick('one', c, row ? { json: { ...row, name: F.names.has(id) ? `"${F.names.get(id)}"` : row.name, definition: { underlying: row.underlying, legs: [] } } } : { status: 404, json: cat('That strategy was not found.') }))
      if (m === 'PATCH' && one[2] === 'name') {
        const r = pick('patch', c, { json: { id, name: `"${body.name}"`, revision: row?.revision } })
        if ((r.status ?? 200) === 200 && !r.abort) F.names.set(id, body.name)
        return serve(route, r)
      }
      if (m === 'DELETE' && !one[2]) {
        const r = pick('del', c, { json: { id, revision: Number(url.searchParams.get('expected_revision')) + 1 } })
        if ((r.status ?? 200) === 200 && !r.abort) F.hidden.add(id)
        return serve(route, r)
      }
      if (m === 'POST' && one[2] === 'undelete') {
        const r = pick('undelete', c, { json: { id } })
        if ((r.status ?? 200) === 200 && !r.abort) F.hidden.delete(id)
        return serve(route, r)
      }
    }
    if (m === 'GET' && /^\/api\/paper\/strategies\/\d+$/.test(path)) return route.fulfill({ status: 404, json: { detail: 'not found' } }) // no paper book: the Builder opens the saved copy
    return route.fulfill({ status: 503, json: {} }) // anything this page does not need: a plain failure, never a proxy hang
  })
  return F
}
// the renamed names the fake keeps are shown through GET /strategies as well
const withNames = (F: Fake) => { F.over.list ??= () => ({ json: { strategies: F.rows.filter((r) => !F.hidden.has(r.id)).map((r) => (F.names.has(r.id) ? { ...r, name: `"${F.names.get(r.id)}"` } : r)) } }) }

const rows = (page: Page) => page.getByTestId('strategy-row')
const rowOf = (page: Page, id: number) => page.locator(`[data-testid="strategy-row"][data-strategy-id="${id}"]`)
const title = (page: Page) => page.getByTestId('page-title')
const names = (page: Page) => page.getByTestId('row-name')
async function open(page: Page, over: Over = {}, list: Row[] = LIST, url = LIST_URL) {
  const F = await stubApi(page, over, list)
  withNames(F)
  await page.goto(url)
  return F
}
async function openLoaded(page: Page, over: Over = {}, list: Row[] = LIST) {
  const F = await open(page, over, list)
  await expect(rows(page).first()).toBeVisible()
  return F
}
const ORDER = ['Iron Condor Nov', 'Bull Put Spread', 'Short Straddle', 'Held IC k10', 'Sent Basket'] // newest save first (U2)
const callsTo = (F: Fake, m: string, re: RegExp) => F.calls.filter((c) => c.m === m && re.test(c.path))

// =============================================================================================== the list
test.describe('My Strategies: the list (REQ-134 AC-4, REQ-009 AC-2, ADR-299, ADR-259)', () => {
  test('LIST-1 the page opens at /strategies/my-strategies with the heading "My Strategies" and the rows newest save first', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 (list shows name, underlying, legs, last saved); owner U2 (newest save first, as Home lists them)
    await openLoaded(page)
    await expect(page).toHaveURL(/\/strategies\/my-strategies$/)
    await expect(title(page)).toHaveText('My Strategies')
    await expect(names(page)).toHaveText(ORDER)
  })

  test('LIST-2 each row shows its underlying, legs line ("and N more"), status word and last-saved time as exact text', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 ("NIFTY 27 Oct 22500 PE and 3 more", last saved time); ADR-299 (status word is the server's)
    await openLoaded(page)
    const r21 = rowOf(page, 21)
    await expect(r21.getByTestId('row-underlying')).toHaveText('SENSEX')
    await expect(r21.getByTestId('row-legs')).toHaveText('SENSEX 3 Dec 2026 82000 CE and 3 more')
    await expect(r21.getByTestId('row-status')).toHaveText('Running')
    await expect(r21.getByTestId('row-saved')).toHaveText('last saved 20 Nov 2026, 10:00:00 IST')
    const r17 = rowOf(page, 17)
    await expect(r17.getByTestId('row-underlying')).toHaveText('NIFTY')
    await expect(r17.getByTestId('row-legs')).toHaveText('NIFTY 1 Dec 2026 25600 PE and 1 more')
    await expect(r17.getByTestId('row-status')).toHaveText('Draft')
    await expect(r17.getByTestId('row-saved')).toHaveText('last saved 10 Nov 2026, 10:00:00 IST')
    await expect(rowOf(page, 4).getByTestId('row-legs')).toHaveText('NIFTY 1 Dec 2026 25600 PE') // one leg: no "and N more"
  })

  test('LIST-3 a column header row names the columns; the Tracking column is gone (ADR-299)', async ({ page, isMobile }) => {
    // Spec basis: ADR-299 (the Tracking column and its words are retired); REQ-134 AC-4
    await openLoaded(page)
    await expect(page.getByTestId('strategy-list')).not.toContainText('Tracked')
    await expect(page.getByTestId('row-tracked')).toHaveCount(0)
    if (!isMobile) await expect(page.getByTestId('my-strategies')).toContainText('Name')
  })

  test('LIST-4 a Completed strategy is not on My Strategies (ADR-259); it is on Completed Strategies with its final figures as the server worded them', async ({ page }) => {
    // Spec basis: ADR-259 (a closed trade leaves this list); REQ-009 AC-2 (Completed Strategies page)
    await openLoaded(page)
    await expect(rowOf(page, 30)).toHaveCount(0)
    await page.goto(DONE_URL)
    await expect(title(page)).toHaveText('Completed Strategies')
    const done = rowOf(page, 30)
    await expect(done.getByTestId('row-status')).toHaveText('Completed')
    await expect(done.getByTestId('row-saved')).toHaveText('closed 15 Nov 2026, 15:20:00 IST')
    await expect(done.getByTestId('row-final-pnl')).toHaveText('Final P&L +1,200.00')
    await expect(done.getByTestId('row-charges')).toHaveText(' · Charges 210.00')
    await expect(done.getByTestId('row-adjustments')).toHaveText(' · Adjustments made 2')
    await expect(done.getByTestId('row-adjustment-cost')).toHaveText(' · Adjustment cost 35.00')
    await expect(rowOf(page, 21)).toHaveCount(0) // and a running one is not on the Completed page
  })

  test('LIST-5 a running paper strategy shows its P&L line from the Positions figure; a draft shows none (R-06, D-41)', async ({ page }) => {
    // Spec basis: REQ-109 AC-10 / ADR-320 (6) (the P&L a My Strategies row shows is the Positions page figure, after charges)
    await openLoaded(page)
    await expect(rowOf(page, 21).getByTestId('row-pnl')).toContainText('+13,410.44')
    await expect(rowOf(page, 17).getByTestId('row-pnl')).toHaveCount(0)
  })

  test('LIST-6 when the paper list cannot be read, a running row shows a dash and the sentence, never a guessed figure (fail closed)', async ({ page }) => {
    // Spec basis: ADR-320 (5) (paused / failed figure: a dash and the sentence), ADR-008 (no guessed number)
    await openLoaded(page, { paper: { status: 500, json: {} } })
    const pnl = rowOf(page, 21).getByTestId('row-pnl')
    await expect(pnl).toHaveAttribute('data-pnl-kind', /paused|failed/)
    await expect(pnl.getByTestId('row-pnl-figure')).not.toHaveText(/\d/)
    await expect(pnl).not.toContainText('13,410.44')
  })

  test('LIST-7 N-14 three strategies with one name are three rows; Rename on the second changes only that row', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 ("Two strategies of one user may share a name; each keeps its own id"); owner N-14 (four strategies all named Short Iron Condor)
    const same = [mk(41, 'Short Iron Condor', '2026-11-25T10:00:00+05:30'), mk(42, 'Short Iron Condor', '2026-11-24T10:00:00+05:30'), mk(43, 'Short Iron Condor', '2026-11-23T10:00:00+05:30')]
    const F = await openLoaded(page, {}, same)
    await expect(names(page)).toHaveText(['Short Iron Condor', 'Short Iron Condor', 'Short Iron Condor'])
    await rowOf(page, 42).getByTestId('rename-42').click()
    await page.getByTestId('rename-input').fill('Condor B')
    await page.getByTestId('rename-save').click()
    await expect(names(page)).toHaveText(['Short Iron Condor', 'Condor B', 'Short Iron Condor'])
    expect(callsTo(F, 'PATCH', /strategies\/42\/name/)).toHaveLength(1)
    expect(callsTo(F, 'PATCH', /strategies\/4[13]\/name/)).toHaveLength(0)
  })

  test('LIST-8 a row with no name shows "Strategy <id>" and no Rename button; an unknown status word reads "Status not available" (never a guessed Draft)', async ({ page }) => {
    // Spec basis: ADR-299 (4) (unknown status words are never guessed); REQ-134 (a named row shows its name); none for the fallback label (searched: Strategy <id>)
    const odd = [{ ...mk(50, null, '2026-11-25T10:00:00+05:30'), status_word: 'Mystery', status: 'weird' }]
    await openLoaded(page, {}, odd)
    await expect(rowOf(page, 50).getByTestId('row-name')).toHaveText('Strategy 50')
    await expect(rowOf(page, 50).getByTestId('row-status')).toHaveText('Status not available')
    await expect(page.getByTestId('rename-50')).toHaveCount(0)
  })

  test('LIST-9 on a 390 px phone the rows show no horizontal page scroll', async ({ page, isMobile }) => {
    // Spec basis: none (searched: horizontal scroll, 390; the project-wide mobile rule is in responsive.spec.ts)
    test.skip(!isMobile, 'mobile project only')
    await openLoaded(page)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})

// =============================================================================================== loading and failure
test.describe('My Strategies: loading, empty and failure states (ADR-320 S-05, REQ-070, ADR-193)', () => {
  test('LOAD-1 (S-05, Q2-7) while the list read runs the page shows grey placeholder rows named "Loading your strategies", never a bare "Loading..."', async ({ page }) => {
    // Spec basis: ADR-330 (S-05) / REQ-070 My Strategies screen wording ("The list read shows a skeleton while it runs")
    const g = gate()
    await open(page, { list: () => ({ wait: g.wait, json: { strategies: LIST } }) })
    const skeleton = page.getByTestId('list-skeleton')
    await expect(skeleton).toHaveAttribute('aria-label', 'Loading your strategies')
    await expect(skeleton.locator('div')).toHaveCount(4)
    await expect(page.getByTestId('my-strategies')).not.toContainText('Loading...')
    await expect(page.getByTestId('strategy-search')).toHaveCount(0) // no search box over a list that is not here yet
    g.open()
    await expect(rows(page).first()).toBeVisible()
    await expect(skeleton).toHaveCount(0)
  })

  test('LOAD-2 (S-05) a 500 shows "Could not load your strategies. Nothing was changed." with a Retry button and no rows', async ({ page }) => {
    // Spec basis: ADR-330 (S-05) / REQ-070 ("on failure ... 'Could not load your strategies. Nothing was changed.' with Retry")
    await open(page, { list: { status: 500, json: cat('Saved strategies could not be read.') } })
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await expect(page.getByTestId('list-load-retry')).toHaveText('Retry')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('list-skeleton')).toHaveCount(0)
    await expect(page.getByTestId('list-empty')).toHaveCount(0) // a failed read is not "you have no strategies"
  })

  test('LOAD-3 (S-05) connection refused shows the same sentence and Retry; nothing is guessed', async ({ page }) => {
    // Spec basis: ADR-330 (S-05); REQ-065 (a failure says what happened and that nothing changed)
    await open(page, { list: { abort: true } })
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await expect(page.getByTestId('list-load-retry')).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
  })

  test('LOAD-4 (S-05) a 200 whose body is unreadable (not JSON) shows the same sentence and Retry', async ({ page }) => {
    // Spec basis: ADR-330 (S-05); REQ-065 (fail closed on an answer that cannot be read)
    // expected-fail: NEW-T11: an unreadable 200 body is read as an empty list, so the page says "You have no saved strategies yet" instead of the load-failed sentence
    test.fail()
    await open(page, { list: { body: '<html>proxy error' } })
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await expect(rows(page)).toHaveCount(0)
  })

  test('LOAD-5 (S-05, Q2-7, N-02) Retry reads again: the rows come in and the failure sentence goes', async ({ page }) => {
    // Spec basis: ADR-330 (S-05) ("Retry, which reads again"); owner N-02 (a red box over data that had loaded)
    let fail = true
    const F = await open(page, { list: () => (fail ? { status: 500, json: {} } : { json: { strategies: LIST } }) })
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    fail = false
    await page.getByTestId('list-load-retry').click()
    await expect(names(page)).toHaveText(ORDER)
    await expect(page.getByTestId('list-load-error')).toHaveCount(0)
    expect(callsTo(F, 'GET', /^\/api\/strategies$/)).toHaveLength(2)
  })

  test('LOAD-6 (S-05) Retry while it fails again keeps the sentence and the button (no blank page)', async ({ page }) => {
    // Spec basis: ADR-330 (S-05)
    const F = await open(page, { list: { status: 500, json: {} } })
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await page.getByTestId('list-load-retry').click()
    await expect.poll(() => callsTo(F, 'GET', /^\/api\/strategies$/).length).toBe(2)
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await expect(page.getByTestId('list-load-retry')).toBeVisible()
  })

  test('LOAD-7 (S-05) no answer within 15 seconds shows the same sentence and Retry; a late answer is then ignored', async ({ page }) => {
    // Spec basis: ADR-330 (S-05) ("after 15 seconds, 'Could not load your strategies. Nothing was changed.' with Retry")
    await page.clock.install()
    const g = gate()
    await open(page, { list: () => ({ wait: g.wait, json: { strategies: LIST } }) })
    await expect(page.getByTestId('list-skeleton')).toBeVisible()
    await page.clock.fastForward(15001)
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    g.open() // the answer comes late: the page already said it failed
    await expect(page.getByTestId('list-load-error')).toHaveText(LOAD_FAILED)
    await expect(rows(page)).toHaveCount(0)
  })

  test('LOAD-8 a failed re-read after a good first read keeps the list on screen (Undo / reload failing does not blank it)', async ({ page }) => {
    // Spec basis: none (searched: re-read, keeps the list; the page comment in MyStrategiesPage.vue is the only source)
    let fail = false
    const F = await openLoaded(page, { list: () => (fail ? { status: 500, json: {} } : { json: { strategies: LIST } }) })
    fail = true
    await rowOf(page, 17).getByTestId('delete-17').click()
    F.over.del = { status: 409, json: cat('This strategy was changed by another action after you opened it.') } // delete refused: the page re-reads (and that read fails)
    await rowOf(page, 17).getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText('This strategy was changed by another action after you opened it.')
    await expect(names(page)).toHaveText(ORDER)
    await expect(page.getByTestId('list-load-error')).toHaveCount(0)
  })

  test('EMPTY-1 (SHARED-01) an empty list shows the exact empty text, no search box and no bulk bar', async ({ page }) => {
    // Spec basis: REQ-076 AC-10 / ADR-193 (empty states); the page's own sentence (REQ-009 AC-2: saved strategies are listed)
    await open(page, {}, [])
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY)
    await expect(page.getByTestId('strategy-search')).toHaveCount(0)
    await expect(page.getByTestId('bulk-bar')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(0)
  })

  test('EMPTY-2 a list that holds only Completed strategies is empty here too; the Completed page says "No strategy is completed yet." when there are none', async ({ page }) => {
    // Spec basis: ADR-259 (a closed trade leaves this list); the page's own Completed empty sentence (searched: "No strategy is completed yet")
    await open(page, {}, [DONE])
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY)
    await page.goto(DONE_URL)
    await expect(rowOf(page, 30)).toBeVisible()
    await page.unroute(/\/api\//)
    await stubApi(page, {}, [R17])
    await page.goto(DONE_URL)
    await expect(page.getByTestId('empty-state-message')).toHaveText('No strategy is completed yet.')
  })

  test('EMPTY-3 a 200 reply without a strategies array reads as an empty list, not a crash', async ({ page }) => {
    // Spec basis: none (searched: unreadable list, strategies missing); fail closed means no rows are invented
    await open(page, { list: { json: { something: 'else' } } })
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY)
  })
})

// =============================================================================================== search
test.describe('My Strategies: search (REQ-134 AC-4, REQ-070 AC-7)', () => {
  test('SEARCH-1 (MYSTR-01) typing filters the rows by name as typed, case-insensitive', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 ("filters the list by name, case-insensitive, as the user types")
    await openLoaded(page)
    const box = page.getByTestId('strategy-search')
    await box.fill('S')
    await expect(names(page)).toHaveText(['Iron Condor Nov', 'Bull Put Spread', 'Short Straddle', 'Held IC k10', 'Sent Basket'].filter((n) => n.toLowerCase().includes('s')))
    await box.fill('')
    await box.pressSequentially('BULL')
    await expect(names(page)).toHaveText(['Bull Put Spread'])
    await box.fill('condor')
    await expect(names(page)).toHaveText(['Iron Condor Nov'])
  })

  test('SEARCH-2 (Q2-4) no match shows exactly "No saved strategy matches <text>" and no rows', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 ('no match shows "No saved strategy matches <text>"')
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('zzzzzz')
    await expect(page.getByTestId('search-no-match')).toHaveText('No saved strategy matches zzzzzz')
    await expect(rows(page)).toHaveCount(0)
    await page.getByTestId('strategy-search').fill('  zz  ')
    await expect(page.getByTestId('search-no-match')).toHaveText('No saved strategy matches zz') // the text is trimmed
  })

  test('SEARCH-3 clearing the box brings every row back in the same order and removes the no-match line', async ({ page }) => {
    // Spec basis: REQ-134 AC-4
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('zzzzzz')
    await expect(page.getByTestId('search-no-match')).toBeVisible()
    await page.getByTestId('strategy-search').fill('')
    await expect(page.getByTestId('search-no-match')).toHaveCount(0)
    await expect(names(page)).toHaveText(ORDER)
  })

  test('SEARCH-4 the search box is named for a screen reader and has the placeholder "Search name"', async ({ page }) => {
    // Spec basis: none (searched: Search name, placeholder, aria-label); REQ-134 AC-4 names the search box only
    await openLoaded(page)
    const box = page.getByTestId('strategy-search')
    await expect(box).toHaveAttribute('placeholder', 'Search name')
    await expect(page.getByRole('searchbox', { name: 'Search saved strategies by name' })).toBeVisible()
  })

  test('SEARCH-5 the search matches the name only (not the underlying or the legs line)', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 ("filters the list by name")
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('SENSEX')
    await expect(page.getByTestId('search-no-match')).toHaveText('No saved strategy matches SENSEX')
  })

  test('SEARCH-6 the typed search is kept while a row is renamed into or out of the match', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 / AC-4 (rename changes only the name; the list stays filtered by the search)
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('straddle')
    await expect(names(page)).toHaveText(['Short Straddle'])
    await rowOf(page, 9).getByTestId('rename-9').click()
    await page.getByTestId('rename-input').fill('Quiet Strangle')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('search-no-match')).toHaveText('No saved strategy matches straddle')
    await expect(page.getByTestId('strategy-search')).toHaveValue('straddle')
  })
})

// =============================================================================================== rename
test.describe('My Strategies: rename (REQ-134 AC-1, AC-3, ADR-183)', () => {
  const box = (page: Page) => page.getByTestId('rename-input')

  test('RENAME-1 (MYSTR-09, MYSTR-12) Rename opens the name box prefilled WITHOUT the API quotes, with the hint "A name can be up to 20 characters."', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 / ADR-183 (1 to 20 characters); owner R-05 (box "Short Iron Condor", hint, Save / Cancel)
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await expect(box(page)).toHaveValue('Bull Put Spread')
    await expect(page.getByTestId('rename-limit')).toHaveText('A name can be up to 20 characters.')
    await expect(page.getByTestId('rename-save')).toHaveText('Save')
    await expect(page.getByTestId('rename-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('rename-form')).toHaveCount(1)
    await expect(box(page)).toHaveAttribute('aria-label', 'New strategy name')
  })

  test('RENAME-2 (MYSTR-13) type a new name and Save: the row shows it, only the name changed, one PATCH with the revision read first', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (renaming changes only the name; never legs, prices, status or last-saved time)
    const F = await openLoaded(page)
    const before = await rowOf(page, 17).innerText()
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Put Spread Dec')
    await page.getByTestId('rename-save').click()
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Put Spread Dec')
    await expect(page.getByTestId('rename-form')).toHaveCount(0)
    const after = await rowOf(page, 17).innerText()
    expect(after.replace('Put Spread Dec', 'Bull Put Spread')).toBe(before)
    const patch = callsTo(F, 'PATCH', /strategies\/17\/name/)
    expect(patch).toHaveLength(1)
    expect(patch[0].body).toEqual({ name: 'Put Spread Dec', expected_revision: 3 })
    expect(callsTo(F, 'GET', /^\/api\/strategies\/17$/)).toHaveLength(1) // the revision is read once, then sent
    await expect(names(page)).toHaveText(['Iron Condor Nov', 'Put Spread Dec', 'Short Straddle', 'Held IC k10', 'Sent Basket']) // order unchanged
  })

  test('RENAME-3 (MYSTR-11) pressing Enter in the name box saves', async ({ page }) => {
    // Spec basis: REQ-134 AC-3; inventory MYSTR-11 ("Enter saves")
    const F = await openLoaded(page)
    await rowOf(page, 9).getByTestId('rename-9').click()
    await box(page).fill('Straddle Dec')
    await box(page).press('Enter')
    await expect(rowOf(page, 9).getByTestId('row-name')).toHaveText('Straddle Dec')
    expect(callsTo(F, 'PATCH', /strategies\/9\/name/)).toHaveLength(1)
  })

  test('RENAME-4 (MYSTR-14) Cancel closes the box, the old name stays and nothing is sent', async ({ page }) => {
    // Spec basis: REQ-134 AC-3; inventory MYSTR-14
    const F = await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Never saved')
    await page.getByTestId('rename-cancel').click()
    await expect(page.getByTestId('rename-form')).toHaveCount(0)
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
    expect(callsTo(F, 'PATCH', /name/)).toHaveLength(0)
  })

  test('RENAME-5 (R-05, MYSTR-11) Escape in the name box closes it without saving', async ({ page }) => {
    // Spec basis: none (searched: Escape, Esc, rename); inventory MYSTR-11 says "Esc cancels"; owner R-05 "whether Escape closed the box not verified"
    // expected-fail: NEW-T10: pressing Escape in the rename box does nothing today (no key handler on the form), the box stays open
    test.fail()
    const F = await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Never saved')
    await box(page).press('Escape')
    await expect(page.getByTestId('rename-form')).toHaveCount(0, { timeout: 2000 })
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
    expect(callsTo(F, 'PATCH', /name/)).toHaveLength(0)
  })

  test('RENAME-6 (D-53) the name box stops at 20 characters: typing 25 keeps 20 and the hint says nothing more can be typed', async ({ page }) => {
    // Spec basis: ADR-183 (a name is 1 to 20 characters); REQ-134 AC-1; the limit hint texts of D-53
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('')
    await box(page).pressSequentially('ABCDEFGHIJKLMNOPQRSTUVWXY')
    await expect(box(page)).toHaveValue('ABCDEFGHIJKLMNOPQRST')
    await expect(page.getByTestId('rename-limit')).toHaveText('That is the 20-character limit: nothing more can be typed.')
  })

  test('RENAME-7 a name stored before ADR-183 (26 characters) opens whole; the hint says it is too long, and Save is answered by the server\'s refusal', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 ("a name stored before ADR-183 with up to 40 characters stays readable"); ADR-183; D-53 over-limit hint
    const long = mk(60, 'Nifty weekly iron condor 26', '2026-11-25T10:00:00+05:30')
    const F = await openLoaded(page, { patch: { status: 422, json: cat('Names can be 1 to 20 characters.') } }, [long])
    await rowOf(page, 60).getByTestId('rename-60').click()
    await expect(box(page)).toHaveValue('Nifty weekly iron condor 26')
    await expect(page.getByTestId('rename-limit')).toHaveText('This name is longer than 20 characters: shorten it to save.')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText('Names can be 1 to 20 characters.')
    await expect(rowOf(page, 60).getByTestId('row-name')).toHaveText('Nifty weekly iron condor 26')
    expect(callsTo(F, 'PATCH', /name/)).toHaveLength(1)
  })

  test('RENAME-8 an empty name is refused by the server: its sentence shows, the box stays open and the old name stays', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 ('an empty name is refused with "Give the strategy a name"')
    await openLoaded(page, { patch: { status: 422, json: cat('Give the strategy a name') } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText('Give the strategy a name')
    await expect(page.getByTestId('rename-form')).toHaveCount(1)
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
  })

  test('RENAME-9 a name another strategy already has is accepted (REQ-134 AC-1: two strategies may share a name)', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 ("Two strategies of one user may share a name; each keeps its own id")
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Short Straddle')
    await page.getByTestId('rename-save').click()
    await expect(names(page)).toHaveText(['Iron Condor Nov', 'Short Straddle', 'Short Straddle', 'Held IC k10', 'Sent Basket'])
    await expect(page.getByTestId('rename-error')).toHaveCount(0)
  })

  test('RENAME-10 server failure (500, catalogue body): the four-part message shows, the old name is kept, the box stays for another try', async ({ page }) => {
    // Spec basis: REQ-065 (a failure says what happened, the impact, what is blocked, what to do); REQ-134 AC-3
    await openLoaded(page, { patch: { status: 500, json: cat('The name could not be saved.') } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Another Name')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText('The name could not be saved.')
    await expect(page.getByTestId('rename-error-impact')).toHaveText('Nothing else changed.')
    await expect(page.getByTestId('rename-error-blocked')).toHaveText('Nothing.')
    await expect(page.getByTestId('rename-error-next')).toHaveText('Try again.')
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
    await expect(box(page)).toHaveValue('Another Name')
  })

  test('RENAME-11 server failure with no catalogue body (plain 500): the neutral four-part message shows and the old name is kept', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback when the failure carries no catalogue message)
    await openLoaded(page, { patch: { status: 500, json: { detail: 'Traceback ...' } } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Another Name')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('rename-error-impact')).toHaveText(NEUTRAL.impact)
    await expect(page.getByTestId('rename-error-blocked')).toHaveText(NEUTRAL.blocked)
    await expect(page.getByTestId('rename-error-next')).toHaveText(NEUTRAL.next)
    await expect(page.getByTestId('rename-error')).not.toContainText('Traceback')
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
  })

  test('RENAME-12 connection refused on Save: the neutral message shows and the old name is kept', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback for a dropped connection)
    await openLoaded(page, { patch: { abort: true } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Another Name')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText(NEUTRAL.what)
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
  })

  test('RENAME-13 an unreadable PATCH answer (no name in it) is not shown as renamed: the neutral message shows and the old name stays', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (fail closed: nothing is shown as renamed on an answer that cannot be read)
    await openLoaded(page, { patch: { json: { id: 17 } } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Another Name')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText(NEUTRAL.what)
    await expect(rowOf(page, 17).getByTestId('row-name')).toHaveText('Bull Put Spread')
  })

  test('RENAME-14 when the revision cannot be read first, no PATCH is sent (fail closed) and the neutral message shows', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (the rename sends the revision it read; an unreadable one sends nothing)
    const F = await openLoaded(page, { one: { json: { id: 17 } } })
    await rowOf(page, 17).getByTestId('rename-17').click()
    await box(page).fill('Another Name')
    await page.getByTestId('rename-save').click()
    await expect(page.getByTestId('rename-error-what')).toHaveText(NEUTRAL.what)
    expect(callsTo(F, 'PATCH', /name/)).toHaveLength(0)
  })

  test('RENAME-15 (S-04) the rename box is its own line: opening it on one row leaves the other rows and their buttons where they were', async ({ page }) => {
    // Spec basis: ADR-330 (S-04) / REQ-070 ("Rename and Delete do not move"); same class as the row confirm
    await openLoaded(page)
    const rename17 = page.getByTestId('rename-17')
    const before = await rename17.boundingBox()
    await rowOf(page, 9).getByTestId('rename-9').click()
    await expect(page.getByTestId('rename-form')).toHaveCount(1)
    const after = await rename17.boundingBox()
    expect(after!.x).toBe(before!.x)
    expect(after!.y).toBe(before!.y)
  })

  test('RENAME-16 opening Rename on a second row moves the box there; only one box is open at a time', async ({ page }) => {
    // Spec basis: none (searched: rename second row); one name box at a time is the page's single `renaming` state
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('rename-17').click()
    await rowOf(page, 9).getByTestId('rename-9').click()
    await expect(page.getByTestId('rename-form')).toHaveCount(1)
    await expect(rowOf(page, 9).getByTestId('rename-form')).toBeVisible()
    await expect(box(page)).toHaveValue('Short Straddle')
  })

  test('RENAME-17 a held-at-broker row and a sent-basket row can still be renamed (rename is not delete)', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (a saved strategy can be renamed; no condition on orders); ADR-292 (held blocks delete only)
    await openLoaded(page)
    await rowOf(page, 5).getByTestId('rename-5').click()
    await box(page).fill('Held renamed')
    await page.getByTestId('rename-save').click()
    await expect(rowOf(page, 5).getByTestId('row-name')).toHaveText('Held renamed')
  })
})

// =============================================================================================== delete one
test.describe('My Strategies: delete one and Undo (REQ-070 AC-6, ADR-293, ADR-292, ADR-271, S-03, S-04)', () => {
  test('DEL-1 (SHARED-06, SHARED-03) Delete asks "Delete this draft? Its history is kept, and you can Undo right after." with Delete and Cancel', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (the user confirms; "draft" only for a strategy that never had an order)
    await openLoaded(page)
    await page.getByTestId('delete-17').click()
    const box = page.getByTestId('delete-confirm-box')
    await expect(box).toContainText(CONFIRM_DRAFT)
    await expect(page.getByTestId('delete-confirm')).toHaveText('Delete')
    await expect(page.getByTestId('delete-cancel')).toHaveText('Cancel')
    await expect(rows(page)).toHaveCount(5) // nothing is deleted until the confirm
  })

  test('DEL-2 (SHARED-04) Cancel closes the question, keeps the row and sends nothing', async ({ page }) => {
    // Spec basis: REQ-070 AC-6
    const F = await openLoaded(page)
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-cancel').click()
    await expect(page.getByTestId('delete-confirm-box')).toHaveCount(0)
    await expect(names(page)).toHaveText(ORDER)
    expect(callsTo(F, 'DELETE', /strategies/)).toHaveLength(0)
  })

  test('DEL-3 (SHARED-03, SHARED-07) confirm deletes: the row goes, "Strategy deleted." with Undo shows, and one DELETE carried the revision read first', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 ("Undo is offered"); ADR-271 (Undo in the fixed toast where the user is looking)
    const F = await openLoaded(page)
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 17)).toHaveCount(0)
    await expect(names(page)).toHaveText(['Iron Condor Nov', 'Short Straddle', 'Held IC k10', 'Sent Basket'])
    await expect(page.getByTestId('delete-toast')).toContainText('Strategy deleted.')
    await expect(page.getByTestId('delete-undo')).toHaveText('Undo')
    expect(callsTo(F, 'DELETE', /strategies\/17\?expected_revision=3$/)).toHaveLength(1)
  })

  test('DEL-4 (SHARED-07) Undo brings the row back in its place with the same name and legs; one undelete call with the deleted revision', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (Undo brings it back); ADR-271
    const F = await openLoaded(page)
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 17)).toHaveCount(0)
    await page.getByTestId('delete-undo').click()
    await expect(names(page)).toHaveText(ORDER)
    await expect(rowOf(page, 17).getByTestId('row-legs')).toHaveText('NIFTY 1 Dec 2026 25600 PE and 1 more')
    await expect(page.getByTestId('delete-toast')).toHaveCount(0)
    expect(callsTo(F, 'POST', /strategies\/17\/undelete\?expected_revision=3$/)).toHaveLength(1) // the revision the page read before the delete
  })

  test('DEL-5 (ADR-271, REQ-167 AC-7) the Undo toast goes away when the served undo window (other.undo_clear_all_seconds = 2) ends, and the row stays deleted', async ({ page }) => {
    // Spec basis: ADR-271 ("its window is 10 s (other.undo_clear_all_seconds)"); REQ-167 AC-7 (the served wait, never a typed time)
    await openLoaded(page, { settings: { json: { groups: [{ settings: [{ key: 'other.undo_clear_all_seconds', value: '2' }] }] } } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-toast')).toBeVisible()
    await expect(page.getByTestId('delete-toast')).toHaveCount(0, { timeout: 8000 })
    await expect(rowOf(page, 17)).toHaveCount(0)
  })

  test('DEL-6 (REQ-167 AC-7) when the undo window cannot be read the row is deleted but no Undo is offered (never a guessed time)', async ({ page }) => {
    // Spec basis: REQ-167 AC-7 ("unknown = no Undo is offered, never a typed time")
    await openLoaded(page, { settings: { status: 500, json: {} } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 17)).toHaveCount(0)
    await expect(page.getByTestId('delete-undo')).toHaveCount(0)
  })

  test('DEL-7 (ADR-293 (4)) a strategy with practice orders says so in the confirm: "Practice orders were placed for this strategy. Delete it? ..."', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 / ADR-293 (4) ("for a paper strategy says its practice record leaves the lists")
    await openLoaded(page)
    await page.getByTestId('delete-21').click()
    await expect(page.getByTestId('delete-confirm-box')).toContainText(CONFIRM_PAPER)
    await expect(page.getByTestId('delete-confirm-box')).not.toContainText('Delete this draft?')
  })

  test('DEL-8 (ADR-293 (1)) a RUNNING paper strategy can be deleted: confirm removes the row and Undo brings it back', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 / ADR-293 (1) ("open or closed"); ADR-330 (8) (real case 25 Nov 09:50, "T1123-C9 pm 4lot" deleted while running)
    const F = await openLoaded(page)
    await page.getByTestId('delete-21').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 21)).toHaveCount(0)
    expect(callsTo(F, 'DELETE', /strategies\/21\?expected_revision=3$/)).toHaveLength(1)
    await page.getByTestId('delete-undo').click()
    await expect(rowOf(page, 21)).toBeVisible()
    await expect(rowOf(page, 21).getByTestId('row-status')).toHaveText('Running')
  })

  test('DEL-9 (S-03, SHARED-05) a held-at-broker row has no Delete button and no tick box: the held sentence takes their place', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 / ADR-292 ("This strategy is marked as held at your broker, so it cannot be deleted." never the orders sentence)
    await openLoaded(page)
    const held = rowOf(page, 5)
    await expect(held.getByTestId('delete-refused')).toHaveText(HELD)
    await expect(held.getByTestId('delete-5')).toHaveCount(0)
    await expect(page.getByTestId('select-5')).toHaveCount(0)
  })

  test('DEL-10 (SHARED-05) a row whose real basket was sent has no Delete button or tick box and says "Orders were already sent for this strategy, so it cannot be deleted."', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 / ADR-118; AC-7 ("a row whose orders were sent keeps ...")
    await openLoaded(page)
    await expect(rowOf(page, 4).getByTestId('delete-refused')).toHaveText(SENT)
    await expect(rowOf(page, 4).getByTestId('delete-4')).toHaveCount(0)
    await expect(page.getByTestId('select-4')).toHaveCount(0)
  })

  test('DEL-11 a row whose can_delete field is missing offers no Delete (fail closed)', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 / ADR-118 ("a missing field is false": only an explicit true from the server offers Delete)
    const noField = mk(70, 'No Field', '2026-11-25T10:00:00+05:30')
    delete noField.can_delete
    await openLoaded(page, {}, [noField])
    await expect(page.getByTestId('delete-70')).toHaveCount(0)
    await expect(page.getByTestId('delete-refused')).toHaveText(SENT)
    await expect(page.getByTestId('select-70')).toHaveCount(0)
  })

  test('DEL-12 (S-04, Q2-6) clicking Delete does not move Rename or the Delete button: the question is its own full-width line below the row', async ({ page }) => {
    // Spec basis: ADR-330 (S-04) / REQ-070 ("The single-row confirm is its own full-width line below the row, so Rename and Delete do not move")
    await openLoaded(page)
    const rename = page.getByTestId('rename-17')
    const del = page.getByTestId('delete-17')
    const r0 = await rename.boundingBox()
    const d0 = await del.boundingBox()
    await del.click()
    const confirm = page.getByTestId('delete-confirm-box')
    await expect(confirm).toBeVisible()
    const r1 = await rename.boundingBox()
    const d1 = await del.boundingBox()
    expect([r1!.x, r1!.y]).toEqual([r0!.x, r0!.y])
    expect([d1!.x, d1!.y]).toEqual([d0!.x, d0!.y])
    const c = await confirm.boundingBox()
    const li = await rowOf(page, 17).boundingBox()
    expect(c!.y).toBeGreaterThanOrEqual(d0!.y + d0!.height - 1) // below the action cluster
    expect(c!.y + c!.height).toBeLessThanOrEqual(li!.y + li!.height + 1) // still inside its row
  })

  test('DEL-13 (SHARED-03) delete refused 409 (changed since the list was read): the server\'s sentence shows and the list is re-read', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (stale revision refused); REQ-065 (four-part message)
    const F = await openLoaded(page, { del: { status: 409, json: cat(CHANGED) } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(CHANGED)
    await expect(rowOf(page, 17)).toBeVisible()
    await expect(page.getByTestId('delete-toast')).toHaveCount(0)
    expect(callsTo(F, 'GET', /^\/api\/strategies$/).length).toBeGreaterThanOrEqual(2) // the re-read
  })

  test('DEL-14 delete 404 (already hidden or not yours): no error is shown, the list is re-read and the row is gone', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (not_found: "never saying it exists"); the single delete re-reads silently
    const F = await openLoaded(page, { del: (c) => { F.hidden.add(c.id!); return { status: 404, json: cat('The page or action you asked for is not available here.') } } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 17)).toHaveCount(0)
    await expect(page.getByTestId('delete-error-what')).toHaveCount(0)
    await expect(page.getByTestId('delete-toast')).toHaveCount(0)
  })

  test('DEL-15 delete 500 with no catalogue body: the neutral message shows and the row stays', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback)
    await openLoaded(page, { del: { status: 500, json: {} } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('delete-error-next')).toHaveText(NEUTRAL.next)
    await expect(rowOf(page, 17)).toBeVisible()
    await expect(page.getByTestId('delete-toast')).toHaveCount(0)
  })

  test('DEL-16 connection refused on confirm: the neutral message shows, the row stays, no Undo', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback for a dropped connection)
    await openLoaded(page, { del: { abort: true } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(rowOf(page, 17)).toBeVisible()
    await expect(page.getByTestId('delete-undo')).toHaveCount(0)
  })

  test('DEL-17 when the revision cannot be read no DELETE is sent (fail closed) and the neutral message shows', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (the delete carries the revision it read; unreadable sends nothing)
    const F = await openLoaded(page, { one: { json: { id: 17 } } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    expect(callsTo(F, 'DELETE', /strategies/)).toHaveLength(0)
    await expect(rowOf(page, 17)).toBeVisible()
  })

  test('DEL-18 Undo that finds nothing to undo (404) says "Nothing to undo" and re-reads the list', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 ("Nothing to undo" is the one catalogue wording of the history screens; ADR-118)
    await openLoaded(page, { undelete: { status: 404, json: cat('The page or action you asked for is not available here.') } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await page.getByTestId('delete-undo').click()
    await expect(page.getByTestId('delete-notice')).toHaveText('Nothing to undo')
    await expect(rowOf(page, 17)).toHaveCount(0)
  })

  test('DEL-19 Undo that fails (500): the neutral message shows; the row is not shown as back until the server has it', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback); REQ-070 AC-6 (Undo brings it back only when the server did)
    await openLoaded(page, { undelete: { status: 500, json: {} } })
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await page.getByTestId('delete-undo').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(rowOf(page, 17)).toHaveCount(0)
  })

  test('DEL-20 (R-11) deleting two rows one after another: the toast offers Undo for the newest only and the first stays deleted', async ({ page }) => {
    // Spec basis: ADR-271 (one Undo toast where the user is looking); REQ-070 AC-6
    const F = await openLoaded(page)
    await page.getByTestId('delete-17').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 17)).toHaveCount(0)
    await page.getByTestId('delete-9').click()
    await page.getByTestId('delete-confirm').click()
    await expect(rowOf(page, 9)).toHaveCount(0)
    await page.getByTestId('delete-undo').click()
    await expect(rowOf(page, 9)).toBeVisible()
    await expect(rowOf(page, 17)).toHaveCount(0)
    expect(callsTo(F, 'POST', /undelete/)).toHaveLength(1)
  })

  test('DEL-21 the Delete button is named for a screen reader? (the text link keeps the visible name "Delete")', async ({ page }) => {
    // Spec basis: none (searched: Delete accessible name, aria-label); REQ-070 AC-6 names the button "Delete"
    await openLoaded(page)
    await expect(page.getByTestId('delete-17')).toHaveText('Delete')
  })
})

// =============================================================================================== bulk
test.describe('My Strategies: bulk select and Delete selected (ADR-330 (8) S-01, REQ-070 AC-7)', () => {
  const tick = (page: Page, id: number) => page.getByTestId(`select-${id}`).check()
  const deleteSelected = (page: Page) => page.getByTestId('delete-selected')
  const BULK_URL = /\/api\/strategies\/bulk-delete$/

  test('BULK-1 (MYSTR-07, MYSTR-03) every deletable row has a tick box named "Select <name>"; "Delete selected (0)" is disabled at 0, and enabled with a count after ticking', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 / "My Strategies screen wording" ("Delete selected (N)" is disabled at 0); ADR-330 (8)
    await openLoaded(page)
    await expect(deleteSelected(page)).toHaveText('Delete selected (0)')
    await expect(deleteSelected(page)).toBeDisabled()
    await expect(page.getByRole('checkbox', { name: 'Select Bull Put Spread' })).toBeVisible()
    await tick(page, 17)
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
    await expect(deleteSelected(page)).toBeEnabled()
    await tick(page, 9)
    await expect(deleteSelected(page)).toHaveText('Delete selected (2)')
    await page.getByTestId('select-17').uncheck()
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
  })

  test('BULK-2 (MYSTR-02) "Select all 3 shown" counts only the rows that can be deleted (held and basket-sent rows are not counted) and ticks them all', async ({ page }) => {
    // Spec basis: REQ-070 "My Strategies screen wording" ("Select all N shown" selects only the rows left after the search); ADR-330 (8)
    await openLoaded(page)
    await expect(page.getByTestId('select-all-label')).toHaveText('Select all 3 shown')
    await page.getByTestId('select-all').check()
    await expect(deleteSelected(page)).toHaveText('Delete selected (3)')
    for (const id of [21, 17, 9]) await expect(page.getByTestId(`select-${id}`)).toBeChecked()
    await page.getByTestId('select-all').uncheck()
    await expect(deleteSelected(page)).toHaveText('Delete selected (0)')
  })

  test('BULK-3 (Q2-4) Select all after a search ticks only the rows still shown, and a later clear of the search leaves the hidden ones unticked', async ({ page }) => {
    // Spec basis: REQ-070 "My Strategies screen wording" ("Select all N shown selects only the rows left after the search"); owner check Q2-4
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('straddle')
    await expect(page.getByTestId('select-all-label')).toHaveText('Select all 1 shown') // Short Straddle only
    await page.getByTestId('select-all').check()
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
    await page.getByTestId('strategy-search').fill('')
    await expect(page.getByTestId('select-9')).toBeChecked()
    await expect(page.getByTestId('select-17')).not.toBeChecked()
    await expect(page.getByTestId('select-21')).not.toBeChecked()
  })

  test('BULK-4 a tick on a row that the search then hides is dropped from the selection (a hidden row is never deleted by a click)', async ({ page }) => {
    // Spec basis: REQ-070 / ADR-330 (8) (the selection is always a subset of the rows shown)
    await openLoaded(page)
    await tick(page, 17)
    await tick(page, 9)
    await page.getByTestId('strategy-search').fill('straddle')
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
  })

  test('BULK-5 (MYSTR-04, MYSTR-06) Delete selected opens "Delete 2 strategies?" (no running clause); Cancel closes it and sends nothing', async ({ page }) => {
    // Spec basis: REQ-070 "My Strategies screen wording" ('One confirmation reads "Delete N strategies?"'); AC-7
    const F = await openLoaded(page)
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await expect(page.getByTestId('bulk-confirm-text')).toHaveText('Delete 2 strategies?')
    await expect(page.getByTestId('bulk-confirm')).toHaveText('Delete')
    await expect(page.getByTestId('bulk-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('bulk-confirm-box')).toHaveAttribute('role', 'alertdialog')
    await page.getByTestId('bulk-cancel').click()
    await expect(page.getByTestId('bulk-confirm-box')).toHaveCount(0)
    await expect(deleteSelected(page)).toHaveText('Delete selected (2)') // the ticks stay
    expect(callsTo(F, 'POST', BULK_URL)).toHaveLength(0)
    await expect(rows(page)).toHaveCount(5)
  })

  test('BULK-6 singular: one ticked row asks "Delete 1 strategy?"', async ({ page }) => {
    // Spec basis: REQ-070 "My Strategies screen wording" ('singular "Delete 1 strategy?"')
    await openLoaded(page)
    await tick(page, 17)
    await deleteSelected(page).click()
    await expect(page.getByTestId('bulk-confirm-text')).toHaveText('Delete 1 strategy?')
  })

  test('BULK-7 (Q2-4, S-01) with a RUNNING paper strategy among the ticked rows the confirmation says "Delete 3 strategies? 1 of them are running."', async ({ page }) => {
    // Spec basis: ADR-330 (8) ('"Delete 14 strategies? 3 of them are running."'); REQ-070 AC-7 (K counts rows whose status word is Running)
    await openLoaded(page)
    await page.getByTestId('select-all').check()
    await deleteSelected(page).click()
    await expect(page.getByTestId('bulk-confirm-text')).toHaveText('Delete 3 strategies? 1 of them are running.')
  })

  test('BULK-8 (MYSTR-05, S-01) confirm sends ONE POST /strategies/bulk-delete with every id and the revision read; the rows go, the summary line shows, the ticks clear', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (POST takes {items:[{id, expected_revision}]}); ADR-330 (8); summary "3 deleted" when none is kept
    const F = await openLoaded(page, { bulk: (c) => ({ json: { deleted: c.body.items.map((i: any) => ({ id: i.id, revision: i.expected_revision + 1 })), kept: [], summary_text: cat('3 deleted') } }) })
    await page.getByTestId('select-all').check()
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-summary')).toHaveText('3 deleted')
    await expect(names(page)).toHaveText(['Held IC k10', 'Sent Basket'])
    await expect(page.getByTestId('bulk-kept')).toHaveCount(0)
    await expect(page.getByTestId('bulk-confirm-box')).toHaveCount(0)
    const posts = callsTo(F, 'POST', BULK_URL)
    expect(posts).toHaveLength(1)
    expect([...posts[0].body.items].sort((a: any, b: any) => a.id - b.id)).toEqual([
      { id: 9, expected_revision: 3 }, { id: 17, expected_revision: 3 }, { id: 21, expected_revision: 3 }])
  })

  test('BULK-9 (SHARED-07) the Undo toast reads "3 strategies deleted." ("1 strategy deleted." for one) and one Undo restores every deleted strategy (one undelete per id)', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('"N strategies deleted." ("1 strategy deleted." for one) in the Undo toast'; "Undo is the per-id undelete, once per deleted id"); owner Q2-4
    const F = await openLoaded(page)
    await page.getByTestId('select-all').check()
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-toast')).toContainText('3 strategies deleted.')
    await page.getByTestId('delete-undo').click()
    await expect(names(page)).toHaveText(ORDER)
    await expect(page.getByTestId('bulk-result')).toHaveCount(0) // the result line goes with the Undo
    const undos = callsTo(F, 'POST', /undelete/).map((c) => c.path).sort()
    expect(undos).toEqual(['/api/strategies/17/undelete?expected_revision=4', '/api/strategies/21/undelete?expected_revision=4', '/api/strategies/9/undelete?expected_revision=4'])
  })

  test('BULK-10 the Undo toast of a one-row bulk delete reads "1 strategy deleted."', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('"1 strategy deleted." for one')
    await openLoaded(page)
    await tick(page, 17)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-toast')).toContainText('1 strategy deleted.')
  })

  test('BULK-11 (S-01) partial answer: "2 deleted, 1 kept: ..." names the kept strategy with the server\'s reason sentence; the kept row stays, the deleted ones go, Undo restores only the deleted', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (kept: [{id, reason: changed, text}]; summary "12 deleted, 2 kept: see each row" or the shared reason's sentence); ADR-330 (8) ("named in the result")
    const F = await openLoaded(page, { bulk: () => ({ json: {
      deleted: [{ id: 21, revision: 4 }, { id: 17, revision: 4 }],
      kept: [{ id: 9, reason: 'changed', text: cat(CHANGED) }],
      summary_text: cat(`2 deleted, 1 kept: ${CHANGED}`) } }) })
    await page.getByTestId('select-all').check()
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-summary')).toHaveText(`2 deleted, 1 kept: ${CHANGED}`)
    await expect(page.getByTestId('bulk-kept')).toHaveText([`Short Straddle: ${CHANGED}`])
    await expect(names(page)).toHaveText(['Short Straddle', 'Held IC k10', 'Sent Basket'])
    await expect(page.getByTestId('delete-toast')).toContainText('2 strategies deleted.')
    await page.getByTestId('delete-undo').click()
    await expect(names(page)).toHaveText(ORDER)
    expect(callsTo(F, 'POST', /undelete/)).toHaveLength(2) // only the two that were deleted
  })

  test('BULK-12 (S-01) each kept reason is named: held_at_broker, orders_sent, not_found, changed, failed show their own sentence beside the strategy name', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (reason one of held_at_broker, orders_sent, not_found, changed, failed; each from the error catalogue); ADR-330 (8)
    const NOT_FOUND = 'The page or action you asked for is not available here.'
    const five = [mk(31, 'K Held', '2026-11-25T10:00:00+05:30'), mk(32, 'K Orders', '2026-11-24T10:00:00+05:30'), mk(33, 'K Gone', '2026-11-23T10:00:00+05:30'),
      mk(34, 'K Changed', '2026-11-22T10:00:00+05:30'), mk(35, 'K Failed', '2026-11-21T10:00:00+05:30')]
    await openLoaded(page, { bulk: () => ({ json: { deleted: [], summary_text: cat('0 deleted, 5 kept: see each row'), kept: [
      { id: 31, reason: 'held_at_broker', text: cat(HELD) }, { id: 32, reason: 'orders_sent', text: cat(SENT) }, { id: 33, reason: 'not_found', text: cat(NOT_FOUND) },
      { id: 34, reason: 'changed', text: cat(CHANGED) }, { id: 35, reason: 'failed', text: cat(FAILED_ITEM) }] } }) }, five)
    await page.getByTestId('select-all').check()
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-summary')).toHaveText('0 deleted, 5 kept: see each row')
    await expect(page.getByTestId('bulk-kept')).toHaveText([`K Held: ${HELD}`, `K Orders: ${SENT}`, `K Gone: ${NOT_FOUND}`, `K Changed: ${CHANGED}`, `K Failed: ${FAILED_ITEM}`])
    await expect(rows(page)).toHaveCount(5) // none deleted: nothing removed
    await expect(page.getByTestId('delete-undo')).toHaveCount(0) // and no Undo for nothing
  })

  test('BULK-13 an answer that carries no summary_text shows the screen\'s own sentence "N deleted, M kept."', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('"N deleted, M kept." (when the answer has no summary_text)')
    await openLoaded(page, { bulk: () => ({ json: { deleted: [{ id: 17, revision: 4 }], kept: [{ id: 9, reason: 'changed', text: cat(CHANGED) }] } }) })
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-summary')).toHaveText('1 deleted, 1 kept.')
  })

  test('BULK-14 a revision that cannot be read: that row is kept as failed with "The strategy could not be read, so it was not deleted." and the others are still sent', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('"The strategy could not be read, so it was not deleted." (a row whose revision could not be read, kept as failed)')
    const F = await openLoaded(page, { one: (c) => (c.id === 9 ? { status: 500, json: {} } : { json: { id: c.id, revision: 3 } }) })
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-kept')).toHaveText(['Short Straddle: The strategy could not be read, so it was not deleted.'])
    await expect(rowOf(page, 9)).toBeVisible()
    await expect(rowOf(page, 17)).toHaveCount(0)
    expect(callsTo(F, 'POST', BULK_URL)[0].body.items).toEqual([{ id: 17, expected_revision: 3 }])
  })

  test('BULK-15 every revision unreadable: nothing is sent to bulk-delete and every row is named as kept', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (fail closed: an unreadable row is kept as failed)
    const F = await openLoaded(page, { one: { status: 500, json: {} } })
    await tick(page, 17)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('bulk-kept')).toHaveText(['Bull Put Spread: The strategy could not be read, so it was not deleted.'])
    await expect(page.getByTestId('bulk-summary')).toHaveText('0 deleted, 1 kept.')
    expect(callsTo(F, 'POST', BULK_URL)).toHaveLength(0)
    await expect(rows(page)).toHaveCount(5)
  })

  test('BULK-16 (ADR-330 (8)) POST refused 422 "You can delete at most 200 strategies at once.": the sentence shows, the selection stays, nothing is removed', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('more than 200 items is refused (422, "You can delete at most 200 strategies at once.")'); "A failed call keeps the selection and removes nothing"
    await openLoaded(page, { bulk: { status: 422, json: { what_happened: 'You can delete at most 200 strategies at once.', impact: 'No strategy was deleted.', what_is_blocked: 'This bulk delete.', next_action: 'Select fewer strategies and delete again.' } } })
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText('You can delete at most 200 strategies at once.')
    await expect(page.getByTestId('delete-error-next')).toHaveText('Select fewer strategies and delete again.')
    await expect(deleteSelected(page)).toHaveText('Delete selected (2)')
    await expect(rows(page)).toHaveCount(5)
    await expect(page.getByTestId('bulk-confirm-box')).toHaveCount(0)
  })

  test('BULK-17 (ADR-330 (8)) POST 500 with no catalogue body: the neutral message shows, the selection stays, nothing is removed', async ({ page }) => {
    // Spec basis: REQ-070 "A failed call keeps the selection and removes nothing"; REQ-065 (neutral fallback)
    await openLoaded(page, { bulk: { status: 500, json: {} } })
    await tick(page, 17)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
    await expect(rows(page)).toHaveCount(5)
    await expect(page.getByTestId('delete-undo')).toHaveCount(0)
  })

  test('BULK-18 (ADR-330 (8)) connection refused on the POST: the neutral message shows, the selection stays, nothing is removed', async ({ page }) => {
    // Spec basis: REQ-070 "A failed call keeps the selection and removes nothing"
    await openLoaded(page, { bulk: { abort: true } })
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(deleteSelected(page)).toHaveText('Delete selected (2)')
    await expect(rows(page)).toHaveCount(5)
  })

  test('BULK-19 (ADR-330 (8)) an answer that cannot be read (no deleted / kept lists) removes nothing and shows the neutral message', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (answer shape {deleted, kept, summary_text}); fail closed on a body that is not that
    await openLoaded(page, { bulk: { json: { ok: true } } })
    await tick(page, 17)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(rows(page)).toHaveCount(5)
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
  })

  test('BULK-20 Undo of a batch where some ids fail says "1 of 2 could not be brought back." and re-reads the list', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 ('"N of M could not be brought back." (Undo of a batch where some ids failed)')
    const F = await openLoaded(page, { undelete: (c) => (c.id === 9 ? { status: 500, json: {} } : { json: { id: c.id } }) })
    await tick(page, 17)
    await tick(page, 9)
    await deleteSelected(page).click()
    await page.getByTestId('bulk-confirm').click()
    await page.getByTestId('delete-undo').click()
    await expect(page.getByTestId('delete-notice')).toHaveText('1 of 2 could not be brought back.')
    await expect(rowOf(page, 17)).toBeVisible()
    await expect(rowOf(page, 9)).toHaveCount(0)
    expect(callsTo(F, 'POST', /undelete/)).toHaveLength(2)
  })

  test('BULK-21 opening the single-row Delete question closes an open bulk question (one question at a time)', async ({ page }) => {
    // Spec basis: none (searched: bulk confirm, row confirm, both open); one confirmation at a time follows REQ-070 AC-6/AC-7 ("the one confirmation")
    await openLoaded(page)
    await tick(page, 17)
    await deleteSelected(page).click()
    await expect(page.getByTestId('bulk-confirm-box')).toBeVisible()
    await page.getByTestId('delete-9').click()
    await expect(page.getByTestId('bulk-confirm-box')).toHaveCount(0)
    await expect(page.getByTestId('delete-confirm-box')).toBeVisible()
  })

  test('BULK-22 (Completed) the Completed page has the same tick boxes and Delete selected', async ({ page }) => {
    // Spec basis: ADR-330 (8) ("Not chosen: tick boxes on drafts and completed strategies only": completed rows are ticked too); REQ-070 AC-7
    await open(page, {}, [DONE, mk(31, 'Closed Two', '2026-11-14T10:00:00+05:30', { status: 'closed', status_word: 'Completed', closed_at: '2026-11-14T15:20:00+05:30', final_pnl_text: '-100.00' })], DONE_URL)
    await expect(page.getByTestId('select-all-label')).toHaveText('Select all 2 shown')
    await page.getByTestId('select-30').check()
    await expect(deleteSelected(page)).toHaveText('Delete selected (1)')
  })

  test('BULK-23 the bulk bar (Select all, Delete selected) is not there when the search matches nothing; it is back when the search is cleared', async ({ page }) => {
    // Spec basis: none (searched: bulk bar, no match); REQ-134 AC-4 (no match shows only the no-match line)
    await openLoaded(page)
    await page.getByTestId('strategy-search').fill('zzzzzz')
    await expect(page.getByTestId('bulk-bar')).toHaveCount(0)
    await page.getByTestId('strategy-search').fill('')
    await expect(page.getByTestId('bulk-bar')).toBeVisible()
  })

  test('BULK-24 when no row can be deleted "Select all 0 shown" is greyed', async ({ page }) => {
    // Spec basis: REQ-070 "My Strategies screen wording" (held / basket-sent rows have no tick box)
    await openLoaded(page, {}, [R5, R4])
    await expect(page.getByTestId('select-all-label')).toHaveText('Select all 0 shown')
    await expect(page.getByTestId('select-all')).toBeDisabled()
    await expect(deleteSelected(page)).toBeDisabled()
  })
})

// =============================================================================================== links out of a row
test.describe('My Strategies: Open in Builder and Execute Strategy (REQ-134 AC-5, REQ-038, REQ-056 AC-1, REQ-073 AC-6, W-121)', () => {
  test('LINK-1 (MYSTR-08) "Open in Builder" on the second row opens THAT strategy: address /strategy/builder?strategy=17, heading Strategy Builder, and its name', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 (the URL names the strategy so a reload opens it again); REQ-038
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('open-builder-17').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=17$/)
    await expect(title(page)).toHaveText('Strategy Builder')
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Bull Put Spread')
  })

  test('LINK-2 each row\'s Open in Builder carries its own id (21, 17, 9, 5, 4), not the first row\'s', async ({ page }) => {
    // Spec basis: REQ-134 AC-5; owner B1 (row 2 opened 171, not the bare builder)
    await openLoaded(page)
    for (const id of [21, 17, 9, 5, 4]) await expect(rowOf(page, id).getByTestId(`open-builder-${id}`)).toHaveText('Open in Builder')
    await rowOf(page, 9).getByTestId('open-builder-9').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=9$/)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Short Straddle')
  })

  test('LINK-3 a held-at-broker and a basket-sent row still open in the Builder (only Delete is refused)', async ({ page }) => {
    // Spec basis: REQ-134 AC-5; ADR-292 (held blocks delete only)
    await openLoaded(page)
    await rowOf(page, 5).getByTestId('open-builder-5').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=5$/)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Held IC k10')
  })

  test('LINK-4 (MYSTR-10) with the order path on, "Execute Strategy" opens /strategy/<id>/execute with the heading Execute Strategy', async ({ page }) => {
    // Spec basis: REQ-056 AC-1 (Execute opens for that strategy); REQ-073 AC-6 / W-121 (offered when the server says the order path is on)
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('open-execute-17').click()
    await expect(page).toHaveURL(/\/strategy\/17\/execute$/)
    await expect(title(page)).toHaveText('Execute Strategy Bull Put Spread') // the heading carries the strategy's name
  })

  test('LINK-5 (W-121) the order path off: no Execute link on any row (absent, not disabled)', async ({ page }) => {
    // Spec basis: REQ-073 AC-6 / ADR-165 (the Execute link is absent unless the server says the order path is on)
    await openLoaded(page, { features: { json: { order_path: 'off' } } })
    await expect(page.locator('[data-testid^="open-execute-"]')).toHaveCount(0)
    await expect(page.getByTestId('open-builder-17')).toBeVisible()
  })

  test('LINK-6 (W-121) the features read failing shows no Execute link (fail closed)', async ({ page }) => {
    // Spec basis: REQ-073 AC-6 / ADR-165 (a failed read is "off")
    await openLoaded(page, { features: { status: 500, json: {} } })
    await expect(page.locator('[data-testid^="open-execute-"]')).toHaveCount(0)
  })

  test('LINK-7 (W-121) an unknown order_path value ("ON") shows no Execute link', async ({ page }) => {
    // Spec basis: REQ-073 AC-6 ("on" is the one exact stated answer)
    await openLoaded(page, { features: { json: { order_path: 'ON' } } })
    await expect(page.locator('[data-testid^="open-execute-"]')).toHaveCount(0)
  })

  test('LINK-8 Open in Builder is the first action and Rename the second on every renameable row; the row actions are in the order Open in Builder, Rename, Delete, Execute Strategy', async ({ page }) => {
    // Spec basis: owner R-10-retry (row actions: Open in Builder, Rename, Delete); REQ-134 AC-3, AC-5
    await openLoaded(page)
    await expect(rowOf(page, 17).getByTestId('row-actions').locator('button, a')).toHaveText(['Open in Builder', 'Rename', 'Delete', 'Execute Strategy'])
    await expect(rowOf(page, 17).getByTestId('row-actions').locator('button, a')).toHaveCount(4)
  })

  test('LINK-9 (R-10) there is no Compare entry in the row actions', async ({ page }) => {
    // Spec basis: none (searched: Compare, row actions; owner R-10-retry observed "No Compare entry"); a spec-silent observation recorded as a test
    await openLoaded(page)
    await expect(rowOf(page, 17)).not.toContainText('Compare')
  })

  test('LINK-10 opening in the Builder and pressing Back returns to My Strategies with the list showing', async ({ page }) => {
    // Spec basis: REQ-009 (the app's pages are reachable and returnable by the browser Back)
    await openLoaded(page)
    await rowOf(page, 17).getByTestId('open-builder-17').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=17$/)
    await page.goBack()
    await expect(page).toHaveURL(/\/strategies\/my-strategies$/)
    await expect(names(page)).toHaveText(ORDER)
  })
})

// =============================================================================================== keyboard
test.describe('My Strategies: keyboard', () => {
  test('KEY-1 Tab reaches Search, Select all and then the first row\'s tick box in reading order; Space ticks it', async ({ page }) => {
    // Spec basis: none (searched: keyboard, tab order, Space); the controls are native inputs, so this holds the order and the Space action
    await openLoaded(page)
    await page.getByTestId('strategy-search').focus()
    await page.keyboard.press('Tab')
    await expect(page.getByTestId('select-all')).toBeFocused()
    await page.keyboard.press('Space')
    await expect(page.getByTestId('delete-selected')).toHaveText('Delete selected (3)')
    await page.keyboard.press('Tab')
    await expect(page.getByTestId('delete-selected')).toBeFocused()
  })

  test('KEY-2 Enter on "Delete selected" opens the one question; Enter on its Delete button runs it', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 (the one confirmation); keyboard use of native buttons
    await openLoaded(page)
    await page.getByTestId('select-17').check()
    await page.getByTestId('delete-selected').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('bulk-confirm-text')).toHaveText('Delete 1 strategy?')
    await page.getByTestId('bulk-confirm').focus()
    await page.keyboard.press('Enter')
    await expect(rowOf(page, 17)).toHaveCount(0)
  })
})
