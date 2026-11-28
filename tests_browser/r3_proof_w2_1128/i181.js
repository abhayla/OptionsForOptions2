// Lane W2 I-181: one request key per Confirm; the same key on a resend; a new key on a new Confirm (Positions > Paper, scenario PATH-10, strategy 2)
const { launch, shot, body, MAIN } = require('./common')
const posts = []
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
async function confirmExit(page, leg, tag) {
  await page.getByRole('checkbox', { name: 'Select ' + leg }).first().check({ timeout: 8000 })
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first().click(); await page.waitForTimeout(2500)
  const dlg = (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' ').slice(0, 300)
  console.log(ts(), tag, 'dialog:', dlg)
  await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(5000)
  console.log(ts(), tag, 'dialog after Confirm:', (await page.getByRole('dialog').first().innerText().catch(() => '<closed>')).replace(/\s+/g, ' ').slice(-330))
  if (!/outcome|could not confirm/i.test(await body(page))) await page.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(500)
}
;(async () => {
  const { browser, page } = await launch()
  let mode = 'pass'
  page.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/\d+\/orders$/.test(r.url())) { const j = JSON.parse(r.postData() || '{}'); posts.push({ t: ts(), key: j.client_request_id, n: (j.orders || []).length }); console.log(ts(), 'POST', r.url().split('/api')[1], 'key', j.client_request_id, 'rows', (j.orders || []).length) } })
  await page.route(/\/paper\/strategies\/\d+\/orders$/, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    if (mode === 'abort_before') return route.abort('connectionreset')           // the server never sees it
    if (mode === 'abort_after') { await route.fetch().catch(() => {}); return route.abort('connectionreset') } // the server stores, the reply is lost
    return route.continue()
  })
  await page.goto(MAIN + '/positions/current-positions?tab=paper&strategy=2'); await page.waitForTimeout(8000)
  // 1 normal Confirm -> K1
  await confirmExit(page, 'NIFTY 9 Nov 22600 PE', 'C1'); console.log(ts(), 'after C1:', (await body(page)).match(/Exit placed[^|]*/)?.[0])
  await shot(page, 'i181-1-confirm1')
  // 2 new Confirm on another leg -> K2
  await confirmExit(page, 'NIFTY 9 Nov 22800 PE', 'C2'); console.log(ts(), 'after C2:', (await body(page)).match(/Exit placed[^|]*/)?.[0])
  // 3 reply lost BEFORE the server (not stored) -> K3, then after the window the retry must carry K3 again
  mode = 'abort_before'
  await confirmExit(page, 'NIFTY 9 Nov 23400 CE', 'C3(cut, never reached server)')
  console.log(ts(), 'after cut:', (await body(page)).match(/[^|]*(outcome|not known|confirm)[^|]*/i)?.[0])
  await shot(page, 'i181-2-cut')
  mode = 'pass'
  // immediately: a second press inside the window must send nothing
  const before = posts.length
  await page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first().click({ timeout: 3000 }).catch(() => console.log('Exit not clickable inside the window'))
  await page.waitForTimeout(2000); await page.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 2000 }).catch(() => {}); await page.waitForTimeout(2000)
  console.log(ts(), 'POSTs sent inside the window by a 2nd press:', posts.length - before)
  await shot(page, 'i181-3-inside-window')
  // wait past the 130 s window (reload so the lock is read from storage; a read decides it)
  await page.waitForTimeout(135000)
  await page.reload(); await page.waitForTimeout(9000)
  console.log(ts(), 'after window+reload:', (await body(page)).match(/[^|]*(outcome|not stored|not known)[^|]*/i)?.[0] || '<no unknown line>')
  await shot(page, 'i181-4-after-window')
  const b4 = posts.length
  const cb = page.getByRole('checkbox', { name: 'Select NIFTY 9 Nov 23400 CE' }).first()
  if (!(await cb.isChecked().catch(() => false))) await cb.check().catch(() => {})
  await page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first().click({ timeout: 3000 }).catch(() => console.log('Exit not clickable after window'))
  await page.waitForTimeout(2500); await page.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 3000 }).catch(() => console.log('Confirm not clickable')); await page.waitForTimeout(6000)
  console.log(ts(), 'retry POSTs:', posts.length - b4, JSON.stringify(posts.slice(b4)))
  await shot(page, 'i181-5-retry')
  console.log('ALL POSTS', JSON.stringify(posts))
  await browser.close()
})()
