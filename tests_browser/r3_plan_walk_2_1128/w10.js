const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const APP = process.env.APP_ID || 'A-28'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 768 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const opp = async () => { await page.goto('http://127.0.0.1:4174/positions/adjustment-opportunities'); await page.waitForTimeout(4000); const t = await T(); return t.slice(t.indexOf('Open:'), t.indexOf('Open:') + 140) + ' ## ' + t.slice(t.indexOf('Link |') ).replace(/\|\s*Spot within.*?\|\s*\d+ adjustment/, '') .slice(0, 0) + t.match(/Your rule was triggered \| [^|]*\|[^|]*\|/g) }
  console.log('OPP BEFORE:', await opp())
  await page.goto('http://127.0.0.1:4174/strategy/builder?adjust=2&opp=3,4,5,6'); await page.waitForTimeout(9000)
  await page.getByLabel('Approach to prepare').first().selectOption(APP); await page.getByRole('button', { name: /prepare basket/i }).first().click(); await page.waitForTimeout(6000)
  console.log('URL', page.url()); let t = await T(); console.log('AFTER PREPARE:', t.slice(0, 1500)); await sh('w10-1-prepared')
  const names = (await page.getByRole('button').allInnerTexts()).map(s => s.trim()).filter(Boolean); console.log('BUTTONS', names.join(' || ').slice(0, 700))
  await browser.close() })()
