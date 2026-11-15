import { expect, test } from 'bun:test'

import app from '../src/worker/index'

const env = {
  ASSETS: {
    fetch: async () => new Response('<html>SENTINEL</html>', { headers: { 'Content-Type': 'text/html' } }),
  },
} as unknown as { ASSETS: Fetcher }

test('health endpoint reports the static service and points live inference at FastAPI', async () => {
  const response = await app.request('https://example.test/api/health', {}, env)
  expect(response.status).toBe(200)
  const payload = (await response.json()) as { status: string; api: string }
  expect(payload.status).toBe('ok')
  expect(payload.api).toBe('python-fastapi')
})

test('unknown API routes return JSON, never HTML', async () => {
  const response = await app.request('https://example.test/api/models', {}, env)
  expect(response.status).toBe(404)
  const payload = (await response.json()) as { error: { code: string } }
  expect(payload.error.code).toBe('static_host')
})

test('non-API routes are served from assets', async () => {
  const response = await app.request('https://example.test/', {}, env)
  expect(await response.text()).toContain('SENTINEL')
})
