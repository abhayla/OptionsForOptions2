// Lane TG: the nine after-close screens with the stored close and no broker session (round 1 defect D-1)
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
  const tag = process.argv[2] || 'c'
  const screens = [
    ['sw1-home', '/home/overview'],
    ['sw2-positions-real', '/positions/current-positions', 'Real'],
    ['sw3-positions-paper', '/positions/current-positions', 'Paper'],
    ['sw4-live', '/strategies/live-strategies'],
    ['sw5-my-strategies', '/strategies/my-strategies'],
    ['sw5b-completed', '/strategies/my-strategies', 'Completed'],
    ['sw6-builder', '/strategy/builder?strategy=1'],
    ['sw7-chain', '/market/option-chain'],
    ['sw8-alerts-active', '/alerts/active'],
    ['sw8-alerts-history', '/alerts/history'],
    ['sw8-alerts-records', '/alerts/records'],
  ]
  for (const [name, url, click] of screens) {
    await page.goto(MAIN + url); await page.waitForTimeout(8000)
    if (click) { await page.getByRole('button', { name: click, exact: true }).first().click().catch(() => page.locator(`text=${click}`).first().click().catch(() => {})); await page.waitForTimeout(2500) }
    const t = await body(page)
    console.log('=== ' + name + ' :: ' + t.replace(/^OF \| OptionsForOptions \| \/ \| /, '').replace(/Home \| Strategies \| Positions \| Market \| Alerts \| Learn \| You \| /, '').slice(0, +process.env.CAP || 900))
    await shot(page, `${tag}-${name}`)
  }
  console.log('CONSOLE ERRORS', errs.length, errs.slice(0, 4))
  await browser.close()
})()
