import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { Asset, Severity, Snapshot } from '../data/types'
import { API_BASE } from './api'

export type ReplayMode = 'live' | 'local'
export type ReplayStatus = 'connecting' | 'open' | 'ended' | 'offline'

export interface ReplaySensor {
  key: string
  label: string
}

export interface ReplayFrame {
  cycle: number
  total_cycles: number
  seq: number
  sensors: Record<string, number>
  rul: { estimate: number | null; lower: number | null; upper: number | null }
  risk_30: number | null
  health: number | null
  anomaly: { score: number | null; severity: Severity | null }
}

export interface ReplayMeta {
  asset_id: string
  label: string
  total_cycles: number
  first_cycle: number
  sensors: ReplaySensor[]
  source: string
  disclaimer: string
}

const BUFFER = 90
const CONNECT_TIMEOUT_MS = 3000
const LOCAL_BASE_INTERVAL_MS = 700

function localFrames(asset: Asset): ReplayFrame[] {
  const series = asset.series
  // The live fleet list intentionally omits the full series; only the artifact
  // snapshot (or the detail endpoint) carries it, so guard the fallback.
  if (!series || !series.cycle) return []
  const total = series.cycle[series.cycle.length - 1] ?? asset.cycle
  return series.cycle.map((cycle, index) => ({
    cycle,
    total_cycles: total,
    seq: index + 1,
    sensors: Object.fromEntries(
      Object.entries(series.sensors).map(([key, values]) => [key, values[index] ?? 0]),
    ),
    rul: { estimate: series.predicted_rul[index] ?? null, lower: null, upper: null },
    risk_30: null,
    health: series.health[index] ?? null,
    anomaly: { score: series.anomaly[index] ?? null, severity: null },
  }))
}

/** The JSON we send to the server and the commands the local player accepts. */
type Command =
  | { action: 'pause' }
  | { action: 'resume' }
  | { action: 'speed'; speed: number }
  | { action: 'seek'; cycle: number }
  | { action: 'restart' }

export interface ReplayController {
  meta: ReplayMeta | null
  frames: ReplayFrame[]
  latest: ReplayFrame | null
  playing: boolean
  speed: number
  mode: ReplayMode
  status: ReplayStatus
  notice: string | null
  setSpeed: (speed: number) => void
  toggle: () => void
  restart: () => void
  seekTo: (cycle: number) => void
}

/**
 * Streams a recorded C-MAPSS trajectory from the API, and falls back to the
 * exported per-asset snapshot series (clearly labelled) when the API or the
 * replay artifact is unavailable.
 */
export function useReplay(assetId: string, snapshot: Snapshot): ReplayController {
  const asset = useMemo(
    () => snapshot.assets.find((entry) => entry.id === assetId) ?? snapshot.assets[0],
    [assetId, snapshot.assets],
  )
  const local = useMemo(() => (asset ? localFrames(asset) : []), [asset])

  const [mode, setMode] = useState<ReplayMode>('live')
  const [status, setStatus] = useState<ReplayStatus>('connecting')
  const [notice, setNotice] = useState<string | null>(null)
  const [meta, setMeta] = useState<ReplayMeta | null>(null)
  const [frames, setFrames] = useState<ReplayFrame[]>([])
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeedState] = useState(1)
  const [cursor, setCursor] = useState(0)

  const socketRef = useRef<WebSocket | null>(null)
  const openedRef = useRef(false)
  const timerRef = useRef<number | null>(null)

  const applyCommand = useCallback((command: Command) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(command))
    }
  }, [])

  // -- open one stream per asset ----------------------------------------
  useEffect(() => {
    if (!asset) return
    let cancelled = false
    openedRef.current = false
    setMode('live')
    setStatus('connecting')
    setNotice(null)
    setFrames([])
    setMeta(null)
    setPlaying(true)
    setSpeedState(1)
    setCursor(0)

    const localMeta: ReplayMeta = {
      asset_id: asset.id,
      label: asset.label,
      total_cycles: local[local.length - 1]?.total_cycles ?? asset.cycle,
      first_cycle: local[0]?.cycle ?? 1,
      sensors: Object.keys(asset.series?.sensors ?? {}).map((key) => ({
        key,
        label: asset.latest_sensors?.find((s) => s.sensor === key)?.label ?? key,
      })),
      source: 'Exported artifact snapshot — per-asset series recorded during the build.',
      disclaimer:
        'Simulated replay of recorded data from the exported build artifact. The API is not connected, so RUL bands and anomaly severity are unavailable.',
    }

    const fallback = (reason: string) => {
      if (cancelled || openedRef.current) return
      setMode('local')
      setStatus('offline')
      setNotice(
        local.length > 0
          ? reason
          : `${reason} This view has no per-asset series in the snapshot; start the API for streaming replay.`,
      )
      setMeta(localMeta)
      setFrames(local.slice(0, 1))
      setCursor(0)
      setPlaying(true)
    }

    const url = `${API_BASE.replace(/^http/, 'ws')}/ws/replay/${encodeURIComponent(asset.id)}`
    let socket: WebSocket | null = null
    let timeout = 0

    const open = () => {
      if (cancelled) return
      try {
        socket = new WebSocket(url)
      } catch {
        fallback('Could not open a WebSocket to the API; using the exported artifact snapshot.')
        return
      }
      const active = socket
      socketRef.current = active
      timeout = window.setTimeout(() => {
        if (!openedRef.current) {
          active.close()
          fallback('Replay API did not answer within 3 s; using the exported artifact snapshot.')
        }
      }, CONNECT_TIMEOUT_MS)

      active.onmessage = (event) => {
      if (cancelled) return
      let message: Record<string, unknown>
      try {
        message = JSON.parse(event.data as string) as Record<string, unknown>
      } catch {
        setNotice('Received a malformed frame from the replay stream; ignoring it.')
        return
      }
      if (message.type === 'meta') {
        openedRef.current = true
        window.clearTimeout(timeout)
        setStatus('open')
        setMode('live')
        setNotice(null)
        setMeta({
          asset_id: String(message.asset_id),
          label: String(message.label),
          total_cycles: Number(message.total_cycles),
          first_cycle: Number(message.first_cycle),
          sensors: (message.sensors as ReplaySensor[]) ?? [],
          source: String(message.source),
          disclaimer: String(message.disclaimer),
        })
      } else if (message.type === 'frame') {
        const frame: ReplayFrame = {
          cycle: Number(message.cycle),
          total_cycles: Number(message.total_cycles),
          seq: Number(message.seq),
          sensors: (message.sensors as Record<string, number>) ?? {},
          rul: {
            estimate: message.rul_estimate == null ? null : Number(message.rul_estimate),
            lower: message.rul_lower == null ? null : Number(message.rul_lower),
            upper: message.rul_upper == null ? null : Number(message.rul_upper),
          },
          risk_30: message.risk_30 == null ? null : Number(message.risk_30),
          health: message.health == null ? null : Number(message.health),
          anomaly: {
            score: message.anomaly_score == null ? null : Number(message.anomaly_score),
            severity: (message.anomaly_severity as Severity | null) ?? null,
          },
        }
        setFrames((current) => [...current, frame].slice(-BUFFER))
      } else if (message.type === 'state') {
        setPlaying(Boolean(message.playing))
        setSpeedState(Number(message.speed))
      } else if (message.type === 'end') {
        setStatus('ended')
        setPlaying(false)
      } else if (message.type === 'error') {
        setNotice(String(message.message ?? 'Replay error'))
      }
      }

      active.onerror = () => {
      if (!openedRef.current) {
        fallback('WebSocket connection failed; using the exported artifact snapshot.')
      }
      }

      active.onclose = () => {
        window.clearTimeout(timeout)
        if (cancelled) return
        if (!openedRef.current) {
          fallback('Replay stream unavailable; using the exported artifact snapshot.')
        } else {
          setStatus((current) => (current === 'ended' ? current : 'offline'))
          setPlaying(false)
        }
      }
    }

    // Defer one tick: React StrictMode mounts, cleans up and remounts. Opening
    // synchronously would emit a spurious "closed before established" socket.
    const startTimer = window.setTimeout(open, 0)

    return () => {
      cancelled = true
      window.clearTimeout(startTimer)
      window.clearTimeout(timeout)
      if (socket) {
        socket.onclose = null
        socket.close()
      }
      socketRef.current = null
    }
  }, [asset, local])

  // -- local player ------------------------------------------------------
  useEffect(() => {
    if (mode !== 'local' || !playing || local.length === 0) return
    const id = window.setInterval(() => {
      setCursor((current) => {
        if (current + 1 >= local.length) {
          setPlaying(false)
          setStatus('ended')
          return current
        }
        return current + 1
      })
    }, LOCAL_BASE_INTERVAL_MS / speed)
    timerRef.current = id
    return () => window.clearInterval(id)
  }, [mode, playing, speed, local])

  useEffect(() => {
    if (mode !== 'local') return
    setFrames(local.slice(0, cursor + 1).slice(-BUFFER))
  }, [cursor, local, mode])

  const setSpeed = useCallback(
    (next: number) => {
      setSpeedState(next)
      applyCommand({ action: 'speed', speed: next })
    },
    [applyCommand],
  )

  const toggle = useCallback(() => {
    setPlaying((current) => {
      const next = !current
      applyCommand({ action: next ? 'resume' : 'pause' })
      if (mode === 'local' && next && status === 'ended') {
        setCursor(0)
        setStatus('offline')
      }
      return next
    })
  }, [applyCommand, mode, status])

  const restart = useCallback(() => {
    setCursor(0)
    setStatus(mode === 'live' ? 'open' : 'offline')
    setPlaying(true)
    setFrames(mode === 'local' ? local.slice(0, 1) : [])
    applyCommand({ action: 'restart' })
  }, [applyCommand, local, mode])

  const seekTo = useCallback(
    (cycle: number) => {
      applyCommand({ action: 'seek', cycle })
      if (mode === 'local') {
        const index = local.findIndex((frame) => frame.cycle >= cycle)
        setCursor(index < 0 ? local.length - 1 : index)
      }
    },
    [applyCommand, local, mode],
  )

  const latest = frames.length > 0 ? frames[frames.length - 1] : null

  return {
    meta,
    frames,
    latest,
    playing,
    speed,
    mode,
    status,
    notice,
    setSpeed,
    toggle,
    restart,
    seekTo,
  }
}
