const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, f) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55, fullPage: !!f })
  const go = async (u, w = 9000) => { await page.goto(M + u); await page.waitForTimeout(w); return T() }
  let t = await go('/positions/current-positions'); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await page.waitForTimeout(6000); t = await T()
  console.log('D-TG-5 paused sentence count (Paper):', (t.match(/Paper P&L paused - prices not live/g) || []).length, '| sample', (t.match(/Paper P&L paused[^|]*/g) || []).slice(0, 2)); await sh('r5-d5-positions-paper', true)
  console.log('D-TG-1 P&L texts:', (t.match(/no price/g) || []).length, 'no-price cells | totals', (t.match(/Total P&L[^|]*\|[^|]*/g) || []).slice(0, 2))
  t = await go('/positions/current-positions'); await page.getByRole('button', { name: /^Real$/ }).first().click().catch(() => {}); await page.waitForTimeout(6000); t = await T()
  console.log('D-TG-3 raw JSON on Positions Real:', /error_class|BROKER_AUTHENTICATION/.test(t), '|', t.slice(t.indexOf('Real'), t.indexOf('Real') + 400)); await sh('r5-d3-positions-real', true)
  t = await go('/strategies/live-strategies'); console.log('Live: paused count', (t.match(/paused/g) || []).length, '| sample', (t.match(/P&L[^|]*\|[^|]*/g) || []).slice(0, 3)); await sh('r5-live', true)
  t = await go('/home/overview'); console.log('HOME:', (t.match(/Total P&L[^|]*\|[^|]*|Includes[^|]*|[0-9]+ strateg[^|]*left out[^|]*/g) || [])); await sh('r5-home')
  t = await go('/strategy/builder?strategy=1', 10000); console.log('AF-06 No price for line:', /No price for:/.test(t), '| banner', (t.match(/Market closed\.[^|]*/) || [])[0], '| builder paused count', (t.match(/Paper P&L paused[^|]*/g) || []).length); await sh('af06-builder')
  await browser.close() })()
