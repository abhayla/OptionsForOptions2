// Lane W3 item 1: second tab release. Tab A (context A) cuts its exit before the server (lock). Tab B (context B, another browser profile) stores the SAME exit (201). Time until tab A's lock sentence and "Updating the numbers" are gone.
const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4174'
const T = async (p) => (await p.locator('body').innerText()).replace(/\s+/g, ' ')
;(async () => { const browser = await chromium.launch()
  const A = await browser.newContext({ viewport: { width: 1366, height: 900 } }); await A.route('**/paper/strategies/1/orders', (r) => r.request().method() === 'POST' ? r.abort('failed') : r.continue())
  const pa = await A.newPage(); await pa.goto(M + '/strategy/builder?strategy=1'); await pa.waitForTimeout(8000)
  await pa.getByRole('button', { name: /^Exit$/ }).first().click(); await pa.waitForTimeout(1500); await pa.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }).click(); await pa.waitForTimeout(5000)
  let t = await T(pa); const t0 = Date.now(); console.log('tab A after cut: lock', /first exit's outcome is not known/.test(t), '| Updating the numbers', /Updating the numbers/.test(t)); await pa.screenshot({ path: `${OUT}/u2-1-tabA-locked.jpg`, type: 'jpeg', quality: 55 })
  const B = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const pb = await B.newPage()
  if (process.env.PB === 'positions') { await pb.goto(M + '/positions/current-positions'); await pb.waitForTimeout(9000); await pb.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await pb.waitForTimeout(3000)
    const cb = pb.getByRole('checkbox'); console.log('Positions checkboxes', await cb.count(), (await pb.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 160)); await cb.nth(1).check().catch((e) => console.log('check err', String(e).slice(0, 80))); await pb.waitForTimeout(1000)
    await pb.getByRole('button', { name: /^Exit \(1\)$/ }).first().click().catch((e) => console.log('Exit(1) err', String(e).slice(0, 80))); await pb.waitForTimeout(2000); await pb.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }).click(); await pb.waitForTimeout(5000) }
  else { await pb.goto(M + '/strategy/builder?strategy=1'); await pb.waitForTimeout(8000); const LB = Number(process.env.LEGB || 0)
  await pb.getByRole('button', { name: /^Exit$/ }).nth(LB).click(); await pb.waitForTimeout(1500); await pb.getByRole('dialog').getByRole('button', { name: /^Confirm$/ }).click(); await pb.waitForTimeout(5000) }
  console.log('tab B after its Confirm:', ((await T(pb)).match(/Exit placed on paper[^.]*\./) || ['<no placed sentence>'])[0]); const tB = Date.now()
  let lockGone = null, updGone = null
  for (let i = 0; i < 40; i++) { t = await T(pa); const lock = /first exit's outcome is not known/.test(t), upd = /Updating the numbers/.test(t); const s = Math.round((Date.now() - tB) / 1000)
    if (!lock && lockGone === null) lockGone = s; if (!upd && updGone === null) updGone = s; if (lockGone !== null && updGone !== null) break; await pa.waitForTimeout(5000) }
  console.log('tab A: lock sentence gone after (s since B stored):', lockGone, '| "Updating the numbers" gone after:', updGone); await pa.screenshot({ path: `${OUT}/u2-2-tabA-after.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
