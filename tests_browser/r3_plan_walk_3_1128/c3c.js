const { chromium } = require('playwright'); const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/strategies/my-strategies'); await page.waitForTimeout(8000); let t = await T()
  console.log('rows:', (t.match(/UNDOTEST-\d/g) || []).join(','), '| any "deleted" text:', JSON.stringify(t.match(/[^|]*deleted[^|]*/gi)))
  const r = await page.request.get(M + '/api/strategies?include_deleted=1').catch(() => null); console.log('api deleted listing status', r && r.status())
  await browser.close() })()
