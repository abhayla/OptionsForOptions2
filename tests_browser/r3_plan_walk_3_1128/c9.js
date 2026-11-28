// Lane W3 item 2: T1-21 API stopped for a few seconds on Positions > Paper (market closed half: grey Exit, reason line, tick kept, lists "-", comes back). ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const { execSync } = require('child_process'); const fs = require('fs'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/positions/current-positions'); await sleep(9000); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await sleep(2500)
  await page.getByRole('checkbox').nth(1).check(); await sleep(800)
  const exit = () => page.getByRole('button', { name: /^Exit \(\d\)$/ }); const st = async (tag) => console.log(tag, 'Exit buttons:', JSON.stringify(await exit().evaluateAll(x => x.map(e => `${e.innerText}:${e.disabled ? 'disabled' : 'enabled'}`))), '| reason lines:', JSON.stringify(((await T()).match(/[^|]*(not live|try again|could not|Try again)[^|]*/gi) || []).slice(0, 5)))
  await st('1 before stop'); await page.screenshot({ path: `${OUT}/c9-1-before.jpg`, type: 'jpeg', quality: 55 })
  const pid = Number(fs.readFileSync('/tmp/claude-0/api-tg.pid', 'utf8').trim()); process.kill(pid); await sleep(15000); await st('2 API down 15 s'); await page.screenshot({ path: `${OUT}/c9-2-api-down.jpg`, type: 'jpeg', quality: 55 })
  const t = await T(); console.log('   rows "no price"/dash count:', (t.match(/no price/g) || []).length, '| list lines:', JSON.stringify((t.match(/[^|]*(Could not load|could not get an answer|Retry)[^|]*/g) || []).slice(0, 4)))
  execSync('bash /home/user/OptionsForOptions2/tests_browser/r3_plan_walk_3_1128/api_start.sh tg'); const t0 = Date.now(); let gone = null
  for (let i = 0; i < 18; i++) { await sleep(10000); const tt = await T(); const bad = /could not get an answer|Could not read whether/i.test(tt); if (!bad && gone === null) { gone = Math.round((Date.now() - t0) / 1000); break } }
  console.log('error lines gone', gone === null ? 'NOT within 180 s' : `${gone} s after the API was started`); await st('3 API back'); await page.screenshot({ path: `${OUT}/c9-3-api-back.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
