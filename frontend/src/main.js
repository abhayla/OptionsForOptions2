// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/main.js (ADR-047). No kite-theme.css (ADR-049).
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
