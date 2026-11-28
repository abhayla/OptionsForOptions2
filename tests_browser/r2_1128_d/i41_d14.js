// I-41 D-14 (ADR-320 (2)): an expiry-day trade shows max profit and profit left twice, labelled "If held to expiry" / "If exited now".
const { launch, shot, text, MAIN } = require('./common')
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  await page.goto(MAIN + '/strategy/builder?strategy=' + (process.env.TD_SID || '4')); await page.waitForTimeout(5500)
  console.log('tiles block:', (await text(page, '[data-testid=summary-block-outcome]')).slice(0, 900))
  console.log('book:', await text(page, '[data-testid=book-total-label]'), await text(page, '[data-testid=book-total]'), '|', await text(page, '[data-testid=book-charges-close]'))
  console.log('all text with "expiry"/"exited now":', JSON.stringify((await page.locator('text=/held to expiry|exited now/i').allInnerTexts()).map(s => s.replace(/\s+/g, ' ').slice(0, 120))))
  await shot(page, 'i41-d14-tiles-expiry-day'); await browser.close()
})()
