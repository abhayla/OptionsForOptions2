// Lane W2 I-188: the lock of an exit of unknown outcome in a second tab, after a reload, and after a wall-clock jump of 200 s (strategy 1 = PATH-01, scenario mode)
const { chromium } = require('playwright')
const { shot, body, MAIN } = require('./common')
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
const URL = MAIN + '/positions/current-positions?tab=paper&strategy=1'
const LEG = 'NIFTY 9 Nov 22950 PE'
const state = async (page) => {
  const exit = page.getByTestId('exit-selected-1')
  const names = await exit.allInnerTexts()
  const dis = []; for (let i = 0; i < await exit.count(); i++) dis.push(await exit.nth(i).isDisabled())
  const t = await body(page)
  return { exit: names.join(','), disabled: dis.join(','), line: (t.match(/[^|]*(outcome[^|]*not known|not known yet|Orderbook|could not confirm)[^|]*/i) || ['<no unknown line>'])[0].trim().slice(0, 200) }
}
;(async () => {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  await ctx.addInitScript(() => { // wall clock offset kept per tab in sessionStorage; performance.now (monotonic) is NOT shifted
    const off = Number(sessionStorage.getItem('w2off') || 0); if (!off) return
    const RealDate = Date; const now = () => RealDate.now() + off
    class D extends RealDate { constructor(...a) { if (a.length) super(...a); else super(now()) } static now() { return now() } }
    globalThis.Date = D
  })
  const A = await ctx.newPage(), B = await ctx.newPage()
  let posts = 0
  for (const p of [A, B]) {
    p.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/\d+\/orders$/.test(r.url())) { posts++; console.log(ts(), 'POST key', JSON.parse(r.postData() || '{}').client_request_id) } })
    await p.route(/\/paper\/strategies\/\d+\/orders$/, (route) => route.request().method() === 'POST' ? route.abort('connectionreset') : route.continue())
  }
  await A.goto(URL); await B.goto(URL); await A.waitForTimeout(9000)   // tabs of one browser profile
  console.log(ts(), 'tab B before:', JSON.stringify(await state(B)))
  await A.getByRole('checkbox', { name: 'Select ' + LEG }).first().check()
  await A.getByTestId('exit-selected-1').click(); await A.waitForTimeout(2500)
  await A.getByRole('button', { name: 'Confirm' }).last().click(); await A.waitForTimeout(6000)
  console.log(ts(), 'tab A after cut:', JSON.stringify(await state(A)), '| POSTs', posts)
  await shot(A, 'i188-1-tabA-cut')
  const pressB = async (tag, shotName) => {
    const p0 = posts
    await B.getByRole('checkbox', { name: 'Select ' + LEG }).first().check({ timeout: 4000 }).catch(() => {})
    await B.getByTestId('exit-selected-1').click({ timeout: 3000 }).catch(() => console.log(tag, 'Exit not clickable'))
    await B.waitForTimeout(2000); await B.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 2000 }).catch(() => console.log(tag, 'Confirm not clickable/absent')); await B.waitForTimeout(3500)
    const dlg = (await B.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' ').slice(-200)
    console.log(ts(), tag, 'POSTs sent by the press:', posts - p0, '| dialog tail:', dlg)
    await shot(B, shotName)
    await B.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 1500 }).catch(() => {}); await B.waitForTimeout(500)
    await B.getByRole('checkbox', { name: 'Select ' + LEG }).first().uncheck({ timeout: 2000 }).catch(() => {})
  }
  await B.waitForTimeout(3000)
  await pressB('TAB B not reloaded, after A cut:', 'i188-2-tabB-live')
  await B.reload(); await B.waitForTimeout(9000)
  await pressB('TAB B after reload:', 'i188-3-tabB-reload')
  await B.evaluate(() => sessionStorage.setItem('w2off', '200000'))   // wall clock +200 s on this tab (the monotonic clock is untouched)
  await B.reload(); await B.waitForTimeout(9000)
  console.log(ts(), 'B Date.now minus real:', await B.evaluate(() => 0)  )
  await pressB('TAB B wall clock +200 s, reloaded:', 'i188-5-clockjump')
  await browser.close()
})()
