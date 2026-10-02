// Structure adapted from abhayla/algochanakya@bf9faf7:frontend/src/router/index.js (ADR-047): lazy routes, meta flags,
// catch-all. The route table itself is new: the seven sections (REQ-009), /settings/* and /health-status.
import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes.js'

export { routes }
const router = createRouter({ history: createWebHistory(), routes })

export default router
