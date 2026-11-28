const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategy/builder'); await sleep(5000); await page.getByRole('button', { name: 'Ready-made' }).click().catch(() => {}); await sleep(1000)
  await page.getByRole('button', { name: 'Bull Put Spread' }).first().click(); await sleep(6000)
  console.log('controls (label/aria) in legs area:', JSON.stringify(await page.locator('select,input,button').evaluateAll(x => x.map(e => (e.getAttribute('aria-label') || e.innerText || e.placeholder || '').trim()).filter(s => s && s.length < 50 && /leg|strike|Buy|Sell|Save|Add|expiry|lots/i.test(s)))))
  await page.screenshot({ path: `${OUT}/c15-bps.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
