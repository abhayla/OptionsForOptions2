// I-71 Pick from Option Chain, I-72 every top-menu item, I-78 Rename + Esc.
const { launch, shot, text, MAIN } = require('./common')
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  await page.goto(MAIN + '/strategy/builder?strategy=1'); await page.waitForTimeout(4500)
  console.log('=== I-71'); await page.click('[data-testid=edit-leg], [data-testid=add-edit]').catch(e => console.log('open picker fail', e.message.slice(0, 100)))
  await page.waitForTimeout(1500)
  const link = page.getByRole('button', { name: 'Pick from Option Chain' }); console.log('link count', await link.count())
  console.log('picker tab before:', await text(page, '[data-testid=picker-view] [aria-selected=true], [data-testid=picker-tabs] [aria-selected=true]'))
  await shot(page, 'i71-01-picker-before')
  await link.first().click(); await page.waitForTimeout(1500)
  console.log('after click, view toggles:', await page.locator('[data-testid^=picker-view-]').evaluateAll(e => e.map(x => x.dataset.testid + ':' + (x.getAttribute('aria-pressed') ?? x.getAttribute('aria-selected') ?? x.className.includes('active')))))
  console.log('strikes panel:', (await text(page, '[data-testid=strikes-panel]')).slice(0, 300), '| tabs selected:', await page.locator('[data-testid=picker-tabs] [aria-selected=true]').allInnerTexts())
  await shot(page, 'i71-02-picker-after-click')
  await page.keyboard.press('Escape')
  console.log('=== I-72'); await page.goto(MAIN + '/'); await page.waitForTimeout(2000)
  const items = []
  for (const sec of ['home', 'strategies', 'positions', 'market', 'alerts', 'learn']) {
    await page.goto(MAIN + '/'); await page.waitForTimeout(600)
    await page.click(`[data-testid=nav-menu-toggle-${sec}]`).catch(() => {}); await page.waitForTimeout(400)
    const links = await page.locator(`[data-testid=primary-nav] a[href^="/${sec}/"]`).evaluateAll(e => e.map(x => ({ href: x.getAttribute('href'), t: x.textContent.trim() })))
    items.push(...links.map(l => ({ sec, ...l })))
  }
  const seen = new Set(); const uniq = items.filter(i => !seen.has(i.href) && seen.add(i.href))
  console.log('menu items found:', uniq.length)
  let n = 0
  for (const it of uniq) {
    await page.goto(MAIN + '/'); await page.waitForTimeout(500)
    await page.click(`[data-testid=nav-menu-toggle-${it.sec}]`).catch(() => {}); await page.waitForTimeout(300)
    await page.locator(`[data-testid=primary-nav] a[href="${it.href}"]`).first().click().catch(e => console.log('  click fail', it.href, e.message.slice(0, 60)))
    await page.waitForTimeout(1500)
    const h = await text(page, 'h1, [data-testid=page-title]'); const red = await page.locator('[role=alert]').count()
    console.log(`  ${it.sec} > ${it.t} -> ${new URL(page.url()).pathname} | title: ${h.slice(0, 60)} | alerts ${red}`)
    if (it.href.includes('create-strategy') || n++ < 0) await shot(page, 'i72-create-strategy')
  }
  await browser.close()
})()
