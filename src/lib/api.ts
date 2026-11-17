import snapshotJson from '../generated/snapshot.json'
import type {
  AlertInbox,
  AlertLifecycle,
  MappingProfile,
  OnboardingReport,
  OnboardingInspection,
  PlantAsset,
  ScenarioComparison,
  ScenarioSummary,
  Snapshot,
} from '../data/types'

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

/** Who is recorded on lifecycle transitions until the platform has real identities. */
export const ALERT_ACTOR = 'console-operator'

export async function fetchAlerts(limit = 200): Promise<AlertInbox> {
  return getJson<AlertInbox>(`/alerts?limit=${limit}`)
}

export async function acknowledgeAlert(id: number, note?: string): Promise<AlertLifecycle> {
  return postJson<AlertLifecycle>(`/alerts/${id}/acknowledge`, { actor: ALERT_ACTOR, note })
}

export async function resolveAlert(id: number, note?: string): Promise<AlertLifecycle> {
  return postJson<AlertLifecycle>(`/alerts/${id}/resolve`, { actor: ALERT_ACTOR, note })
}

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  const payload = await getJson<{ scenarios: ScenarioSummary[] }>('/maintenance/scenarios')
  return payload.scenarios
}

export async function saveScenario(name: string, budget: number, note?: string) {
  return postJson<ScenarioSummary>('/maintenance/scenarios', { name, budget, note })
}

export async function compareScenarios(ids: number[]): Promise<ScenarioComparison> {
  const query = ids.map((id) => `ids=${id}`).join('&')
  return getJson<ScenarioComparison>(`/maintenance/scenarios/compare?${query}`, 8000)
}

export async function deleteScenario(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/maintenance/scenarios/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: { message?: string } }
    throw new Error(payload.error?.message ?? `Request failed (${response.status})`)
  }
}

export async function inspectPlantCsv(text: string, filename = 'upload.csv') {
  const response = await fetch(
    `${API_BASE}/onboarding/inspect?filename=${encodeURIComponent(filename)}`,
    { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: text },
  )
  const payload = (await response.json()) as OnboardingInspection & { error?: { message?: string } }
  if (!response.ok) throw new Error(payload.error?.message ?? `Request failed (${response.status})`)
  return payload
}

export async function validatePlantCsv(
  csv_text: string,
  mapping: Record<string, string>,
  source_file = 'upload.csv',
  profile_id?: number,
): Promise<OnboardingReport> {
  return postJson<OnboardingReport>('/onboarding/validate', {
    csv_text,
    mapping,
    source_file,
    profile_id: profile_id ?? null,
  })
}

export async function importPlantCsv(
  name: string,
  csv_text: string,
  mapping: Record<string, string>,
  source_file = 'upload.csv',
  profile_id?: number,
  accept_drift = false,
) {
  return postJson<{ report: OnboardingReport; assets: PlantAsset[] }>('/onboarding/import', {
    name,
    csv_text,
    mapping,
    source_file,
    profile_id: profile_id ?? null,
    accept_drift,
  })
}

export async function fetchMappingProfiles(): Promise<MappingProfile[]> {
  const payload = await getJson<{ profiles: MappingProfile[] }>('/onboarding/profiles')
  return payload.profiles
}

export async function saveMappingProfile(
  name: string,
  source: string,
  mapping: Record<string, string>,
  expected_columns: string[],
  notes?: string,
): Promise<MappingProfile> {
  return postJson<MappingProfile>('/onboarding/profiles', {
    name,
    source,
    mapping,
    expected_columns,
    notes,
  })
}

export async function applyMappingProfile(
  id: number,
  csvText: string,
): Promise<{ profile_id: number; mapping: Record<string, string>; drift: import('../data/types').SchemaDrift }> {
  const response = await fetch(`${API_BASE}/onboarding/profiles/${id}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/csv' },
    body: csvText,
  })
  const payload = await response.json() as {
    error?: { message?: string }
    profile_id: number
    mapping: Record<string, string>
    drift: import('../data/types').SchemaDrift
  }
  if (!response.ok) throw new Error(payload.error?.message ?? `Request failed (${response.status})`)
  return payload
}

export async function deleteMappingProfile(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/onboarding/profiles/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: { message?: string } }
    throw new Error(payload.error?.message ?? `Request failed (${response.status})`)
  }
}

export async function fetchPlantAssets(): Promise<PlantAsset[]> {
  const payload = await getJson<{ assets: PlantAsset[] }>('/onboarding/assets')
  return payload.assets
}

export async function scorePlantAsset(id: number) {
  return postJson<{
    eligible: boolean
    prediction: { predicted_rul: number; lower: number; upper: number; model: string; clip: number }
  }>(`/onboarding/assets/${id}/score`, {})
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
