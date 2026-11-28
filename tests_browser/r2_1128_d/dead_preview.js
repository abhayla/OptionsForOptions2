// I-20 / I-86 on the second preview (/api -> closed port 9): builder empty state and My Strategies message, as first loaded.
const { launch, shot, text, DEAD } = require('./common')
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  for (const [k, u] of [['builder', '/strategy/builder'], ['builder-strategy1', '/strategy/builder?strategy=1'], ['my-strategies', '/strategies/my-strategies'], ['positions', '/positions/current-positions'], ['home', '/home/overview']]) {
    await page.goto(DEAD + u); await page.waitForTimeout(7000)
    console.log(`[${k}]`, (await text(page, '[data-testid=app-content]')).slice(0, 420)); await shot(page, `i20-dead-preview-${k}`)
  }
  await browser.close()
})()
