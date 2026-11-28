const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const dlg = async () => (await page.getByRole('dialog').first().innerText({ timeout: 3000 }).catch(() => '<no dialog>')).replace(/\s+/g, ' ')
  // builder: per-leg Exit and Exit all
  await page.waitForTimeout(0)
  // positions: tick a leg, Exit (n)
  await page.goto(M + '/positions/current-positions'); await page.waitForTimeout(3000); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await page.waitForTimeout(6000)
  const cb = page.getByRole('checkbox').filter({ has: page.locator('xpath=self::*') }); const boxes = page.locator('input[type=checkbox]'); let ticked = ''
  for (let i = 0; i < await boxes.count(); i++) { const al = (await boxes.nth(i).getAttribute('aria-label')) || ''; if (/24000 PE|24100 PE|24300 CE|24400 CE/.test(al)) { await boxes.nth(i).check(); ticked = al; break } }
  console.log('POSITIONS ticked:', ticked); const all = page.getByRole('button', { name: /^Exit \(/ }); console.log('ALL Exit buttons:', await all.evaluateAll(x => x.map(e => e.innerText + (e.disabled ? ' [disabled]' : ' [enabled]')))); const pe = page.getByRole('button', { name: /^Exit \([1-9]/ }).first(); console.log('POSITIONS Exit button text/disabled:', await pe.innerText().catch(() => 'n/a'), await pe.isDisabled().catch(() => 'n/a'), 'title:', await pe.getAttribute('title').catch(() => null)); await sh('w25d2-positions-ticked')
  await pe.click({ timeout: 3000 }).catch(() => console.log('positions Exit click blocked')); await page.waitForTimeout(2500); console.log('POSITIONS Exit dialog:', (await dlg()).slice(0, 520)); await sh('w25d2-positions-dialog')
  await browser.close() })()
