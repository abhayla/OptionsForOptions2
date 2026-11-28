const { chromium } = require('playwright')
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 768 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto('http://127.0.0.1:4174/strategy/builder?adjust=2&opp=3,4,5,6'); await page.waitForTimeout(9000)
  const sel = page.getByLabel('Approach to prepare'); const vals = await sel.first().locator('option').evaluateAll(o => o.map(x => x.value))
  for (const v of vals) { await sel.first().selectOption(v); await page.waitForTimeout(500)
    await page.getByRole('button', { name: /prepare basket/i }).first().click(); await page.waitForTimeout(4000)
    const t = await T(); const i = t.indexOf('Open in builder and prepare basket'); console.log(v, '=>', t.slice(i, i + 330)); 
    const url = page.url(); console.log('   url', url.slice(0, 120)); if (!/adjust=2&opp/.test(url)) { await page.goto('http://127.0.0.1:4174/strategy/builder?adjust=2&opp=3,4,5,6'); await page.waitForTimeout(8000) } }
  await browser.close() })()
