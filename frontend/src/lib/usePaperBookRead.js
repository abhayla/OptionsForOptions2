// GC-ICFIX round 2 (F4): the trade page's ONE read of GET /paper/strategies/{id} per refresh (the page's rhythm, usePaperRefresh).
// Its reply feeds the paper panel, the tracking box's total and the P&L table TOTAL row, so all three show one moment. The reply is
// always taken (it is the truth); when its open contracts differ from the shown ones `contractsChanged` stays true (the screen's net
// legs belong to the old set: the panel says so and asks for a reload). A failed read sets `readFailed`: the last figures stay.
// A trade with no open contract is final: no more reads.
// D-41 (modular doors, Phase 3): this module is also the ONE reader of that reply for every panel that shows a leg price or the P&L
// headline: `legPricesOf` (the LegPrice of each open contract) and `paperPnlBlock` (the headline total plus those LegPrices). The Net
// Positions table and the Paper P&L panel read the same book, so a leg has one price source (the book's display price, ADR-212: in hours
// the live price, after hours the last close). Texts are the server's, as sent (ADR-008); nothing is added or compared here.
import { ref, watch } from 'vue'
import api from '@/services/api'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { sharedTotal } from '@/lib/tracking'
import { PAPER_NO_FIGURE } from '@/lib/paperList'

const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)

/** LegPrice (a plain object): one open contract's price, quote time and own TOTAL (booked plus still open, ADR-328 (3)), as the
 *  book sent them. Keyed by the contract id text; a flat contract has none; null = the server sent none. */
export function legPricesOf(book, failed = false) {
  const out = new Map()
  for (const p of Array.isArray(book?.positions) ? book.positions : []) {
    if (p.net_quantity === 0) continue
    // #744: a failed read prints the one dash the legs table prints, never the last figures (entry, LTP, TOTAL; no quote time, no reason text)
    if (failed) { out.set(String(p.contract_id), { entry: PAPER_NO_FIGURE, ltp: PAPER_NO_FIGURE, at: null, total: PAPER_NO_FIGURE, noPrice: null }); continue }
    out.set(String(p.contract_id), { entry: text(p.average_text), ltp: text(p.ltp_text), at: p.price_at ?? null, total: text(p.total_text), noPrice: text(p.no_price_text) })
  }
  return out
}

/** N-07: the P&L Table's per-leg figures for a paper trade, keyed by the page leg's instrument_id (the outcome reply's leg identity). Each is
 *  the legs table's own cell text (entry = Avg, ltp = LTP, pnl = the leg's TOTAL); a failed read prints the same dash the table does. A page
 *  leg whose contract the book does not hold is absent. Each entry carries the net leg's side and lots: the P&L Table uses it only for a reply row of the same contract, side and lots. null = not a paper trade (no book or net). */
export function paperLegsOf(net, book, failed = false) {
  if (!book || !Array.isArray(net)) return null
  const prices = legPricesOf(book)
  const out = new Map()
  // `priced`: the book sent an LTP text for this leg and the read did not fail (the leg list's "now" price needs a real figure, not a dash)
  for (const l of net) {
    const p = l?.contract_id == null || typeof l.instrument_id !== 'string' ? undefined : prices.get(String(l.contract_id))
    if (p === undefined) continue
    out.set(l.instrument_id, { action: l.action, lots: l.lots, priced: !failed && p.ltp !== null, ...(failed ? { entry: PAPER_NO_FIGURE, ltp: PAPER_NO_FIGURE, pnl: PAPER_NO_FIGURE } : { entry: p.entry ?? '-', ltp: p.ltp ?? '-', pnl: p.total ?? '-' }) })
  }
  return out
}

/** The one P&L block of a paper book: the headline (sharedTotal: after charges, or the labelled before text, or paused, with its
 *  as-of line) and the LegPrice of every open contract. null = no book. */
export function paperPnlBlock(book, failed = false) {
  const total = sharedTotal(book, failed)
  if (total === null) return null
  const legs = legPricesOf(book, failed) // #744: a failed read gives the dash rows, the same as the legs table and the P&L Table
  return { ...total, failed, legs }
}

const openKey = (b) => (b?.positions ?? []).filter((p) => p.net_quantity !== 0).map((p) => `${p.contract_id}:${p.net_quantity}`).join(',')

export function usePaperBookRead({ key, book, onBook, enabled = () => true }) {
  const readFailed = ref(false)
  const contractsChanged = ref(false)
  watch(key, () => { readFailed.value = false; contractsChanged.value = false })
  usePaperRefresh({
    key,
    enabled: () => enabled() && openKey(book()) !== '',
    read: async (id) => (await api.get(`/paper/strategies/${id}`)).data,
    onData: (b) => {
      readFailed.value = false
      if (openKey(b) !== openKey(book())) contractsChanged.value = true
      onBook(b)
    },
    onError: () => { readFailed.value = true }, // the last values stay; the lines say they are old
  })
  return { readFailed, contractsChanged }
}
