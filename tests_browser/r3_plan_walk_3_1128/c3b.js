const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/strategies/my-strategies'); await page.waitForTimeout(8000)
  await page.getByPlaceholder(/search/i).first().fill('UNDOTEST'); await page.waitForTimeout(1500)
  for (const n of ['UNDOTEST-1', 'UNDOTEST-2', 'UNDOTEST-3']) await page.getByRole('checkbox', { name: new RegExp(n) }).check()
  await page.getByRole('button', { name: /Delete selected \(3\)/ }).click(); await page.waitForTimeout(1500)
  let t = await T(); console.log('after Delete selected:', t.slice(t.indexOf('My Strategies'), t.indexOf('My Strategies') + 500)); console.log('buttons:', (await page.getByRole('button').allInnerTexts()).slice(0, 20)); await page.screenshot({ path: `${OUT}/c3b-1.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
