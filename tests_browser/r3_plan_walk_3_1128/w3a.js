// Lane W3 item 1, market-closed screens on ofo_tg (stack 4173): stored-close P&L with its date, plan block figures, Exit dialog Confirm
const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, f) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55, fullPage: !!f })
  const go = async (u, w = 9000) => { await page.goto(M + u); await page.waitForTimeout(w); return T() }
  const seg = (t, re, n = 8) => (t.match(re) || []).slice(0, n).map((s) => s.trim())
  const cnt = (t, s) => t.split(s).length - 1
  for (const [name, u] of [['home', '/'], ['positions', '/positions/current-positions'], ['live', '/strategies/live-strategies'], ['mystrat', '/strategies/my-strategies'], ['builder1', '/strategy/builder?strategy=1']]) {
    const t = await go(u); await sh('w3a-' + name, true)
    console.log(`== ${name}: banner`, JSON.stringify(seg(t, /Market closed\.[^|]*/g, 2)), '| "Prices are from" dates:', JSON.stringify(seg(t, /Prices are from[^|.]*[.]?/g, 2)))
    console.log('   P&L segments:', JSON.stringify(seg(t, /(Total P&L|Paper P&L|P&L)[^|]*\|?[^|]*/g, 8)))
    console.log('   paused sentence count:', cnt(t, 'Paper P&L paused'), '| "Includes"/"left out":', JSON.stringify(seg(t, /(Includes \d+ closed[^|]*|\d+ strateg[^|]*left out[^|]*)/g, 3)), '| "no price" count:', cnt(t, 'no price'))
  }
  // builder Plan block
  let t = await go('/strategy/builder?strategy=1'); console.log('== builder Plan block:', JSON.stringify(seg(t, /Plan \|[^]{0,900}?Time exit[^|]*/g, 1)).slice(0, 1200))
  console.log('   Target/Stop lines:', JSON.stringify(seg(t, /(Target|Stop)[^|]*\|?[^|]*/g, 12)).slice(0, 1500)); await sh('w3a-plan-block', true)
  // Exit dialog: Confirm
  const ex = page.getByRole('button', { name: /^Exit$/ }); console.log('== Exit buttons', await ex.count(), 'enabled', await ex.evaluateAll(x => x.map(e => !e.disabled)))
  await ex.first().click(); await page.waitForTimeout(2500)
  const dlg = (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' '); const cf = page.getByRole('dialog').getByRole('button', { name: /^Confirm$/ })
  console.log('   dialog:', dlg.slice(0, 500), '| Confirm count', await cf.count(), 'enabled', await cf.first().isEnabled().catch(() => 'n/a')); await sh('w3a-exit-dialog')
  await browser.close() })()
