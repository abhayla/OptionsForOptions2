const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const APP = process.env.APP_ID || 'A-28'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 768 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const opp = async () => { await page.goto('http://127.0.0.1:4174/positions/adjustment-opportunities'); await page.waitForTimeout(4000); const t = await T(); const m = t.slice(t.indexOf('Open:')); return m.slice(0, 120) + ' ## ' + (t.match(/(Open|Acted on[^|]*|Your rule was triggered)\s*\|/g) || []).join(' ; ') }
  const prep = async () => { await page.goto('http://127.0.0.1:4174/strategy/builder?adjust=2&opp=3,4,5,6'); await page.waitForTimeout(9000)
    await page.getByLabel('Approach to prepare').first().selectOption(APP); await page.getByRole('button', { name: /prepare basket/i }).first().click(); await page.waitForTimeout(6000) }
  console.log('BEFORE:', await opp())
  await prep(); await page.getByRole('button', { name: /^Review and add$/ }).first().click(); await page.waitForTimeout(8000)
  let t = await T(); console.log('CONFIRM LIST:', t.slice(t.indexOf('Review'), t.indexOf('Review') + 1100)); await sh('w10-2-confirm-list')
  await page.getByRole('button', { name: /^Cancel$/ }).first().click(); await page.waitForTimeout(2500); await sh('w10-3-after-cancel')
  console.log('AFTER CANCEL (opps):', await opp())
  await prep(); await page.getByRole('button', { name: /^Review and add$/ }).first().click(); await page.waitForTimeout(8000)
  const c = page.getByRole('button', { name: /^Confirm$/ }); console.log('confirm enabled?', await c.first().isEnabled()); await c.first().click(); await page.waitForTimeout(8000)
  t = await T(); console.log('AFTER CONFIRM PAGE:', t.slice(0, 700)); await sh('w10-4-after-confirm')
  console.log('AFTER CONFIRM (opps):', await opp()); await sh('w10-5-opps')
  await browser.close() })()
