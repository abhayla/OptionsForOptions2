#!/usr/bin/env node
// Screen inventory extractor (Lane T). Reads the route table and the .vue templates and writes the machine-readable
// companion docs/design/next-batch-2026-11-26/screen-inventory.json. No dependencies; templates are scanned with a small
// quote-aware tag tokenizer, not a full Vue parser.
//
// Usage (from anywhere):  node frontend/e2e/support/inventory-extract.mjs [--out <file.json>] [--check]
//   --check  exits 1 when the committed JSON differs from what the code now produces.
//
// EXTRACTION RULE (kept in step with the "How this was built" section of screen-inventory.md)
// 1. Routes: every entry of `routes` in frontend/src/router/routes.js, imported as a module (so nav.js is the single list
//    of sections / items). Redirect-only entries are listed with component "(redirect)". A page component mounted at
//    several paths lists its controls once, under its first path; the other paths carry "sameAs".
// 2. Components: for each routed page .vue, every `.vue` it imports (static `import X from '...vue'` or `import('...vue')`,
//    '@/' = frontend/src) whose tag is used in its template (or any import when the template has `<component :is>`),
//    followed recursively. Layout (AppLayout.vue, reached from App.vue) is the pseudo route "(app shell)". A component
//    reached from two or more different pages (or from the shell and a page) is listed once, under the pseudo route
//    "(shared components)". A component reached from exactly one page is listed under that page. A .vue file that no route
//    and no shell reaches is listed under the pseudo route "(unrouted components)" so it cannot hide a control.
// 3. Controls (one row per template element or script handler):
//    button     <button>, role="button"
//    link       <a>, <router-link>, <RouterLink>, role="link"|"menuitem", <component :is> naming RouterLink or 'a' (button for 'button')
//    tab        role="tab"|"switch"|"checkbox"|"radio"|"option"|"combobox"|"textbox"|"slider" (any element)
//    field      <input> (type != hidden), <select>, <textarea>
//    disclosure <summary>
//    form       <form> that has @submit
//    dialog     role="dialog"|"alertdialog", <dialog>, and a <Modal> or <Drawer> usage
//    key        any @keydown / @keyup / @keypress (with or without modifier) on any element, and every
//               `addEventListener('keydown'|'keyup'|'keypress'` in a <script> block
//    click      any other element or component carrying @click / @dblclick / v-on:click (div, span, li, tr, td, Chip, ...)
//    An element that is already a button/link/tab/field/dialog and also carries @keydown gets ONE row (kind of its tag);
//    the key handler is noted in `keys` on that row. A `key` row is made only for elements that are none of the above.
// 4. Label = visible text of the element (nested text joined, `{{ expr }}` kept as `{{expr}}`), else aria-label /
//    :aria-label, else title, else placeholder, else name, else for a dialog its `title` prop. testid = data-testid
//    (static) or `:data-testid` expression in backticks.
// 5. source = repo-relative path : line of the opening tag.
// 6. IDs are <PREFIX>-<nn> in document order within a route (files in import order); the prefix is chosen per route in
//    PREFIXES below, so a new route must be added there (the script exits 1 on an unknown component).

import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const FRONTEND = resolve(HERE, '..', '..')
const REPO = resolve(FRONTEND, '..')
const SRC = join(FRONTEND, 'src')
const DEFAULT_OUT = join(REPO, 'docs', 'design', 'next-batch-2026-11-26', 'screen-inventory.json')

// Page component file name -> ID prefix. Pseudo routes: SHELL, SHARED.
export const PREFIXES = {
  'HomeOverviewPage.vue': 'HOME',
  'LandingPage.vue': 'LAND',
  'MyStrategiesPage.vue': 'MYSTR',
  'CreateStrategyPage.vue': 'CREATE',
  'StrategyBuilderPage.vue': 'BUILD',
  'LiveStrategiesPage.vue': 'LIVE',
  'AdjustmentsPage.vue': 'ADJ',
  'PositionsPage.vue': 'POS',
  'AdjustmentOpportunitiesPage.vue': 'ADJOPP',
  'OptionChainPage.vue': 'CHAIN',
  'IndexViewPage.vue': 'INDEX',
  'MarketContextPage.vue': 'CTX',
  'AlertsPage.vue': 'ALERT',
  'LearnPage.vue': 'LEARN',
  'BillingShellPage.vue': 'BILL',
  'BrokerSettingsPage.vue': 'BROKER',
  'SettingsPage.vue': 'SET',
  'ExecuteStrategyPage.vue': 'EXEC',
  'ExecutionReturnedPage.vue': 'RET',
  'BrokerConnectedPage.vue': 'BCONN',
  'BrokerRefusedPage.vue': 'BREF',
  'HealthPage.vue': 'HEALTH',
  'NotFoundPage.vue': 'NF',
  'PlaceholderPage.vue': 'PLACE',
}
const SHELL = '(app shell)'
const SHARED = '(shared components)'

// ---------------------------------------------------------------- template scan
const NATIVE_KIND = { button: 'button', a: 'link', 'router-link': 'link', routerlink: 'link', input: 'field', select: 'field', textarea: 'field', summary: 'disclosure', dialog: 'dialog' }
const ROLE_KIND = { button: 'button', link: 'link', menuitem: 'link', tab: 'tab', switch: 'tab', checkbox: 'tab', radio: 'tab', option: 'tab', combobox: 'tab', textbox: 'tab', slider: 'tab', dialog: 'dialog', alertdialog: 'dialog' }

function lineAt(text, offset) {
  let n = 1
  for (let i = 0; i < offset; i++) if (text.charCodeAt(i) === 10) n++
  return n
}

function tokenize(tpl) {
  const toks = []
  let i = 0
  while (i < tpl.length) {
    if (tpl.startsWith('<!--', i)) {
      const e = tpl.indexOf('-->', i)
      i = e < 0 ? tpl.length : e + 3
      continue
    }
    if (tpl[i] === '<' && /[A-Za-z]/.test(tpl[i + 1] || '')) {
      let j = i + 1
      while (j < tpl.length && /[\w.:-]/.test(tpl[j])) j++
      const name = tpl.slice(i + 1, j)
      const attrs = {}
      let selfClose = false
      while (j < tpl.length) {
        while (j < tpl.length && /\s/.test(tpl[j])) j++
        if (tpl[j] === '>') { j++; break }
        if (tpl[j] === '/' && tpl[j + 1] === '>') { selfClose = true; j += 2; break }
        let k = j
        while (k < tpl.length && !/[\s=>/]/.test(tpl[k])) k++
        if (k === j) { j++; continue }
        const an = tpl.slice(j, k)
        j = k
        let val = true
        if (tpl[j] === '=') {
          j++
          const q = tpl[j]
          if (q === '"' || q === "'") {
            const e = tpl.indexOf(q, j + 1)
            val = tpl.slice(j + 1, e < 0 ? tpl.length : e)
            j = e < 0 ? tpl.length : e + 1
          } else {
            let e = j
            while (e < tpl.length && !/[\s>]/.test(tpl[e])) e++
            val = tpl.slice(j, e)
            j = e
          }
        }
        attrs[an] = val
      }
      toks.push({ t: 'open', name, attrs, selfClose, off: i })
      i = j
      continue
    }
    if (tpl.startsWith('</', i)) {
      const e = tpl.indexOf('>', i)
      toks.push({ t: 'close', name: tpl.slice(i + 2, e).trim(), off: i })
      i = e < 0 ? tpl.length : e + 1
      continue
    }
    let j = i
    while (j < tpl.length && !(tpl[j] === '<' && (/[A-Za-z]/.test(tpl[j + 1] || '') || tpl[j + 1] === '/' || tpl.startsWith('<!--', j)))) {
      // a `<` inside a mustache is not a tag
      if (tpl.startsWith('{{', j)) {
        const e = tpl.indexOf('}}', j)
        j = e < 0 ? tpl.length : e + 2
        continue
      }
      j++
    }
    if (j === i) j++
    toks.push({ t: 'text', text: tpl.slice(i, j), off: i })
    i = j
  }
  return toks
}

const VOID = new Set(['input', 'br', 'hr', 'img', 'meta', 'link', 'source'])

function innerText(toks, idx) {
  const open = toks[idx]
  if (open.selfClose || VOID.has(open.name.toLowerCase())) return ''
  let depth = 1
  let out = ''
  for (let k = idx + 1; k < toks.length && depth > 0; k++) {
    const t = toks[k]
    if (t.t === 'open' && !t.selfClose && !VOID.has(t.name.toLowerCase())) depth++
    else if (t.t === 'close') depth--
    else if (t.t === 'text') out += t.text
    if (depth > 0 && t.t === 'open') {
      const al = t.attrs['aria-label'] || t.attrs[':aria-label']
      if (al && /^(Icon|svg)$/i.test(t.name)) out += ''
    }
  }
  return out.replace(/\{\{\s*([\s\S]*?)\s*\}\}/g, (_, e) => `{{${e.replace(/\s+/g, ' ')}}}`).replace(/\s+/g, ' ').trim()
}

const clean = (s) => (typeof s === 'string' ? s.replace(/\s+/g, ' ').trim() : '')

function templateOf(src) {
  const m = /^<template[^>]*>/m.exec(src)
  if (!m) return null
  const start = m.index + m[0].length
  const end = src.lastIndexOf('\n</template>')
  return { text: src.slice(start, end < 0 ? src.length : end), offset: start }
}

export function scanFile(file) {
  const src = readFileSync(file, 'utf8')
  const rel = relative(REPO, file).replace(/\\/g, '/')
  const controls = []
  const tpl = templateOf(src)
  if (tpl) {
    const toks = tokenize(tpl.text)
    toks.forEach((tk, idx) => {
      if (tk.t !== 'open') return
      const name = tk.name.toLowerCase()
      const a = tk.attrs
      const role = typeof a.role === 'string' ? a.role : null
      let kind = NATIVE_KIND[name] || (role && ROLE_KIND[role]) || null
      if (name === 'input' && a.type === 'hidden') return
      if (name === 'form') kind = a['@submit'] !== undefined || a['@submit.prevent'] !== undefined ? 'form' : null
      if (tk.name === 'Modal' || tk.name === 'Drawer') kind = 'dialog'
      const keyAttrs = Object.keys(a).filter((k) => /^(@|v-on:)(keydown|keyup|keypress)/.test(k))
      const clickAttrs = Object.keys(a).filter((k) => /^(@|v-on:)(click|dblclick)/.test(k))
      if (!kind && name === 'component' && typeof a[':is'] === 'string') {
        // <component :is="cond ? RouterLink : 'span'">: a link when the expression names RouterLink, a button when it names 'button'
        if (/router-?link/i.test(a[':is'])) kind = 'link'
        else if (/['"]button['"]/.test(a[':is'])) kind = 'button'
        else if (/['"]a['"]/.test(a[':is'])) kind = 'link'
        if (kind && typeof a['v-bind'] === 'string') {
          const m = /'data-testid':\s*'([^']+)'/.exec(a['v-bind'])
          if (m) a['data-testid'] = m[1]
          const to = /\bto:\s*([\w.]+)/.exec(a['v-bind'])
          if (to) a.to = to[1]
        }
      }
      if (!kind && keyAttrs.length) kind = 'key'
      if (!kind && clickAttrs.length) kind = 'click'
      if (!kind) return
      const text = innerText(toks, idx)
      let enclosing = ''
      if (!(text || a['aria-label'] || a[':aria-label'] || a.title || a[':title'] || a.placeholder || a[':placeholder'] || a.name) && (kind === 'field' || kind === 'button' || kind === 'tab')) {
        // nearest unclosed <label> before this element names it
        let open = 0
        for (let k = idx - 1; k >= 0; k--) {
          const p = toks[k]
          if (p.t === 'close' && p.name.toLowerCase() === 'label') open--
          else if (p.t === 'open' && p.name.toLowerCase() === 'label' && !p.selfClose) {
            if (open === 0) { enclosing = innerText(toks, k); break }
            open++
          }
        }
      }
      const label = text || clean(a['aria-label']) || clean(a[':aria-label']) || clean(a.title) || clean(a[':title']) ||
        clean(a.placeholder) || clean(a[':placeholder']) || clean(a.name) || clean(a[':title']) ||
        '' || (enclosing.length > 80 ? enclosing.slice(0, 80) + '...' : enclosing)
      const model = Object.keys(a).filter((k) => k.startsWith('v-model')).map((k) => `${k}=${clean(a[k])}`)[0] || ''
      const labelSrc = text ? 'text' : (a['aria-label'] || a[':aria-label']) ? 'aria-label' : label ? 'attr' : 'none'
      const aria = clean(a['aria-label']) || clean(a[':aria-label'])
      const testid = a['data-testid'] ? clean(a['data-testid']) : a[':data-testid'] ? '`' + clean(a[':data-testid']) + '`' : ''
      const row = {
        kind,
        tag: tk.name,
        label: label || (model ? `(unlabelled ${a.type || tk.name}: ${model})` : '(no label)'),
        labelFrom: labelSrc,
        ariaLabel: aria,
        testid,
        source: `${rel}:${lineAt(src, tpl.offset + tk.off)}`,
      }
      const handlers = [...keyAttrs, ...clickAttrs].map((k) => k.replace(/^(@|v-on:)/, ''))
      if (handlers.length) row.handlers = handlers
      if (a.type && typeof a.type === 'string') row.type = a.type
      if (kind === 'link') row.to = clean(a.to) || clean(a[':to']) || clean(a.href) || clean(a[':href'])
      controls.push(row)
    })
  }
  // script-level key listeners
  const re = /addEventListener\(\s*['"](keydown|keyup|keypress)['"]/g
  let m
  while ((m = re.exec(src))) {
    controls.push({ kind: 'key', tag: 'script', label: `${m[1]} listener (script)`, labelFrom: 'none', ariaLabel: '', testid: '', source: `${rel}:${lineAt(src, m.index)}`, handlers: [m[1]] })
  }
  controls.sort((x, y) => Number(x.source.split(':')[1]) - Number(y.source.split(':')[1]))
  return { src, tpl, controls }
}

// ---------------------------------------------------------------- component graph
const importRe = /import\s+(\w+)\s+from\s+['"]([^'"]+\.vue)['"]|import\(\s*['"]([^'"]+\.vue)['"]\s*\)/g
function resolveVue(from, spec) {
  if (spec.startsWith('@/')) return join(SRC, spec.slice(2))
  return resolve(dirname(from), spec)
}
export function childrenOf(file) {
  const { src, tpl } = scanFile(file)
  const out = []
  const tplText = tpl ? tpl.text : ''
  const dynamic = /<component\s[^>]*:is=/.test(tplText)
  let m
  importRe.lastIndex = 0
  while ((m = importRe.exec(src))) {
    const spec = m[2] || m[3]
    const p = resolveVue(file, spec)
    if (!existsSync(p)) continue
    const local = m[1]
    if (local) {
      const kebab = local.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
      const used = new RegExp(`<(${local}|${kebab})[\\s/>]`).test(tplText) || new RegExp(`\\b${local}\\b`).test(tplText)
      if (!used && !dynamic) continue
    }
    if (!out.includes(p)) out.push(p)
  }
  return out
}

export function reach(root) {
  const seen = []
  const walk = (f) => {
    if (seen.includes(f)) return
    seen.push(f)
    for (const c of childrenOf(f)) walk(c)
  }
  walk(root)
  return seen
}

// ---------------------------------------------------------------- build

// routes.js imports lib/orderPath.js (axios, '@/' aliases) which plain Node cannot load, so the route table is evaluated
// from a rewritten copy: the guard import becomes a stub and nav.js is imported by absolute path. Lazy `() => import(...)`
// factories are never called; their source text names the page file.
async function loadRoutes() {
  const { mkdtempSync } = await import('node:fs')
  const { tmpdir } = await import('node:os')
  let txt = readFileSync(join(SRC, 'router', 'routes.js'), 'utf8')
  txt = txt.replace(/import \{ requireOrderPath \} from '[^']+'/, 'const requireOrderPath = () => {}')
  txt = txt.replace("from './nav.js'", `from '${pathToFileURL(join(SRC, 'router', 'nav.js')).href}'`)
  const dir = mkdtempSync(join(tmpdir(), 'inv-routes-'))
  const f = join(dir, 'routes.mjs')
  writeFileSync(f, txt)
  return (await import(pathToFileURL(f).href)).routes
}
// routes.js cannot be imported in plain Node (it dynamic-imports .vue files lazily, which is fine until called, but
// `String(factory)` gives `() => import('../pages/X.vue')`, so the file name is readable). The module itself imports only
// nav.js and lib/orderPath.js, so importing it works.
// Pure builder: returns the inventory object (no file written, no process exit). The guard test
// frontend/tests/screen-inventory-guard.test.js calls it; main() below is the CLI around it.
export async function buildInventory() {
  const routes = await loadRoutes()
  const routeList = routes.map((r) => {
    let component = '(redirect)'
    if (r.component) {
      const mm = /pages\/(\w+\.vue)/.exec(String(r.component))
      component = mm ? mm[1] : '(unresolved)'
    }
    return { path: r.path, name: r.name || '', component, redirect: r.redirect ? (typeof r.redirect === 'string' ? r.redirect : '(function)') : '' }
  })
  if (routeList.some((r) => r.component === '(unresolved)')) throw new Error('a route component could not be resolved: ' + JSON.stringify(routeList.filter((r) => r.component === '(unresolved)')))

  // pages and their reach
  const pageComps = [...new Set(routeList.map((r) => r.component).filter((c) => c !== '(redirect)'))]
  const reachOf = {}
  for (const c of pageComps) {
    if (!PREFIXES[c]) throw new Error(`no ID prefix for page ${c}: add it to PREFIXES`)
    reachOf[c] = reach(join(SRC, 'pages', c))
  }
  const shellReach = reach(join(SRC, 'App.vue'))
  const pageSet = new Set(pageComps.map((c) => join(SRC, 'pages', c)))
  // owner of every file
  const owner = new Map()
  const allFiles = new Set([...shellReach, ...Object.values(reachOf).flat()])
  for (const f of allFiles) {
    const owners = new Set()
    if (shellReach.includes(f)) owners.add(SHELL)
    for (const c of pageComps) if (reachOf[c].includes(f)) owners.add(c)
    // a page that is the page itself
    owner.set(f, owners)
  }
  const ownerOf = (f) => {
    const o = owners(f)
    return o
  }
  function owners(f) { return owner.get(f) }
  const final = {}
  for (const f of allFiles) {
    const o = [...owners(f)]
    let key
    if (pageSet.has(f)) key = relative(join(SRC, 'pages'), f)
    else if (o.length === 1) key = o[0]
    else if (o.length === 2 && o.includes(SHELL) && false) key = SHELL
    else key = o.includes(SHELL) && o.length >= 1 && f.includes(join('components', 'layout')) ? SHELL : SHARED
    final[f] = key
  }
  // App.vue and AppLayout belong to the shell
  for (const f of shellReach) if (f === join(SRC, 'App.vue') || f === join(SRC, 'components', 'layout', 'AppLayout.vue')) final[f] = SHELL

  // controls per bucket in discovery order: shell files, then pages in route order, then shared
  const bucket = {}
  const add = (k, f) => { (bucket[k] ||= []).push(f) }
  const order = []
  for (const f of shellReach) order.push(f)
  for (const c of pageComps) for (const f of reachOf[c]) if (!order.includes(f)) order.push(f)
  for (const f of order) add(final[f], f)

  const controlsOf = {}
  const unlabeled = []
  for (const [k, files] of Object.entries(bucket)) {
    const prefix = k === SHELL ? 'SHELL' : k === SHARED ? 'SHARED' : PREFIXES[k]
    let n = 0
    controlsOf[k] = []
    for (const f of files) {
      for (const c of scanFile(f).controls) {
        n++
        const id = `${prefix}-${String(n).padStart(2, '0')}`
        controlsOf[k].push({ id, ...c, component: relative(SRC, f).replace(/\\/g, '/') })
      }
    }
  }

  // routes[]: shell, shared, then the route table
  const result = { generatedBy: 'frontend/e2e/support/inventory-extract.mjs', routes: [] }
  const strip = (c) => c
  result.routes.push({ path: SHELL, component: 'App.vue > AppLayout.vue', controls: (controlsOf[SHELL] || []).map(strip) })
  result.routes.push({ path: SHARED, component: 'components reached from two or more pages', controls: (controlsOf[SHARED] || []).map(strip) })
  const firstPath = {}
  for (const r of routeList) {
    if (r.component === '(redirect)') {
      result.routes.push({ path: r.path, name: r.name, component: '(redirect)', redirect: r.redirect, controls: [] })
      continue
    }
    if (firstPath[r.component]) {
      result.routes.push({ path: r.path, name: r.name, component: r.component, sameAs: firstPath[r.component], controls: [] })
    } else {
      firstPath[r.component] = r.path
      result.routes.push({ path: r.path, name: r.name, component: r.component, controls: (controlsOf[r.component] || []).map(strip) })
    }
  }
  // which shared / page components each page uses (for the reader)
  result.pageComponents = {}
  for (const c of pageComps) result.pageComponents[c] = reachOf[c].map((f) => relative(SRC, f).replace(/\\/g, '/'))
  result.shellComponents = shellReach.map((f) => relative(SRC, f).replace(/\\/g, '/'))
  // .vue files under src that no route and no shell reaches
  const { readdirSync, statSync } = await import('node:fs')
  const all = []
  const walk = (d) => { for (const e of readdirSync(d)) { const p = join(d, e); statSync(p).isDirectory() ? walk(p) : p.endsWith('.vue') && all.push(p) } }
  walk(SRC)
  result.unreachedVueFiles = all.filter((p) => !allFiles.has(p)).map((p) => relative(SRC, p).replace(/\\/g, '/'))
  // components no route and no shell reaches (kept under test only): still listed, so a button added there is not invisible
  const unrouted = []
  let un = 0
  for (const f of all.filter((p) => !allFiles.has(p))) {
    for (const c of scanFile(f).controls) unrouted.push({ id: `UNROUTED-${String(++un).padStart(2, '0')}`, ...c, component: relative(SRC, f).replace(/\\/g, '/') })
  }
  result.routes.splice(2, 0, { path: '(unrouted components)', component: 'components that no route or the shell renders', controls: unrouted })
  return result
}

export async function main(argv) {
  const out = argv.includes('--out') ? resolve(argv[argv.indexOf('--out') + 1]) : DEFAULT_OUT
  const result = await buildInventory()
  const text = JSON.stringify(result, null, 1) + '\n'
  if (argv.includes('--check')) {
    const cur = existsSync(out) ? readFileSync(out, 'utf8') : ''
    if (cur !== text) { console.error('screen-inventory.json is out of date: run node frontend/e2e/support/inventory-extract.mjs'); process.exit(1) }
    console.log('screen-inventory.json is current')
    return
  }
  writeFileSync(out, text)
  const total = result.routes.reduce((s, r) => s + r.controls.length, 0)
  console.log(`wrote ${relative(REPO, out)}: ${result.routes.length} route entries, ${total} controls, ${result.unreachedVueFiles.length} unreached .vue files`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main(process.argv.slice(2))
