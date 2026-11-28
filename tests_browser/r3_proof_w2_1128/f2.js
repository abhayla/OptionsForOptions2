// Lane W2 F2 (28c0e7be6): I-197 Plan block prints the stop / target figure; I-208 Stop % beside Stop Rs, Target % beside Target Rs
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  for (const sid of [1, 7]) {
    await page.goto(MAIN + '/strategy/builder?strategy=' + sid); await page.waitForTimeout(9000)
    const t = await body(page)
    console.log(`I-197 builder #${sid}:`, (t.match(/[^|]*(Stop|Target)[^|]*(Rs|%|set)[^|]*/g) || ['<none>']).slice(0, 8).join(' ;; ').slice(0, 800))
    await shot(page, `f2-i197-builder${sid}`)
  }
  await page.goto(MAIN + '/strategy/builder?strategy=1'); await page.waitForTimeout(8000)
  await page.getByRole('button', { name: 'Edit plan' }).click(); await page.waitForTimeout(2000)
  const dlg = page.getByRole('dialog').first()
  const ins = dlg.locator('input:not([type=time]):not([type=date])')
  console.log('sheet labels:', (await dlg.innerText()).replace(/\s+/g, ' ').slice(0, 500))
  const save = async (label) => {
    await dlg.getByRole('button', { name: 'Save plan' }).click(); await page.waitForTimeout(2500)
    if (!(await dlg.isVisible().catch(() => false))) { console.log(label, '-> sheet closed (SAVED, no message)'); await page.getByRole('button', { name: 'Edit plan' }).click(); await page.waitForTimeout(2000) }
    else console.log(label, '-> message:', ((await dlg.innerText()).match(/[^\n]*(differ|not valid|Stop and|Target and)[^\n]*/g) || ['<no message>']).join(' ;; '))
  }
  await ins.nth(0).fill('30'); await ins.nth(1).fill('900'); await save('Target 30 % + Target Rs 900')
  await ins.nth(0).fill('61.54'); await ins.nth(1).fill('3000.00'); await ins.nth(2).fill('9'); await ins.nth(3).fill('500'); await save('Stop 9 % + Stop Rs 500')
  await shot(page, 'f2-i208-sheet'); await browser.close()
})()
