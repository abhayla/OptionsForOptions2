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

const text = (v) => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)

/** LegPrice (a plain object): one open contract's price, quote time and own TOTAL (booked plus still open, ADR-328 (3)), as the
 *  book sent them. Keyed by the contract id text; a flat contract has none; null = the server sent none. */
export function legPricesOf(book) {
  const out = new Map()
  for (const p of Array.isArray(book?.positions) ? book.positions : []) {
    if (p.net_quantity === 0) continue
    out.set(String(p.contract_id), { ltp: text(p.ltp_text), at: p.price_at ?? null, total: text(p.total_text), noPrice: text(p.no_price_text) })
  }
  return out
}

/** The one P&L block of a paper book: the headline (sharedTotal: after charges, or the labelled before text, or paused, with its
 *  as-of line) and the LegPrice of every open contract. null = no book. */
export function paperPnlBlock(book, failed = false) {
  const total = sharedTotal(book, failed)
  return total === null ? null : { ...total, legs: legPricesOf(book) }
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
