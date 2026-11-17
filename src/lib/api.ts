import snapshotJson from '../generated/snapshot.json'
import type { Snapshot } from '../data/types'

export const SNAPSHOT = snapshotJson as unknown as Snapshot

export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000/api/v1'

export type DataSource = 'live' | 'snapshot'

export interface DatasetState {
  data: Snapshot
  source: DataSource
  error: string | null
}

async function getJson<T>(path: string, timeoutMs = 4000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_BASE}${path}`, { signal: controller.signal })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    return (await response.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Load the platform payload.
 *
 * The snapshot is a build artifact produced by the Python pipeline, not sample
 * data. It is used when the FastAPI service is not reachable (for example in a
 * static preview); the UI always shows which source is active.
 */
export async function loadDataset(): Promise<DatasetState> {
  try {
    const status = await getJson<{ status: string; build_version: string }>('/health')
    if (status.status !== 'ok') throw new Error('API reported a degraded state')
    const [fleet, assets, alerts, predictive, anomalies, rul, explainability, maintenance, forecast] =
      await Promise.all([
        getJson<Snapshot['fleet']>('/fleet/summary'),
        getJson<{ assets: Snapshot['assets'] }>('/fleet/assets?sort=health'),
        getJson<{ alerts: Snapshot['alerts'] }>('/alerts?limit=60'),
        getJson<Snapshot['predictive']>('/predictions'),
        getJson<Snapshot['anomalies']>('/anomalies'),
        getJson<Snapshot['rul']>('/rul'),
        getJson<Snapshot['explainability']>('/explainability'),
        getJson<Snapshot['maintenance']>('/maintenance'),
        getJson<Snapshot['forecast']>('/forecast'),
      ])
    const data: Snapshot = {
      ...SNAPSHOT,
      fleet: { ...fleet, health_weights: SNAPSHOT.fleet.health_weights },
      assets: assets.assets,
      alerts: alerts.alerts,
      predictive,
      anomalies,
      rul,
      explainability,
      maintenance,
      forecast,
    }
    return { data, source: 'live', error: null }
  } catch (error) {
    return {
      data: SNAPSHOT,
      source: 'snapshot',
      error: error instanceof Error ? error.message : 'API unreachable',
    }
  }
}

export async function predictFailure(input: Record<string, number | string>) {
  return postJson('/predict/failure', input)
}

export async function explainFailure(input: Record<string, number | string>) {
  return postJson('/predict/failure/explain', input)
}

export async function optimizeMaintenance(budget: number) {
  return postJson('/maintenance/optimize', { budget })
}

async function postJson<T = Record<string, unknown>>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = (await response.json()) as T & { error?: { message?: string } }
  if (!response.ok) throw new Error(payload.error?.message ?? `Request failed (${response.status})`)
  return payload
}
