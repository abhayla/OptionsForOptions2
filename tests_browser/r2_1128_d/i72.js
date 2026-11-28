// I-72: click every top-menu item (dropdown entries of the six sections) and record where it lands.
const { launch, shot, text, MAIN } = require('./common')
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  const errs = []; page.on('pageerror', e => errs.push(e.message.slice(0, 120)))
  const secs = ['home', 'strategies', 'positions', 'market', 'alerts', 'learn']; const items = []
  for (const sec of secs) {
    await page.goto(MAIN + '/home/overview'); await page.waitForTimeout(700)
    await page.click(`[data-testid=nav-menu-toggle-${sec}]`); await page.waitForTimeout(300)
    items.push(...(await page.locator(`#nav-menu-${sec} a`).evaluateAll(e => e.map(x => ({ href: x.getAttribute('href'), t: x.textContent.trim().replace(/\s+/g, ' ') })))).map(l => ({ sec, ...l })))
  }
  console.log('dropdown items:', items.length)
  let i = 0
  for (const it of items) {
    await page.goto(MAIN + '/home/overview'); await page.waitForTimeout(500)
    await page.click(`[data-testid=nav-menu-toggle-${it.sec}]`); await page.waitForTimeout(300)
    await page.locator(`#nav-menu-${it.sec} a[href="${it.href}"]`).first().click()
    await page.waitForTimeout(1300)
    const path = new URL(page.url()).pathname; const h = await text(page, '[data-testid=page-title], h1, h2')
    const al = (await page.locator('[role=alert]').allInnerTexts()).join(' | ').replace(/\s+/g, ' ').slice(0, 120)
    console.log(`${it.sec} > ${it.t} -> ${path} ${path === it.href ? 'OK' : 'REDIRECT'} | heading: ${h.slice(0, 50)} | alert: ${al || '-'}`)
    if (/create-strategy|strategy-builder|adjustments$/.test(it.href)) await shot(page, `i72-${it.href.split('/').pop()}`)
  }
  console.log('pageerrors', errs); await browser.close()
})()
