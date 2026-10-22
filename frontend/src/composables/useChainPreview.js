// W-124 (REQ-031 AC-1/AC-2): the Option Chain's live preview read. ONE read-only call to the server's preview route, which
// answers with the outcome route's own numbers for the selected legs (net premium, max profit / loss, breakevens, payoff
// points, the matched template's name). It is not an order, basket, margin or execute call (REQ-029 AC-6, ADR-002); kept
// out of the page file so the page's no-order scan can stay strict. Nothing is computed here.
import api from '@/services/api'
import { PREVIEW_PATH } from '@/lib/chainDisplay'

/** The server's preview answer for `legs` (see chainDisplay.previewLegs), or null when the read failed. */
export async function readChainPreview(underlying, legs) {
  try {
    const { data } = await api.post(PREVIEW_PATH, { underlying, legs })
    return data && typeof data === 'object' ? data : null
  } catch {
    return null
  }
}
