const { chromium } = require('playwright'); const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/home/overview'); await sleep(10000); let t = await T(); const home = (t.match(/Total P&L \(after charges\) \| ([+−\-\d,.]+) \| ([^|]*)\| ([^|]*)\| ([^|]*)/) || []).slice(1); console.log('Home total:', home.join(' | '), '| at', new Date().toISOString())
  await page.goto(M + '/strategies/my-strategies'); await sleep(10000); t = await T(); const rows = [...t.matchAll(/P&L ([+−\-][\d,]+\.\d\d) \(after charges\) \| ([^|]+?) \(#(\d+)/g)].map(m => [m[3], m[2], m[1]]); const paused = [...t.matchAll(/P&L — · Paper P&L paused[^|]*\| ([^|]+?) \(#(\d+)/g)].map(m => [m[2], m[1], 'paused']); console.log('My Strategies rows with P&L:', JSON.stringify(rows)); console.log('paused rows:', JSON.stringify(paused)); console.log('my strategies counts line:', JSON.stringify((t.match(/(Running|Completed|Draft)[^|]{0,30}\d+[^|]{0,40}/g) || []).slice(0, 4)))
  const num = (s) => Number(s.replace('−', '-').replace(/,/g, '')); const sum = rows.reduce((a, r) => a + num(r[2]), 0); console.log('sum of running rows with P&L:', sum.toFixed(2), '| Home total:', home[0], '| difference Home - sum:', (num(home[0]) - sum).toFixed(2))
  await browser.close() })()
