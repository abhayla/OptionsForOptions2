// Lane W2 I-57 (F3 head): after "Reset to playbook" the changed markers or the "Nothing differed" line
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  await page.goto(MAIN + '/strategy/builder?strategy=2'); await page.waitForTimeout(9000)
  const open = async () => { await page.getByRole('button', { name: 'Edit plan' }).click(); await page.waitForTimeout(2000); return page.getByRole('dialog').first() }
  let dlg = await open(); const ins = dlg.locator('input:not([type=time]):not([type=date])')
  await ins.nth(0).fill('40'); await dlg.getByRole('button', { name: 'Save plan' }).click(); await page.waitForTimeout(3000)
  dlg = await open()
  await dlg.getByRole('button', { name: 'Reset to playbook' }).click(); await page.waitForTimeout(1500)
  console.log('after first click:', (await page.locator('body').innerText()).replace(/\s+/g, ' ').match(/Reset the conditions\?[^]{0,200}/)?.[0])
  await page.getByRole('button', { name: 'Reset to playbook' }).last().click().catch(() => {}); await page.waitForTimeout(3000)
  const t = (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  console.log('RESULT line:', (t.match(/[^.]*(Nothing differed|changed|put back|differed)[^.]*\./g) || ['<none>']).slice(0, 4).join(' ;; ').slice(0, 500))
  await shot(page, 'i57-reset'); await browser.close()
})()
