// LOCAL ONLY: a stub for GET /health so the health spec can run without PostgreSQL. It mirrors the real response
// shape of backend/ofo_app/routes/health.py. The real-backend proof runs in CI, not with this stub.
import http from 'node:http'

const port = Number(process.env.STUB_PORT || 8000)
http
  .createServer((req, res) => {
    if (req.url === '/health') {
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ status: 'healthy', database: 'connected' }))
    } else {
      res.writeHead(404).end()
    }
  })
  .listen(port, '127.0.0.1', () => console.log(`stub api on ${port}`))
