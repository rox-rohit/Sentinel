import { useCallback, useEffect, useRef, useState } from 'react'

import { useData } from './data-context'
import {
  createTwin,
  deleteTwin,
  deviceToken,
  fetchTwin,
  fetchTwins,
  forgetDeviceToken,
  rememberDeviceToken,
  rotateTwinToken,
  startAuto,
  stopAuto,
  updateTwin,
  type DeviceInfo,
  type TwinSensorDef,
  type TwinSnapshot,
  type TwinSummary,
} from './twin'

const POLL_MS = 2000
const LIST_POLL_MS = 15000

export interface TwinController {
  live: boolean
  loading: boolean
  twins: TwinSummary[]
  sensors: TwinSensorDef[]
  snapshot: TwinSnapshot | null
  selectedId: string | null
  token: string | null
  error: string | null
  busy: string | null
  select: (deviceId: string | null) => void
  create: (input: { name: string; asset_id: string | null; mode: 'manual' | 'auto'; interval_ms: number }) => Promise<DeviceInfo | null>
  patch: (deviceId: string, changes: Partial<Pick<DeviceInfo, 'name' | 'asset_id' | 'mode' | 'interval_ms'>>) => Promise<void>
  remove: (deviceId: string) => Promise<void>
  start: (deviceId: string) => Promise<void>
  stop: (deviceId: string) => Promise<void>
  rotate: (deviceId: string) => Promise<void>
  refresh: (deviceId?: string) => Promise<void>
  rememberToken: (deviceId: string, token: string) => void
}

/**
 * Twin state over the FastAPI service: list + selected snapshot, polled only
 * while the tab is visible. Device tokens stay in sessionStorage.
 */
export function useTwins(): TwinController {
  const { source } = useData()
  const live = source === 'live'
  const [twins, setTwins] = useState<TwinSummary[]>([])
  const [sensors, setSensors] = useState<TwinSensorDef[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<TwinSnapshot | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  const refreshList = useCallback(async () => {
    if (!live) {
      setLoading(false)
      return
    }
    try {
      const payload = await fetchTwins()
      if (!alive.current) return
      setTwins(payload.twins)
      setSensors(payload.sensors)
      setError(null)
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : 'Twin service unreachable')
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [live])

  const refreshSnapshot = useCallback(async (deviceId: string, quiet = false) => {
    if (!live) return
    try {
      const next = await fetchTwin(deviceId)
      if (!alive.current) return
      setSnapshot(next)
      if (!quiet) setError(null)
    } catch (cause) {
      if (alive.current && !quiet) {
        setError(cause instanceof Error ? cause.message : 'Twin snapshot unavailable')
      }
    }
  }, [live])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  useEffect(() => {
    if (!live) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refreshList()
    }, LIST_POLL_MS)
    return () => window.clearInterval(timer)
  }, [live, refreshList])

  useEffect(() => {
    if (!live || !selectedId) {
      setSnapshot(null)
      return
    }
    setToken(deviceToken(selectedId))
    void refreshSnapshot(selectedId)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refreshSnapshot(selectedId, true)
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [live, selectedId, refreshSnapshot])

  const select = useCallback((deviceId: string | null) => {
    setSelectedId(deviceId)
    setError(null)
  }, [])

  const run = useCallback(async <T,>(label: string, action: () => Promise<T>): Promise<T | null> => {
    setBusy(label)
    try {
      const result = await action()
      setError(null)
      return result
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Request failed')
      return null
    } finally {
      setBusy(null)
    }
  }, [])

  const rememberToken = useCallback((deviceId: string, nextToken: string) => {
    rememberDeviceToken(deviceId, nextToken)
    setToken(nextToken)
  }, [])

  const create = useCallback(async (input: {
    name: string; asset_id: string | null; mode: 'manual' | 'auto'; interval_ms: number
  }) => {
    const result = await run('create', () => createTwin(input))
    if (!result) return null
    rememberDeviceToken(result.device.device_id, result.token)
    setToken(result.token)
    setSelectedId(result.device.device_id)
    await refreshList()
    await refreshSnapshot(result.device.device_id)
    return result.device
  }, [run, refreshList, refreshSnapshot])

  const patch = useCallback(async (
    deviceId: string,
    changes: Partial<Pick<DeviceInfo, 'name' | 'asset_id' | 'mode' | 'interval_ms'>>,
  ) => {
    const updated = await run('patch', () => updateTwin(deviceId, changes))
    if (!updated) return
    setSnapshot((current) => (current ? { ...current, device: updated } : current))
    await refreshList()
    await refreshSnapshot(deviceId, true)
  }, [run, refreshList, refreshSnapshot])

  const remove = useCallback(async (deviceId: string) => {
    await run('remove', () => deleteTwin(deviceId))
    forgetDeviceToken(deviceId)
    setSelectedId(null)
    setSnapshot(null)
    setToken(null)
    await refreshList()
  }, [run, refreshList])

  const start = useCallback(async (deviceId: string) => {
    await run('start', () => startAuto(deviceId))
    await refreshSnapshot(deviceId, true)
    await refreshList()
  }, [run, refreshSnapshot, refreshList])

  const stop = useCallback(async (deviceId: string) => {
    await run('stop', () => stopAuto(deviceId))
    await refreshSnapshot(deviceId, true)
    await refreshList()
  }, [run, refreshSnapshot, refreshList])

  const rotate = useCallback(async (deviceId: string) => {
    const result = await run('rotate', () => rotateTwinToken(deviceId))
    if (!result) return
    rememberDeviceToken(deviceId, result.token)
    setToken(result.token)
    await refreshSnapshot(deviceId, true)
  }, [run, refreshSnapshot])

  const refresh = useCallback(async (deviceId?: string) => {
    await refreshList()
    if (deviceId) await refreshSnapshot(deviceId)
  }, [refreshList, refreshSnapshot])

  return {
    live, loading, twins, sensors, snapshot, selectedId, token, error, busy,
    select, create, patch, remove, start, stop, rotate, refresh, rememberToken,
  }
}
