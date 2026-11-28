// Lane W3 item 2: T2-09 Dismiss + own Delete line, T3-15 Undo and the history entries (via the page's own history route). ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const line = async () => ((await T()).match(/\d+ deleted \| Undo \| Dismiss|\d+ deleted[^|]*\|[^|]*\|[^|]*/) || ['<no line>'])[0]
  const hist = async (id) => { const r = await page.request.get(`${M}/strategies/${id}/history`); const j = await r.json().catch(() => ({})); return (j.entries || []).map(e => `${e.kind || e.label || ''}:${e.title || e.text || JSON.stringify(e).slice(0, 60)}`) }
  await page.goto(M + '/strategies/my-strategies'); await page.waitForTimeout(8000); await page.getByPlaceholder(/search/i).first().fill('UNDOTEST'); await page.waitForTimeout(1500)
  // bulk 3 (5,6,7), keep line 31 s, Dismiss
  for (const n of ['UNDOTEST-5', 'UNDOTEST-6', 'UNDOTEST-7']) await page.getByRole('checkbox', { name: new RegExp(n) }).check()
  await page.getByRole('button', { name: /Delete selected \(3\)/ }).click(); await page.getByRole('button', { name: /^Delete$/ }).first().click(); await sleep(3000); console.log('bulk line at 3 s:', await line())
  await sleep(29000); console.log('bulk line at 32 s:', await line()); await page.screenshot({ path: `${OUT}/c4-1-line-32s.jpg`, type: 'jpeg', quality: 55 })
  await page.getByRole('button', { name: /^Dismiss$/ }).first().click(); await sleep(1500); console.log('after Dismiss:', await line())
  // own Delete of UNDOTEST-4: line, Dismiss
  await page.getByRole('button', { name: /^Delete$/ }).first().click(); await sleep(800); console.log('own Delete confirm:', ((await T()).match(/Delete UNDOTEST[^|]*\|[^|]*\|[^|]*|Delete this[^|]*\|[^|]*\|[^|]*|Delete [^|?]*\?[^|]*\|[^|]*\|[^|]*/) || ['<none>'])[0])
  await page.getByRole('button', { name: /^Delete$/ }).first().click().catch(() => {}); await sleep(3000); console.log('own Delete line:', await line()); await page.getByRole('button', { name: /^Dismiss$/ }).first().click().catch(() => console.log('no Dismiss')); await sleep(1000); console.log('after own Dismiss:', await line())
  await browser.close() })()
