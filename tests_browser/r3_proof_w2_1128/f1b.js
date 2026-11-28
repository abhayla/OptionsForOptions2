const { chromium } = require('playwright')
const { shot, body, MAIN } = require('./common')
const LEG = 'NIFTY 9 Nov 22950 PE'
;(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  await ctx.addInitScript(() => { const off = Number(sessionStorage.getItem('w2off') || 0); if (!off) return; const R = Date; const now = () => R.now() + off; class D extends R { constructor(...a) { if (a.length) super(...a); else super(now()) } static now() { return now() } } globalThis.Date = D })
  const page = await ctx.newPage(); let cut = true
  await page.route(/\/paper\/strategies\/1\/orders$/, (route) => route.request().method() === 'POST' && cut ? route.abort('connectionreset') : route.continue())
  const dlgText = async () => (await page.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' ')
  const open = async () => { await page.getByRole('checkbox', { name: 'Select ' + LEG }).first().check({ timeout: 6000 }).catch(() => {}); await page.getByTestId('exit-selected-1').click({ timeout: 3000 }).catch(() => {}); await page.waitForTimeout(2000) }
  await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(9000)
  await open(); await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(4500)
  let d = await dlgText(); console.log('(a) after the cut, dialog:', d.slice(d.indexOf('This is not a real trade')), '| contains "before trying again":', /before trying again/.test(d)); await shot(page, 'f1b-a-sentence')
  await page.getByRole('button', { name: 'Cancel' }).last().click().catch(() => {})
  for (const off of [200000, -200000]) {
    await page.evaluate((o) => sessionStorage.setItem('w2off', String(o)), off); await page.reload(); await page.waitForTimeout(8000); await open(); d = await dlgText()
    console.log(`(b) wall clock ${off / 1000} s, ~${off > 0 ? 20 : 35} s real after the cut: says "Two minutes have passed":`, /Two minutes have passed/.test(d), '| Confirm enabled:', await page.getByRole('button', { name: 'Confirm' }).last().isEnabled().catch(() => false), '| tail:', d.slice(-200))
    await shot(page, `f1b-b-${off > 0 ? 'fwd' : 'back'}`); await page.getByRole('button', { name: 'Cancel' }).last().click().catch(() => {})
  }
  await browser.close()
})()
