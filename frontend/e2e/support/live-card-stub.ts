// Lane T: one stub of every /api call and the strategy live socket that the Live Strategies page makes (the page, its cards and
// the paper P&L list). Used by screen-live-strategies.spec.ts. Everything the page shows is served from here, so no database,
// broker or market is needed; the socket is played by the test (push, drop, refuse), and every follow message the page sends
// is recorded. Same style as the Home screen stub (screen-home.spec.ts): a Reply is {status, json} or {abort} or a gate.
import type { Page, Route, WebSocketRoute } from '@playwright/test'
import { echoSeq } from './echoSeq'

export const T_NOW = '2026-11-26T10:00:00+05:30'
export const T_CHECK = '2026-11-26T10:00:01+05:30'
export const EXPIRY = '2026-12-01'

export type Reply = { status?: number; json?: unknown; text?: string; abort?: boolean; wait?: Promise<void> }
export const ok = (json: unknown): Reply => ({ json })
export const gate = () => {
  let open!: () => void
  const wait = new Promise<void>((r) => { open = r })
  return { wait, open }
}

export const CATALOGUE_PARTS = {
  what_happened: 'Saved strategies could not be read.', impact: 'The list is missing.',
  what_is_blocked: 'Nothing else is blocked.', next_action: 'Try again shortly.',
}
export const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}

export type Row = {
  id: number; name: string | null; underlying: string; status_word: 'Draft' | 'Running' | 'Completed'
  updated_at: string; open_opportunities_text?: string | null
}
export const row = (id: number, name: string | null, status_word: Row['status_word'], updated_at: string, extra: Partial<Row> = {}): Row =>
  ({ id, name: name === null ? null : `"${name}"`, underlying: 'NIFTY', status_word, updated_at, ...extra })

// The contracts of the stub catalogue: id -> token. A strategy follows its own contracts, so the socket knows whose follow it is.
export const CONTRACTS = [
  { contract_id: 501, exchange_segment: 'NSE_FO', exchange_token: 50501, instrument_type: 'CE', expiry: EXPIRY, strike: '25900.00', lot_size: 65, symbol: 'NIFTY25DEC25900CE' },
  { contract_id: 502, exchange_segment: 'NSE_FO', exchange_token: 50502, instrument_type: 'PE', expiry: EXPIRY, strike: '25650.00', lot_size: 65, symbol: 'NIFTY25DEC25650PE' },
  { contract_id: 503, exchange_segment: 'NSE_FO', exchange_token: 50503, instrument_type: 'CE', expiry: EXPIRY, strike: '26000.00', lot_size: 65, symbol: 'NIFTY25DEC26000CE' },
  { contract_id: 504, exchange_segment: 'NSE_FO', exchange_token: 50504, instrument_type: 'CE', expiry: EXPIRY, strike: '25800.00', lot_size: 65, symbol: 'NIFTY25DEC25800CE' },
  { contract_id: 505, exchange_segment: 'NSE_FO', exchange_token: 50505, instrument_type: 'PE', expiry: EXPIRY, strike: '25500.00', lot_size: 65, symbol: 'NIFTY25DEC25500PE' },
]
const cid = (n: number) => CONTRACTS.find((c) => c.contract_id === n)!

/** A paper book (GET /paper/strategies/{id}): the open positions of a Running trade. */
export function paperBookOf(id: number, held: [number, number, string][], over: Record<string, unknown> = {}) {
  return {
    strategy_id: id, underlying: 'NIFTY', answered_at: T_NOW,
    orders: [{ id: 1 }, { id: 2 }],
    positions: held.map(([contract_id, net_quantity, average]) => ({ contract_id, net_quantity, average, expiry: EXPIRY, price_at: T_NOW })),
    max_profit_text: '+13,066.25', max_loss_text: 'No fixed maximum', breakevens_display: ['25,420.00', '26,170.00'],
    ...over,
  }
}
/** A saved plan (GET /strategies/{id}) of a Draft: one saved leg per [contract_id, action, planned entry]. */
export function savedOf(id: number, legs: [number, 'BUY' | 'SELL', string | null][], row_: Row) {
  return {
    ...row_, id, revision: 1, created_at: row_.updated_at,
    definition: { underlying: 'NIFTY', legs: legs.map(([c, action, entry]) => {
      const k = cid(c)
      return { contract_id: c, contract_state: 'live', exchange_segment: k.exchange_segment, exchange_token: k.exchange_token, action, instrument: k.instrument_type,
        strike: k.strike, expiry: EXPIRY, quantity: k.lot_size, planned_entry: entry, captured_at: entry === null ? null : T_NOW }
    }) },
  }
}

/** A paper-list group (GET /paper/strategies): the figure the Positions page shows and the Live card repeats. */
export const paperGroup = (id: number, over: Record<string, unknown> = {}) => ({
  strategy_id: id, name: `"Short Iron Condor"`, underlying: 'NIFTY', state: 'LIVE', status_word: 'Running', open_count: 1, position_count: 1,
  total_text: '+225.00', total_after_text: '+190.50', booked_text: '+0.00', unbooked_text: '+225.00', after_charges_reason: null, positions: [], ...over,
})
export const paperList = (groups: unknown[]) => ({ strategies: groups, totals: null, answered_at: T_NOW })

/** One leg of an outcome answer. */
export const oleg = (contract_id: number, action: 'BUY' | 'SELL', ltp: string | null, health: string | null = 'available', entry: string | null = '171.70') => {
  const k = cid(contract_id)
  return { instrument_id: `${k.exchange_segment}:${k.exchange_token}`, action, strike: k.strike, instrument_type: k.instrument_type, expiry: EXPIRY, lots: 1,
    planned_entry: entry, ltp, health }
}
export const computed = (legs: unknown[], over: Record<string, unknown> = {}) => ({
  state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null, market_closed: false,
  spot_level: '25790.35', spot_at: T_NOW, last_price_at: T_NOW, answered_at: T_CHECK,
  summary: { max_profit: '13066.25', max_loss: '0.00', max_profit_unlimited: false, max_loss_unlimited: false, max_profit_display: '+13,066.25', max_loss_display: '−4,000.00' },
  legs, ...over,
})

export type Stub = {
  strategies: Reply; paperList: Reply; alerts: Reply; opps: Reply; dismiss: (id: number, body: unknown) => Reply
  book: Record<number, Reply>; saved: Record<number, Reply>; catalogue: Reply; outcome: Reply
  /** the answer sent on a socket when it receives its follow; by owner (strategy id). Absent: no answer is sent. */
  auto: Record<number, () => unknown>
  sockets: { owner: number; ws: WebSocketRoute; stamp: (p: object) => object; pushStamped: (p: object) => void; body: any }[]
  follows: { owner: number; body: any }[]
  refuseSockets: boolean
  posts: { path: string; body: unknown }[]
  calls: string[]
  push: (owner: number, msg: object) => void
  drop: (owner: number) => Promise<void>
  /** the connection of the newest socket of this owner */
  last: (owner: number) => Stub['sockets'][number]
}

const ownerOf = (body: any): number => {
  const token = String(body?.legs?.[0]?.instrument_id ?? '').split(':')[1]
  const c = CONTRACTS.find((x) => String(x.exchange_token) === token)
  return OWNER_OF_CONTRACT[c?.contract_id ?? 0] ?? 0
}
// The first contract of each strategy's open legs decides whose socket it is.
export const OWNER_OF_CONTRACT: Record<number, number> = { 501: 171, 502: 172, 504: 170, 505: 168, 503: 0 }

export async function stubLive(page: Page, over: Partial<Stub> = {}): Promise<Stub> {
  const S: Stub = {
    strategies: ok({ strategies: [] }), paperList: ok(paperList([])), alerts: ok({ unread: 0, alerts: [] }), opps: { status: 503, json: {} }, dismiss: () => ({ status: 503, json: {} }),
    book: {}, saved: {}, catalogue: ok({ contracts: CONTRACTS }), outcome: { status: 503, json: {} },
    auto: {}, sockets: [], follows: [], refuseSockets: false, posts: [], calls: [],
    push: (owner, msg) => S.last(owner).pushStamped(msg), // same payload plus the version stamp (REQ-133 AC-2)
    drop: async (owner) => { S.refuseSockets = true; await S.last(owner).ws.close() },
    last: (owner) => S.sockets.filter((s) => s.owner === owner).at(-1)!,
    ...over,
  }
  const serve = async (route: Route, r: Reply) => {
    if (r.wait) await r.wait
    if (r.abort) return route.abort('connectionrefused')
    if (r.text !== undefined) return route.fulfill({ status: r.status ?? 200, contentType: 'application/json', body: r.text })
    return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname, searchParams } = new URL(req.url())
    const get = req.method() === 'GET'
    S.calls.push(`${req.method()} ${pathname}`)
    if (get && pathname === '/api/strategies') return serve(route, S.strategies)
    if (get && pathname === '/api/paper/strategies') return serve(route, S.paperList)
    if (get && pathname === '/api/adjustment-opportunities') return serve(route, S.opps)
    const dis = /^\/api\/adjustment-opportunities\/(\d+)\/dismiss$/.exec(pathname)
    if (dis && req.method() === 'POST') { const b = req.postDataJSON(); S.posts.push({ path: pathname, body: b }); return serve(route, S.dismiss(Number(dis[1]), b)) }
    if (get && pathname === '/api/paper/alerts') return serve(route, S.alerts)
    if (get && pathname === '/api/market/indices') return route.fulfill({ json: { state: 'NOT_CONNECTED', answered_at: T_NOW, last_price_at: null, market_closed: false, indices: [] } })
    if (get && pathname === '/api/catalogue/NIFTY/contracts') { void searchParams; return serve(route, S.catalogue) }
    const book = /^\/api\/paper\/strategies\/(\d+)$/.exec(pathname)
    if (get && book) return serve(route, S.book[Number(book[1])] ?? { status: 404, json: { detail: 'not found' } })
    const one = /^\/api\/strategies\/(\d+)$/.exec(pathname)
    if (get && one) return serve(route, S.saved[Number(one[1])] ?? { status: 404, json: { detail: 'not found' } })
    if (req.method() === 'POST' && pathname === '/api/strategies/outcome') {
      S.posts.push({ path: pathname, body: req.postDataJSON() })
      return serve(route, S.outcome)
    }
    return route.fulfill({ status: 503, json: {} })
  })
  await page.routeWebSocket('**/api/market/indices/live', () => {}) // the shell's index strip: held open, silent
  await page.routeWebSocket('**/api/strategies/live', (ws) => {
    if (S.refuseSockets) { ws.close(); return }
    const seq = echoSeq()
    const entry = { owner: 0, ws, stamp: (p: object) => seq.stamp(p), pushStamped: (p: object) => ws.send(JSON.stringify(seq.stamp(p))), body: null as any }
    S.sockets.push(entry)
    ws.onMessage((m) => {
      seq.remember(m)
      const body = JSON.parse(String(m))
      entry.owner = ownerOf(body)
      entry.body = body
      S.follows.push({ owner: entry.owner, body })
      const answer = S.auto[entry.owner]
      if (answer) ws.send(JSON.stringify(seq.stamp(answer() as object)))
    })
  })
  return S
}
