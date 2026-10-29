import { describe, it, expect, beforeAll } from 'vitest'
import { ESLint } from 'eslint'
import path from 'path'

const eslint = new ESLint({ cwd: path.resolve(__dirname, '..') })

async function messages(code, file) {
  const [res] = await eslint.lintText(code, { filePath: path.resolve(__dirname, '..', file) })
  return res.messages.filter((m) => m.ruleId && m.ruleId.includes('no-restricted-syntax'))
}

describe('lint rule banning literal vendor hosts (ADR-012)', () => {
  // GC-TPD F-2: the first lintText loads the config and plugins cold (25.8 s under the full run, past the 5 s test
  // limit); load them once here with a long hook timeout so each test times only its own lint call
  beforeAll(async () => {
    await eslint.lintText('export const warm = 1\n', { filePath: path.resolve(__dirname, '..', 'src/x.js') })
  }, 120000)

  it.each(['kite.trade', 'zerodha.com', 'nseindia.com', 'api.upstox.com', 'angelone', 'dhan.co'])(
    'flags %s in a string literal',
    async (host) => {
      expect((await messages(`export const u = 'https://${host}/x'\n`, 'src/x.js')).length).toBeGreaterThan(0)
    }
  )

  it('flags a vendor host in a template literal', async () => {
    expect((await messages('export const u = `https://kite.trade/${1}`\n', 'src/x.js')).length).toBeGreaterThan(0)
  })

  it('flags a vendor host in a Vue template attribute', async () => {
    const code = '<template><a href="https://kite.trade/">x</a></template>\n'
    expect((await messages(code, 'src/x.vue')).length).toBeGreaterThan(0)
  })

  it('flags the dhan API host', async () => {
    expect((await messages("export const u = 'https://api.dhan.co/v2'\n", 'src/x.js')).length).toBeGreaterThan(0)
  })

  it('flags the DhanHQ host', async () => {
    expect((await messages("export const u = 'https://dhanhq.co/docs'\n", 'src/x.js')).length).toBeGreaterThan(0)
  })

  it('passes an ordinary word that contains the letters dhan', async () => {
    expect(await messages("export const u = 'Sudhanshu and Madhana'\n", 'src/x.js')).toEqual([])
  })

  it('passes a same-origin call', async () => {
    expect(await messages("export const u = '/api/health'\n", 'src/x.js')).toEqual([])
  })
})
