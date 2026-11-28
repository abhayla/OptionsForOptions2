// Lane W3 item 2: W-30 monthly half (synthetic NIFTY future on 14 Dec makes 14 Dec monthly; #20 monthly IC, #21 weekly IC), stop % 45 read back in the sheet, plan-watch and the builder. ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const dlg = async () => (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' ')
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  for (const [sid, kind] of [[20, 'MONTHLY 14 Dec'], [21, 'WEEKLY 8 Dec']]) {
    await page.goto(`${M}/strategy/builder?strategy=${sid}`); await sleep(8000); await page.getByRole('button', { name: /Edit plan|Set plan/ }).first().click(); await sleep(2500)
    const inputs = page.getByRole('dialog').first().locator('input:not([type=time]):not([type=date])'); console.log(`#${sid} ${kind}: sheet values before:`, JSON.stringify(await inputs.evaluateAll(x => x.map(e => e.value))), '| expiry-type sentence:', (await dlg()).match(/[^.]*(expiry type|monthly|weekly)[^.]*\./i)?.[0] || '<none>')
    await inputs.nth(3).fill(''); await inputs.nth(2).fill('45'); await page.getByRole('button', { name: /Save plan/ }).click(); await sleep(5000)
    await page.getByRole('button', { name: /Edit plan/ }).first().click(); await sleep(2500); console.log(`#${sid} sheet reopened:`, JSON.stringify(await inputs.evaluateAll(x => x.map(e => e.value)))); await page.keyboard.press('Escape'); await sleep(500)
    const b = await T(); console.log(`   builder lines:`, JSON.stringify((b.match(/Stop[^|]*/g) || []).slice(0, 4)))
    const pw = await (await page.request.get(`${M}/api/plan-watch?strategy_ids=${sid}`)).json(); const lines = (pw.items?.[0]?.watch?.lines || []).filter(l => l.kind === 'stop'); console.log('   plan-watch stop lines:', JSON.stringify(lines.map(l => ({ label: l.label, fires_at: l.fires_at, state: l.state }))).slice(0, 500)) }
  await page.goto(M + '/positions/current-positions'); await sleep(9000); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await sleep(2000); const t = await T(); console.log('Positions Stop lines:', JSON.stringify((t.match(/Stop[^|]*/g) || []).slice(0, 8)).slice(0, 700)); await page.screenshot({ path: `${OUT}/c18-positions.jpg`, type: 'jpeg', quality: 55, fullPage: true })
  await browser.close() })()
