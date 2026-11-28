// Lane W3 item 2: T3-15 bulk delete of 3 + Undo, and own delete + Undo; the history entries. ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const hist = async (id) => { const r = await page.request.get(`${M}/strategies/${id}/history`); const j = await r.json().catch(() => ({})); return r.status() + ' ' + JSON.stringify((j.entries || j)).slice(0, 700) }
  await page.goto(M + '/strategies/my-strategies'); await page.waitForTimeout(8000); await page.getByPlaceholder(/search/i).first().fill('HIST-'); await sleep(1500)
  const ids = {}; const t0 = await T(); console.log('rows:', t0.match(/HIST-\d+ \(#\d+/g))
  for (const n of ['HIST-16', 'HIST-17', 'HIST-18']) await page.getByRole('checkbox', { name: new RegExp(n) }).check()
  await page.getByRole('button', { name: /Delete selected \(3\)/ }).click(); await page.getByRole('button', { name: /^Delete$/ }).first().click(); await sleep(3000)
  await page.getByRole('button', { name: /^Undo$/ }).first().click(); await sleep(3000); let t = await T(); console.log('after bulk Undo, rows:', t.match(/HIST-\d+ \(#\d+/g), '| line:', (t.match(/[^|]*(restored|Restored)[^|]*/) || ['<no restored line>'])[0])
  for (const id of [16, 17, 18]) console.log(`history #${id}:`, await hist(id))
  // own delete + Undo of HIST-19
  await page.getByPlaceholder(/search/i).first().fill('HIST-19'); await sleep(1500); await page.getByRole('button', { name: /^Delete$/ }).first().click(); await sleep(600); await page.getByRole('button', { name: /^Delete$/ }).last().click(); await sleep(2500)
  await page.getByRole('button', { name: /^Undo$/ }).first().click(); await sleep(3000); console.log('history #19 (single):', await hist(19)); await page.screenshot({ path: `${OUT}/c6-after-undo.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
