import { Hono } from 'hono'

// Static hosting worker. The ML API is FastAPI (sentinel.api.main) and is not
// emulated here: the frontend falls back to the exported artifact snapshot when
// the API is unreachable, so this worker only serves assets and health.
type Env = {
  ASSETS: Fetcher
}

const app = new Hono<{ Bindings: Env }>()

app.get('/api/health', (c) =>
  c.json({ status: 'ok', service: 'sentinel-static', api: 'python-fastapi' }),
)

app.all('/api/*', (c) =>
  c.json(
    {
      error: {
        code: 'static_host',
        message:
          'This deployment serves the SENTINEL frontend and its build snapshot. Run the FastAPI service for live inference.',
      },
    },
    404,
  ),
)

app.all('*', (c) => c.env.ASSETS.fetch(c.req.raw))

export default app
