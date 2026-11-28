const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  for (const leg of [2, 1]) {
    await page.goto(MAIN + '/strategy/builder?strategy=1'); await page.waitForTimeout(9000)
    const sel = page.getByLabel(`Change expiry of leg ${leg}`); const opts = await sel.locator('option').allInnerTexts()
    await sel.selectOption({ index: 1 }).catch(e => console.log('select err')); await page.waitForTimeout(3000)
    await page.getByRole('button', { name: /Review/ }).first().click({ timeout: 8000 }).catch(() => console.log('no Review')); await page.waitForTimeout(12000)
    const d = (await page.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' ')
    console.log(`leg ${leg} (options ${opts.join('/')}) REVIEW:`, d.slice(0, 700)); console.log('  stop sentence:', (d.match(/The stop on[^.]*\./) || ['<none>'])[0])
    await shot(page, `fj2-5-leg${leg}`)
  }
  await browser.close()
})()
