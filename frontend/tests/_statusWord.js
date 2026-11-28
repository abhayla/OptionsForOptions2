// GC-ICLIVE D-28 round 2: the server (strategy_store.status_word) sends `status_word` on every strategy row; the browser only reads it.
// A fixture row written with the stored status and has_order gets the word the server's one function would send.
export const serverWord = (r) => r.status_word ?? (r.status === 'closed' ? 'Completed' : r.status === 'draft' ? (r.has_order ? 'Running' : 'Draft') : 'Unknown')
export const withWords = (data) => (data && Array.isArray(data.strategies) ? { ...data, strategies: data.strategies.map((r) => ({ ...r, status_word: serverWord(r) })) } : data)
export const withWord = (r) => ({ ...r, status_word: serverWord(r) })
