const { chromium } = require('playwright'); const { execSync } = require('child_process'); const fs = require('fs'); const OUT = process.env.OUT || '/tmp/claude-0/sp'
const MAIN = 'http://127.0.0.1:4173'; const ST = '/home/user/OptionsForOptions2/tests_browser/r3_plan_walk_2_1128'
;(async () => { const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const page = await ctx.newPage()
  const T = async (p = page) => (await p.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, p = page) => p.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const box = (t) => { const i = t.indexOf('Plan watch'); return t.slice(i, i + 700) }
  await page.goto(MAIN + '/strategy/builder?strategy=1'); await page.waitForTimeout(12000); let t = await T(); console.log('W-03 API up, box:', box(t).slice(0, 350))
  const pid = fs.readFileSync('/tmp/claude-0/api-tg.pid', 'utf8').trim(); process.kill(Number(pid)); const t0 = Date.now(); console.log('API stopped at', new Date().toTimeString().slice(0, 8))
  await page.waitForTimeout(8000)
  // W-25 D: press a leg Exit with the API down (about 8 s after stop)
  await page.getByRole('button', { name: /^Exit$/ }).first().click({ timeout: 5000 }).catch(() => console.log('Exit click blocked/disabled')); await page.waitForTimeout(3000); const d = (await page.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' '); console.log('W-25 D dialog (API down ~11 s):', d.slice(0, 520)); await sh('w25d-exit-api-down')
  const conf = page.getByRole('button', { name: /^Confirm$/ }); console.log('Confirm present/enabled:', await conf.count(), await conf.first().isEnabled().catch(() => 'n/a'))
  await page.keyboard.press('Escape'); await page.getByRole('button', { name: /^Cancel$/ }).first().click({ timeout: 1500 }).catch(() => {})
  // T3-10 other pages while API down
  const p2 = await ctx.newPage()
  for (const [n, u] of [['my-strategies', '/strategies/my-strategies'], ['live', '/strategies/live-strategies'], ['positions', '/positions/current-positions'], ['alerts', '/alerts/active'], ['history', '/alerts/history']]) { await p2.goto(MAIN + u); await p2.waitForTimeout(9000); const x = await T(p2); console.log('T3-10', n, '=>', x.slice(x.indexOf('You') + 5, x.indexOf('You') + 330)); await sh('t310-' + n, p2) }
  const wait = 70000 - (Date.now() - t0); await page.waitForTimeout(Math.max(0, wait)); t = await T(); console.log('W-03 step 4 at ~70 s down, builder box:', box(t).slice(0, 500)); console.log('"Could not refresh the rule check" shown:', /Could not refresh the rule check/.test(t)); await sh('w03-step4-api-down')
  execSync(`bash ${ST}/api_start.sh tg`, { env: { ...process.env } }); console.log('API restarted', new Date().toTimeString().slice(0, 8)); await page.waitForTimeout(25000); t = await T(); console.log('after restart box:', box(t).slice(0, 300)); await sh('w03-after-restart')
  await browser.close() })()
