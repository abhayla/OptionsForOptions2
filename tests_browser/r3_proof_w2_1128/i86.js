// Lane W2 I-86 / I-200 / I-201 (F3 head): API stopped, ten pages, a Retry on each
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  for (const [n, u] of [['home', '/home/overview'], ['positions', '/positions/current-positions'], ['live', '/strategies/live-strategies'], ['mystrat', '/strategies/my-strategies'], ['completed', '/strategies/completed-strategies'], ['builder', '/strategy/builder?strategy=1'], ['chain', '/market/option-chain'], ['alerts-active', '/alerts/active'], ['alerts-history', '/alerts/history'], ['adjustments', '/strategies/adjustments']]) {
    await page.goto(MAIN + u).catch(() => {}); await page.waitForTimeout(7000)
    const t = await body(page)
    console.log(n.padEnd(15), 'Retry buttons:', await page.getByRole('button', { name: /Retry|Try again/ }).count(), '| error words:', (t.match(/(could not|couldn't|not available|Something went wrong|failed|Unable)[^|]{0,70}/i) || ['-'])[0], '| raw:', /error_class|ECONN|500|502|Network Error/.test(t))
    await shot(page, 'i86-' + n)
  }
  await browser.close()
})()
