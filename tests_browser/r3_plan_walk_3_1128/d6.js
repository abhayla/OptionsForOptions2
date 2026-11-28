const { chromium } = require('playwright'); const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategies/my-strategies'); await sleep(10000)
  const rows = await page.locator('[data-testid^="strategy-row"], tbody tr, li').evaluateAll(x => x.map(e => e.innerText.replace(/\s+/g, ' ').trim()).filter(s => /\(#\d+/.test(s)).slice(0, 14)); console.log('rows via DOM:', rows.length); rows.forEach(r => console.log('  ', r.slice(0, 230)))
  await page.goto(M + '/home/overview'); await sleep(9000); const t = (await page.locator('body').innerText()).replace(/\n+/g, ' | '); console.log('Home:', (t.match(/Running strategies[^]{0,330}/) || [''])[0].slice(0, 330))
  await browser.close() })()
