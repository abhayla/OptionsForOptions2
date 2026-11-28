// Lane W3 item 1 core: the unknown-outcome lock on the build (scenario PATH-10, API 8001 / vite 4174). MODE=lost (the post never reaches the server) or MODE=committed (server stores it, answer lost)
const { chromium } = require('playwright'); const { execSync } = require('child_process'); const fs = require('fs')
const M = 'http://127.0.0.1:4174'; const API = 'http://127.0.0.1:8001'; const MODE = process.env.MODE || 'lost'; const OUT = process.env.OUT || '/tmp/claude-0/sp'
const SHOT = (p, n) => p.screenshot({ path: `${OUT}/u1-${MODE}-${n}.jpg`, type: 'jpeg', quality: 55 })
const db = () => Number(execSync(`PGPASSWORD=postgres_ci_dummy_pw psql -h127.0.0.1 -U postgres ofo_dev -Atc "select count(*) from paper_orders"`).toString().trim())
const T = async (p) => (await p.locator('body').innerText()).replace(/\s+/g, ' ')
const find = (t) => (t.match(/The first exit's outcome[^.]*\./g) || ['<lock sentence absent>'])
;(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } })
  const posts = []; let lastBody = null
  await ctx.route('**/paper/strategies/1/orders', async (route) => {
    const req = route.request(); if (req.method() !== 'POST') return route.continue()
    posts.push(req.postData()); lastBody = req.postData()
    if (MODE === 'committed') { await route.fetch().catch(() => {}) }
    await route.abort('failed')
  })
  const page = await ctx.newPage(); const n0 = db(); console.log(`MODE=${MODE} orders in db before:`, n0)
  await page.goto(M + '/strategy/builder?strategy=1'); await page.waitForTimeout(8000)
  const ex = page.getByRole('button', { name: /^Exit$/ })
  await ex.first().click(); await page.waitForTimeout(1500)
  await page.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }).click(); await page.waitForTimeout(6000)
  const t1 = await T(page); console.log('after first Confirm: posts', posts.length, 'lock sentences:', JSON.stringify(find(t1)), 'db', db()); await SHOT(page, '1-after-first-confirm')
  const body1 = JSON.parse(posts[0] || '{}'); console.log('first body keys:', Object.keys(body1), 'client_request_id', body1.client_request_id)
  // second Exit (another leg) while the outcome is unknown
  const ex2 = page.getByRole('button', { name: /^Exit$/ }); console.log('exit buttons enabled:', await ex2.evaluateAll(x => x.map(e => !e.disabled)))
  await ex2.nth(1).click({ timeout: 4000 }).catch((e) => console.log('second Exit click:', String(e).split('\n')[0].slice(0, 100))); await page.waitForTimeout(2000)
  const d2 = await page.getByRole('dialog').first().innerText({ timeout: 2000 }).catch(() => '<no dialog>'); console.log('second dialog:', d2.replace(/\s+/g, ' ').slice(0, 400))
  const cf = page.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }); console.log('Confirm count', await cf.count(), 'enabled', await cf.first().isEnabled().catch(() => 'n/a')); await SHOT(page, '2-second-exit-dialog')
  if (await cf.count() && await cf.first().isEnabled().catch(() => false)) { await cf.first().click().catch(() => {}); await page.waitForTimeout(3000) }
  console.log('after second Confirm attempt: posts', posts.length, 'db', db())
  await page.keyboard.press('Escape').catch(() => {})
  // reload, then move the wall clock +10 min with the monotonic clock untouched
  await page.reload(); await page.waitForTimeout(7000); const t2 = await T(page); console.log('after reload lock sentences:', JSON.stringify(find(t2))); await SHOT(page, '3-after-reload')
  const lsBefore = await page.evaluate(() => ({ ls: localStorage.getItem('ofo.exitUnknown'), keys: localStorage.getItem('ofo.orderKeys'), mono: performance.now(), wall: Date.now() })); console.log('storage before clock move:', JSON.stringify(lsBefore).slice(0, 600))
  // (a) the SAME page instance: wall clock moved +600 s by an in-page override, monotonic untouched, then the re-read link
  await page.evaluate(() => { const off = 600000; const D = Date; const N = () => D.now() + off; window.Date = class extends D { constructor(...a) { if (a.length) super(...a); else super(N()) } static now() { return N() } } })
  await page.getByRole('link', { name: /Orderbook/ }).or(page.getByRole('button', { name: /Orderbook/ })).first().click({ timeout: 4000 }).catch((e) => console.log('Orderbook click:', String(e).split('\n')[0].slice(0, 90))); await page.waitForTimeout(5000)
  console.log('(a) same instance, wall +600 s, after Orderbook re-read: lock', JSON.stringify(find(await T(page))), 'exit enabled:', await page.getByRole('button', { name: /^Exit$/ }).evaluateAll(x => x.map(e => !e.disabled))); await SHOT(page, '3a-same-instance-clock-moved')
  // clock move: new page with Date offset +600 s, performance.now left alone
  const page2 = await ctx.newPage(); await page2.addInitScript((OFFSET) => { const off = Number(window.name === '' ? 0 : 0) + OFFSET; const D = Date; const N = () => D.now() + off; const P = class extends D { constructor(...a) { if (a.length) super(...a); else super(N()) } static now() { return N() } }; window.Date = P }, Number(process.env.OFFSET ?? 600000))
  await page2.goto(M + '/strategy/builder?strategy=1'); await page2.waitForTimeout(8000)
  const t3 = await T(page2); const wall2 = await page2.evaluate(() => Date.now()); console.log('clock +600 s tab (wall', new Date(wall2).toISOString(), ') lock sentences:', JSON.stringify(find(t3))); await SHOT(page2, '4-clock-moved-tab')
  const ex3 = page2.getByRole('button', { name: /^Exit$/ }); await ex3.first().click({ timeout: 4000 }).catch(() => {}); await page2.waitForTimeout(1500)
  const cf3 = page2.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }); console.log('second tab Confirm count', await cf3.count(), 'enabled', await cf3.first().isEnabled().catch(() => 'n/a'))
  if (await cf3.count() && await cf3.first().isEnabled().catch(() => false)) { await cf3.first().click().catch(() => {}); await page2.waitForTimeout(3000) }
  console.log('after second-tab Confirm attempt: posts', posts.length, 'db', db()); await SHOT(page2, '5-second-tab')
  fs.writeFileSync(`${OUT}/u1-${MODE}-lastbody.json`, lastBody || '')
  await browser.close() })()
