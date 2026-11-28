const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  for (const [name, url] of [['live', '/strategies/live-strategies'], ['positions', '/positions/current-positions?tab=paper&strategy=7'], ['builder', '/strategy/builder?strategy=7']]) {
    await page.goto(MAIN + url); await page.waitForTimeout(9000)
    const t = (await body(page)).split(' | ')
    console.log('=== ' + name)
    t.forEach((l, i) => { if (/Real position|Kite|TC Real|real/i.test(l) && !/not real|Real P&L|real money|real trade/i.test(l)) console.log('  ', i, t.slice(Math.max(0, i - 3), i + 4).join(' / ').slice(0, 330)) })
    console.log('  Exit buttons:', (await page.getByRole('button').allInnerTexts()).filter(x => /^Exit/.test(x)).join(' | '), '| Stops links:', await page.getByText('Stops', { exact: true }).count())
    await shot(page, `n1-${name}`)
  }
  await browser.close()
})()
