// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/main.js (ADR-047). No kite-theme.css (ADR-049).
import { createApp } from 'vue'
import { createPinia } from 'pinia'
// UI-007 (ADR-193): Inter 400/500/600/700, bundled (font-display: swap). Self-hosted, not a Google Fonts link, so the
// browser reaches no third-party host and the built bundle holds no outside URL (tests/test_bundle_secret_scan.py).
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
