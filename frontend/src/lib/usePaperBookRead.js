// GC-ICFIX round 2 (F4): the trade page's ONE read of GET /paper/strategies/{id} per refresh (the page's rhythm, usePaperRefresh).
// Its reply feeds the paper panel, the tracking box's total and the P&L table TOTAL row, so all three show one moment. The reply is
// always taken (it is the truth); when its open contracts differ from the shown ones `contractsChanged` stays true (the screen's net
// legs belong to the old set: the panel says so and asks for a reload). A failed read sets `readFailed`: the last figures stay.
// A trade with no open contract is final: no more reads.
import { ref, watch } from 'vue'
import api from '@/services/api'
import { usePaperRefresh } from '@/lib/usePaperRefresh'

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
