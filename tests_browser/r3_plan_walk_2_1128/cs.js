const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  await page.goto('http://127.0.0.1:4173/strategies/create-strategy'); await page.waitForTimeout(5000); console.log('CREATE:', (await T()).slice(60, 900))
  const g = page.getByRole('button', { name: /Guided/ }).first(); if (await g.count()) { await g.click(); await page.waitForTimeout(2000) }
  console.log('GUIDED:', (await T()).slice(60, 700))
  const k = page.getByText(/I already know my strategy/).first(); if (await k.count()) { await k.click(); await page.waitForTimeout(2000) }
  const n = page.getByRole('button', { name: /^NIFTY$/ }).first(); if (await n.count()) { await n.click(); await page.waitForTimeout(6000) }
  const t = await T(); console.log('AFTER NIFTY:', t.slice(60, 1100)); console.log('took-too-long box?', /took too long|too long/i.test(t)); await sh('t317-1-create-guided')
  // T-Q7 chain
  await page.goto('http://127.0.0.1:4173/market/option-chain'); await page.waitForTimeout(8000); const c = await T(); console.log('CHAIN days:', (c.match(/[^|]*days? left[^|]*/gi) || []).slice(0, 6)); console.log('CHAIN head:', c.slice(60, 600)); await sh('t317-2-chain')
  const ex = await (await page.request.get('http://127.0.0.1:4173/api/catalogue/NIFTY/expiries')).text().catch(() => ''); console.log('EXPIRIES api:', ex.slice(0, 400))
  await browser.close() })()
