// Lane W2 on FJ2 4201d3af2: points 1 (clock +/-200 s), 2 (second tab), 5 (expiry Review), 6 (unknown sentence). Scenario PATH-01 (strategy 1)
const { chromium } = require('playwright')
const { shot, body, MAIN } = require('./common')
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
const URL = MAIN + '/positions/current-positions?tab=paper'; const LEG = 'NIFTY 9 Nov 22950 PE'
;(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  await ctx.addInitScript(() => { const off = Number(sessionStorage.getItem('w2off') || 0); if (!off) return; const R = Date; const now = () => R.now() + off; class D extends R { constructor(...a) { if (a.length) super(...a); else super(now()) } static now() { return now() } } globalThis.Date = D })
  let mode = 'pass', posts = 0
  const mk = async () => { const p = await ctx.newPage(); p.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/1\/orders$/.test(r.url())) { posts++; console.log(ts(), 'POST key', JSON.parse(r.postData() || '{}').client_request_id) } }); await p.route(/\/paper\/strategies\/1\/orders$/, async (route) => { if (route.request().method() !== 'POST' || mode === 'pass') return route.continue(); if (mode === 'before') return route.abort('connectionreset'); await route.fetch().catch(() => {}); return route.abort('connectionreset') }); return p }
  const A = await mk()
  const press = async (p, leg, tag) => { const p0 = posts; await p.getByRole('checkbox', { name: 'Select ' + leg }).first().check({ timeout: 6000 }).catch(() => {}); await p.getByTestId('exit-selected-1').click({ timeout: 3000 }).catch(() => {}); await p.waitForTimeout(2000)
    const conf = p.getByRole('button', { name: 'Confirm' }).last(); const en = await conf.isEnabled().catch(() => false); if (en) { await conf.click().catch(() => {}); await p.waitForTimeout(3500) }
    const dlg = (await p.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' ').slice(-190); console.log(ts(), tag, '| Confirm enabled before:', en, '| POSTs sent:', posts - p0, '| dialog tail:', dlg)
    await p.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 1200 }).catch(() => {}); await p.waitForTimeout(400); await p.getByRole('checkbox', { name: 'Select ' + leg }).first().uncheck({ timeout: 1500 }).catch(() => {}) }
  await A.goto(MAIN + '/strategy/builder?strategy=1'); await A.waitForTimeout(8000)
  const P = await mk(); await P.goto(URL); await P.waitForTimeout(8000)
  const B = await mk(); await B.goto(URL); await B.waitForTimeout(8000)
  mode = 'pass'; await press(B, 'NIFTY 9 Nov 22950 PE', 'TAB B stored exit'); 
  const line = async (p) => ((await body(p)).match(/[^|]*(not known yet|could not confirm|Updating the numbers)[^|]*/g) || ['<no unknown/updating line>']).slice(0, 2).join(' ;; ').slice(0, 200)
  for (const s of [3, 12]) { await A.waitForTimeout(s === 3 ? 3000 : 9000); console.log(`${ts()} +${s}s tab A builder:`, await line(A), '| tab Positions:', await line(P)) }
  await shot(A, 'fj2-2-tabA-builder'); await shot(P, 'fj2-2-tabP-positions')
  await browser.close()
})()
