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
  await prep(); let t = await T(); console.log('URL', page.url()); console.log('W-11 staged exits:', (t.match(/[0-9]+ pending changes?/) || ['<none>'])[0], '| "Exiting these legs (staged, not placed yet)":', /Exiting these legs \(staged, not placed yet\)/.test(t), '| "No legs yet":', /No legs yet/.test(t)); await sh('w11-1-staged')
  await page.getByRole('button', { name: /^Review/ }).first().click().catch(() => console.log('no Review button')); await page.waitForTimeout(6000); console.log('CONFIRM LIST:', (await dlg()).slice(0, 700)); await sh('w11-2-confirm-list')
  await page.getByRole('button', { name: /^Cancel$/ }).first().click().catch(() => {}); await page.waitForTimeout(2000); console.log('AFTER CANCEL builder staged:', (await T()).match(/[0-9]+ pending changes?/)?.[0]); console.log('AFTER CANCEL opps:', await opp())
  await prep(); await page.getByRole('button', { name: /^Review/ }).first().click(); await page.waitForTimeout(6000)
  const c = page.getByRole('button', { name: /^Confirm$/ }).first(); console.log('Confirm enabled:', await c.isEnabled()); await c.click(); await page.waitForTimeout(8000); console.log('AFTER CONFIRM page:', (await T()).slice(60, 500)); await sh('w11-3-after-confirm')
  console.log('AFTER CONFIRM opps:', await opp()); await sh('w11-4-opps')
  await browser.close() })()
