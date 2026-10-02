// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/eslint.config.js (ADR-047)
// Changed: dropped the prettier plugin rule; added a ban on literal vendor hosts in source (ADR-012: the browser never
// talks to a market-data vendor or broker host; only same-origin /api).
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier'
import globals from 'globals'

export const VENDOR_HOSTS = /kite\.trade|zerodha\.com|nseindia\.com|upstox|angelone|dhan\.co|api\.dhan/i
const message = 'Vendor/broker hosts are never named in the browser (ADR-012). Call same-origin /api only.'

export default [
  { ignores: ['node_modules/', 'dist/', 'coverage/', 'playwright-report/', 'test-results/'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  prettier,
  {
    files: ['src/**/*.{js,vue}', 'tests/**/*.js'],
    languageOptions: { globals: { ...globals.browser, ...globals.es2021, ...globals.node } },
    rules: {
      'no-console': 'off',
      'vue/multi-word-component-names': 'off',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    // Source only: the lint test itself has to name the hosts it proves are banned.
    files: ['src/**/*.{js,vue}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: `Literal[value=${VENDOR_HOSTS}]`, message },
        { selector: `TemplateElement[value.raw=${VENDOR_HOSTS}]`, message },
      ],
    },
  },
  {
    files: ['src/**/*.vue'],
    rules: {
      'vue/no-restricted-syntax': [
        'error',
        { selector: `VAttribute > VLiteral[value=${VENDOR_HOSTS}]`, message },
        { selector: `VExpressionContainer Literal[value=${VENDOR_HOSTS}]`, message },
        { selector: `VText[value=${VENDOR_HOSTS}]`, message },
      ],
    },
  },
]
