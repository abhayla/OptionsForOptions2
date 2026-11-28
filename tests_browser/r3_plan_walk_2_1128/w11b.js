const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const APP = process.env.APP_ID || 'A-31'; const M = 'http://127.0.0.1:4174'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const dlg = async () => (await page.getByRole('dialog').first().innerText({ timeout: 3000 }).catch(() => '<no dialog>')).replace(/\s+/g, ' ')
  const opp = async () => { await page.goto(M + '/positions/adjustment-opportunities'); await page.waitForTimeout(4000); return (await page.getByTestId('opp-outcome').allInnerTexts()).join(' ; ') }
  const prep = async () => { await page.goto(M + '/strategy/builder?adjust=1&opp=3,4,5,6'); await page.waitForTimeout(9000)
    const g = await page.evaluate(async () => (await (await fetch('/api/adjustment-opportunities')).json()).groups.map(x => x.records.map(r => r.id)).flat().join(','))
    console.log('open record ids:', g)
    await page.getByLabel('Approach to prepare').first().selectOption(APP); await page.getByRole('button', { name: /prepare basket/i }).first().click(); await page.waitForTimeout(6000) }
  console.log('BEFORE:', await opp())
  await prep(); await page.waitForTimeout(2000)
  const c = page.getByRole('button', { name: /^Confirm$/ }).first(); console.log('Confirm enabled:', await c.isEnabled()); await c.click(); await page.waitForTimeout(8000); console.log('AFTER CONFIRM page:', (await T()).slice(60, 500)); await sh('w11-3-after-confirm')
  console.log('AFTER CONFIRM opps:', await opp()); await sh('w11-4-opps')
  await browser.close() })()
