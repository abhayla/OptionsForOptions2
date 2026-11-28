// Lane W3 item 3: I-86 API stopped, Retry buttons on the lists, no raw error text. ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const { execSync } = require('child_process'); const fs = require('fs'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const page = await ctx.newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  process.kill(Number(fs.readFileSync('/tmp/claude-0/api-tg.pid', 'utf8').trim())); await sleep(3000)
  for (const [n, u] of [['Home', '/'], ['Positions', '/positions/current-positions'], ['Live', '/strategies/live-strategies'], ['My Strategies', '/strategies/my-strategies'], ['Completed', '/strategies/completed-strategies'], ['Option Chain', '/market/option-chain'], ['Alerts Active', '/alerts/active'], ['Alerts History', '/alerts/history'], ['Adjustments', '/strategies/adjustments'], ['Builder #1', '/strategy/builder?strategy=1']]) {
    await page.goto(M + u); await sleep(14000); const t = await T(); const retry = await page.getByRole('button', { name: /Retry|Try again/ }).count()
    console.log(`${n}: Retry buttons ${retry} | raw markers ${JSON.stringify(t.match(/error_class|BROKER_AUTH|ECONN|\[object|undefined|NaN|at \w+\.\w+ \(/g) || [])} | sentence ${JSON.stringify((t.match(/[^|]*(Could not|could not|not get an answer)[^|]*/g) || ['<none>'])[0]).slice(0, 120)}`) }
  execSync('bash /home/user/OptionsForOptions2/tests_browser/r3_plan_walk_3_1128/api_start.sh tg'); await sleep(15000); await browser.close() })()
