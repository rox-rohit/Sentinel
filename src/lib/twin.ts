import type { HealthCategory, Severity } from '../data/types'
import { getJson, requestJson } from './api'

export interface TwinSensorDef {
  key: string
  label: string
}

export interface DeviceInfo {
  device_id: string
  name: string
  asset_id: string | null
  mode: 'manual' | 'auto'
  interval_ms: number
  token_prefix: string
  notes: string | null
  created_at: string | null
  updated_at: string | null
  last_seen_at: string | null
  token?: string
}

export interface TwinReading {
  sensor: string
  value: number
  median: number
  scale: number
  z_score: number
  deviation_pct: number | null
}

export interface TwinAssessment {
  usable: boolean
  health_score: number | null
  category: HealthCategory | null
  anomaly_score: number | null
  severity: Severity | null
  coverage: {
    expected: number
    matched: number
    coverage: number
    missing: string[]
    unknown: string[]
    rejected: string[]
  }
  sensors: TwinReading[]
  top_sensors: TwinReading[]
  explanation: string
}

export interface TwinSample {
  seq: number
  at: string | null
  cycle: number | null
  source: string
  health: number | null
  anomaly: number | null
  severity: Severity | null
  coverage: number | null
  sensors: Record<string, number>
}

export interface TwinTrend {
  direction: 'degrading' | 'recovering' | 'stable' | 'unknown'
  slope_per_sample: number | null
  window: number
  delta?: number
}

export interface TwinModelReference {
  asset_id: string
  label: string
  cycle: number
  lifetime: number
  estimate: number
  lower: number
  upper: number
  status: HealthCategory
  health_score: number
  note: string
}

export interface TwinAutoState {
  running: boolean
  cursor: number | null
  total_cycles: number | null
  started_at: string | null
  finished: boolean
  error: string | null
}

export interface TwinSnapshot {
  device: DeviceInfo
  twin: TwinAssessment | null
  latest: TwinSample | null
  history: TwinSample[]
  trend: TwinTrend
  baseline: {
    asset_id: string
    cycles: number
    sensor_count: number
    channels: Record<string, { median: number; scale: number; samples: number }>
  } | null
  model: TwinModelReference | null
  auto: TwinAutoState
  sample_count: number
  sensors: TwinSensorDef[]
}

export interface TwinSummary {
  device: DeviceInfo
  twin: TwinAssessment | null
  trend: TwinTrend
  model: TwinModelReference | null
  auto: TwinAutoState
  sample_count: number
}

const TOKEN_PREFIX = 'sentinel.device.'

/** Device tokens are session-scoped: they die with the browser tab. */
export function rememberDeviceToken(deviceId: string, token: string): void {
  try {
    window.sessionStorage.setItem(`${TOKEN_PREFIX}${deviceId}`, token)
  } catch {
    // The token still lives in component state for the current page.
  }
}

export function deviceToken(deviceId: string): string | null {
  try {
    return window.sessionStorage.getItem(`${TOKEN_PREFIX}${deviceId}`)
  } catch {
    return null
  }
}

export function forgetDeviceToken(deviceId: string): void {
  try {
    window.sessionStorage.removeItem(`${TOKEN_PREFIX}${deviceId}`)
  } catch {
    // Nothing to forget.
  }
}

export async function fetchTwins(): Promise<{ twins: TwinSummary[]; sensors: TwinSensorDef[] }> {
  return getJson<{ twins: TwinSummary[]; sensors: TwinSensorDef[] }>('/devices')
}

export async function fetchTwin(deviceId: string): Promise<TwinSnapshot> {
  return getJson<TwinSnapshot>(`/devices/${encodeURIComponent(deviceId)}?limit=180`)
}

export async function createTwin(input: {
  name: string
  asset_id: string | null
  mode: 'manual' | 'auto'
  interval_ms: number
}): Promise<{ device: DeviceInfo; token: string; twin: TwinSnapshot }> {
  return requestJson('/devices', { method: 'POST', body: input })
}

export async function updateTwin(
  deviceId: string,
  changes: Partial<Pick<DeviceInfo, 'name' | 'asset_id' | 'mode' | 'interval_ms'>>,
): Promise<DeviceInfo> {
  return requestJson<DeviceInfo>(`/devices/${encodeURIComponent(deviceId)}`, {
    method: 'PATCH',
    body: changes,
  })
}

export async function deleteTwin(deviceId: string): Promise<void> {
  await requestJson(`/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' })
}

export async function startAuto(deviceId: string): Promise<TwinAutoState> {
  const payload = await requestJson<{ auto: TwinAutoState }>(
    `/devices/${encodeURIComponent(deviceId)}/auto/start`, { method: 'POST', body: {} },
  )
  return payload.auto
}

export async function stopAuto(deviceId: string): Promise<TwinAutoState> {
  const payload = await requestJson<{ auto: TwinAutoState }>(
    `/devices/${encodeURIComponent(deviceId)}/auto/stop`, { method: 'POST', body: {} },
  )
  return payload.auto
}

export async function rotateTwinToken(
  deviceId: string,
): Promise<{ token: string; device: DeviceInfo }> {
  return requestJson(`/devices/${encodeURIComponent(deviceId)}/rotate-token`, {
    method: 'POST',
    body: {},
  })
}

export async function pushTwinSample(
  deviceId: string,
  token: string | null,
  sensors: Record<string, number>,
  cycle?: number | null,
): Promise<{ sample: TwinSample; twin: TwinAssessment }> {
  return requestJson(`/devices/${encodeURIComponent(deviceId)}/telemetry`, {
    method: 'POST',
    body: { sensors, cycle: cycle ?? null },
    headers: token ? { 'X-Device-Token': token } : {},
  })
}
