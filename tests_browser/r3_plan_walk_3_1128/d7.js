// Lane W3: D-W3-1 original cause on 8425feead: the Review dialog for a leg with NO stored close (#3 TC Unpriced Trade)
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp2'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategy/builder?strategy=3'); await sleep(9000); console.log('legs:', (await page.locator('table tbody tr').allInnerTexts()).filter(r => /NIFTY \d+ [PC]E/.test(r)).slice(0, 3).map(r => r.replace(/\s+/g, ' ').slice(0, 70)))
  const sel = page.getByLabel('Change expiry of leg 1'); console.log('expiry select count', await sel.count()); await sel.selectOption({ index: 1 }); await sleep(2500)
  await page.getByRole('button', { name: /Review/ }).first().click(); const t0 = Date.now()
  for (let i = 0; i < 6; i++) { await sleep(5000); const d = (await page.getByRole('dialog').first().innerText().catch(() => '')).replace(/\s+/g, ' '); console.log(`${Math.round((Date.now() - t0) / 1000)} s:`, /Checking whether this exit/.test(d) ? 'Checking... still shown' : 'resolved', '|', d.slice(0, 380)) }
  await page.screenshot({ path: `${OUT}/d7-review-unpriced.jpg`, type: 'jpeg', quality: 55 }); await browser.close() })()
