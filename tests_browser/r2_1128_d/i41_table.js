// I-41 step: the P&L Table total, with Add Booked P&L ON and OFF, compact and full view.
const { launch, shot, text, MAIN } = require('./common')
const base = process.env.TD_BASE || MAIN, sid = process.env.TD_SID || '1', tag = process.env.TD_TAG || 'adj02'
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  await page.goto(base + `/strategy/builder?strategy=${sid}`); await page.waitForTimeout(5000)
  await page.click('[data-testid=tab-pnl]'); await page.waitForTimeout(1200)
  const read = async (label) => {
    const t = (await text(page, '[data-testid=panel-pnl]')); console.log(`[${label}]`, t.slice(0, 1200))
    console.log(`[${label}] tiles: max-profit`, await text(page, '[data-testid=max-profit]'), '| max-loss', await text(page, '[data-testid=max-loss]'), '| BE', await text(page, '[data-testid=breakevens]'))
  }
  const sw = page.locator('[data-testid=add-booked-switch] input, input[type=checkbox]').filter({ hasText: '' })
  const booked = page.getByLabel('Add Booked P&L')
  console.log('booked checked at start:', await booked.isChecked())
  await read('compact booked=' + await booked.isChecked()); await page.locator('[data-testid=panel-pnl]').scrollIntoViewIfNeeded(); await page.mouse.wheel(0, 600); await page.waitForTimeout(400); await shot(page, `i41-${tag}-table-compact-on`)
  await booked.uncheck(); await page.waitForTimeout(900); await read('compact booked=false'); await shot(page, `i41-${tag}-table-compact-off`)
  await booked.check(); await page.getByLabel('Full table').check(); await page.waitForTimeout(900); await read('full booked=true'); await shot(page, `i41-${tag}-table-full-on`)
  await booked.uncheck(); await page.waitForTimeout(900); await read('full booked=false'); await shot(page, `i41-${tag}-table-full-off`)
  await browser.close()
})()
