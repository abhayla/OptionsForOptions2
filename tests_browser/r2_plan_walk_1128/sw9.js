const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  await page.goto(MAIN + '/strategies/live-strategies'); await page.waitForTimeout(7000)
  await page.getByRole('link', { name: 'Stops' }).nth(3).click().catch(async () => page.getByText('Stops', { exact: true }).nth(3).click()); await page.waitForTimeout(6000)
  const t=(await body(page)).split(' | '); t.forEach((l,i)=>{ if(/Index values|NIFTY (last|now)|Data: |exits are recorded|Conditional exit|as of 1/.test(l)) console.log(i, l.slice(0,200)) })
  await shot(page, 'sw9-stops')
  await browser.close()
})()
