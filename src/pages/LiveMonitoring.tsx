import { Pause, Play, RotateCcw, Wifi, WifiOff } from 'lucide-react'
import { useMemo, useState } from 'react'

import { AreaTrend, TelemetryChart } from '../components/charts/Charts'
import type { SeriesPoint } from '../components/charts/Charts'
import { Badge } from '../components/ui/Badge'
import { Note, PageHeader } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { cx } from '../lib/cx'
import { useData } from '../lib/data-context'
import { navigate } from '../lib/router'
import { number, percent } from '../lib/format'
import { useReplay } from '../lib/useReplay'

const SPEEDS = [0.5, 1, 2, 4]

function healthCategory(score: number | null): string {
  if (score === null) return 'unknown'
  if (score >= 80) return 'healthy'
  if (score >= 60) return 'attention'
  if (score >= 40) return 'warning'
  return 'critical'
}

export function LiveMonitoring() {
  const { data } = useData()
  const assets = useMemo(
    () => [...data.assets].sort((a, b) => a.asset_id - b.asset_id),
    [data.assets],
  )
  // Start on the longest recorded trajectory so the first replay has history.
  const [assetId, setAssetId] = useState(
    [...assets].sort((a, b) => b.cycle - a.cycle)[0]?.id ?? '',
  )
  // `?cycle=` opens the stream at a recorded cycle (useful for deep links).
  const startCycle = Number(new URLSearchParams(window.location.search).get('cycle') ?? 0) || 0
  const replay = useReplay(assetId, data, startCycle)
  const { meta, frames, latest, playing, speed, mode, status, notice } = replay
  const asset = assets.find((entry) => entry.id === assetId)

  const sensors = meta?.sensors ?? []
  const visibleSensors = sensors.slice(0, 2)

  const chartData: SeriesPoint[] = frames.map((frame) => ({
    cycle: frame.cycle,
    rul: frame.rul.estimate,
    health: frame.health,
    anomaly: frame.anomaly.score,
    ...Object.fromEntries(
      Object.entries(frame.sensors).map(([key, value]) => [`sensor_${key}`, value]),
    ),
  }))

  const events = useMemo(() => {
    const entries: { cycle: number; tone: 'warn' | 'bad'; message: string }[] = []
    let lastSeverity: string | null = null
    let lastCategory: string | null = null
    for (const frame of frames) {
      const category = healthCategory(frame.health)
      if (category !== lastCategory) {
        if (category === 'warning' || category === 'critical') {
          entries.push({
            cycle: frame.cycle,
            tone: category === 'critical' ? 'bad' : 'warn',
            message: `Health entered ${category} (${number(frame.health, 0)}/100).`,
          })
        }
        lastCategory = category
      }
      const severity = frame.anomaly.severity
      if (severity && severity !== lastSeverity && (severity === 'high' || severity === 'critical')) {
        entries.push({
          cycle: frame.cycle,
          tone: severity === 'critical' ? 'bad' : 'warn',
          message: `Anomaly ensemble escalated to ${severity} (score ${number(frame.anomaly.score, 2)}).`,
        })
      }
      lastSeverity = severity ?? lastSeverity
    }
    return entries.slice(-8).reverse()
  }, [frames])

  const streamBadge = mode === 'local'
    ? { tone: 'medium' as const, text: 'Local artifact replay', icon: WifiOff }
    : status === 'connecting'
      ? { tone: 'neutral' as const, text: 'Connecting…', icon: WifiOff }
      : status === 'ended'
        ? { tone: 'neutral' as const, text: 'Replay complete', icon: Wifi }
        : status === 'offline'
          ? { tone: 'medium' as const, text: 'Stream closed', icon: WifiOff }
          : { tone: 'healthy' as const, text: 'Streaming', icon: Wifi }

  const progress = meta && latest ? Math.min(100, (latest.cycle / meta.total_cycles) * 100) : 0
  const StatusIcon = streamBadge.icon

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Streaming"
        title="Live monitoring"
        description={
          meta?.source ??
          'Replays a recorded C-MAPSS trajectory cycle by cycle, with the model estimates the build pipeline produced for each cycle.'
        }
        actions={
          <>
            <Badge tone="neutral" dot>Recorded replay</Badge>
            <Badge tone={streamBadge.tone} dot>
              <StatusIcon className="size-3" />
              {streamBadge.text}
            </Badge>
          </>
        }
      />

      <Panel
        title="Replay controls"
        subtitle="Pacing only — pause, resume, seek and speed never alter the recorded data"
        action={
          <div className="flex items-center gap-1.5">
            <button
              onClick={replay.toggle}
              className="flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-fg transition-colors hover:border-[var(--color-line-strong)]"
              aria-pressed={playing}
            >
              {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              {playing ? 'Pause' : status === 'ended' ? 'Replay again' : 'Resume'}
            </button>
            <button
              onClick={replay.restart}
              className="flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted transition-colors hover:border-[var(--color-line-strong)] hover:text-fg"
            >
              <RotateCcw className="size-3.5" />
              Restart
            </button>
          </div>
        }
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Asset</span>
            <select
              value={assetId}
              onChange={(event) => setAssetId(event.target.value)}
              className="mt-1 block min-w-[190px] rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11.5px] text-fg"
            >
              {assets.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label} · {entry.status} · {number(entry.health_score, 0)}/100
                </option>
              ))}
            </select>
          </label>

          <div>
            <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Speed</span>
            <div className="mt-1 flex overflow-hidden rounded-[7px] border border-[var(--color-line)]">
              {SPEEDS.map((value) => (
                <button
                  key={value}
                  onClick={() => replay.setSpeed(value)}
                  aria-pressed={speed === value}
                  className={cx(
                    'numeric px-2.5 py-1.5 text-[11px] transition-colors',
                    speed === value
                      ? 'bg-[var(--accent-soft)] text-[var(--color-accent)]'
                      : 'text-muted hover:bg-[var(--overlay-2)] hover:text-fg',
                  )}
                >
                  {value}×
                </button>
              ))}
            </div>
          </div>

          <div className="min-w-[200px] flex-1">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.1em] text-faint">
              <span>Cursor</span>
              <span className="numeric text-muted">
                {latest ? `${latest.cycle} / ${meta?.total_cycles ?? latest.total_cycles} cycles` : 'waiting for frames'}
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
              <div
                className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-200"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {asset && (
            <div className="text-[10.5px] text-muted">
              Dataset state: <span className="text-fg">{asset.status}</span> · model RUL{' '}
              <span className="numeric text-fg">{number(asset.rul.estimate, 0)} cyc</span>
            </div>
          )}
        </div>

        {notice && (
          <div className="mt-3">
            <Note tone="warn">{notice}</Note>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Cycle" value={latest ? latest.cycle : '—'} unit={`of ${meta?.total_cycles ?? '—'}`}
          tone="accent" hint="Recorded operating cycle" />
        <Stat label="RUL estimate" value={latest?.rul.estimate != null ? number(latest.rul.estimate, 0) : '—'}
          unit="cycles"
          hint={
            latest?.rul.lower != null && latest?.rul.upper != null
              ? `80% band ${number(latest.rul.lower, 0)}–${number(latest.rul.upper, 0)}`
              : mode === 'local'
                ? 'Band unavailable in local replay'
                : 'No band at this cycle'
          } />
        <Stat label="Health score" value={latest?.health != null ? number(latest.health, 0) : '—'}
          unit="/ 100" tone={latest?.health != null && latest.health < 60 ? 'warn' : 'default'}
          hint={latest ? healthCategory(latest.health) : '—'} />
        <Stat label="Anomaly score" value={latest?.anomaly.score != null ? number(latest.anomaly.score, 2) : '—'}
          tone={latest?.anomaly.severity === 'high' || latest?.anomaly.severity === 'critical' ? 'bad' : 'default'}
          hint={
            latest?.anomaly.severity
              ? `${latest.anomaly.severity} severity`
              : mode === 'local'
                ? 'Severity unavailable locally'
                : 'No severity at this cycle'
          } />
        <Stat label="Risk ≤ 30 cycles" value={latest?.risk_30 != null ? percent(latest.risk_30) : '—'}
          hint="Empirical residual CDF at this cycle" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="RUL estimate" subtitle="Model prediction per recorded cycle">
          <AreaTrend data={chartData} xKey="cycle" yKey="rul" color="var(--chart-1)" height={170} name="RUL" />
        </Panel>
        <Panel title="Health score" subtitle="Transparent weighted score per cycle">
          <AreaTrend data={chartData} xKey="cycle" yKey="health" color="var(--chart-4)" height={170} name="Health" />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel
          title="Sensor telemetry"
          subtitle={visibleSensors.length ? visibleSensors.map((s) => s.label).join(' · ') : 'Waiting for the stream'}
        >
          <TelemetryChart
            data={chartData}
            xKey="cycle"
            height={190}
            series={visibleSensors.map((sensor, index) => ({
              key: `sensor_${sensor.key}`,
              color: index === 0 ? 'var(--chart-1)' : 'var(--chart-3)',
              label: sensor.key.toUpperCase(),
            }))}
          />
          <p className="mt-1 text-[10.5px] text-muted">
            Recorded C-MAPSS channels, replayed at the selected speed. Values are raw sensor readings, not scaled.
          </p>
        </Panel>

        <Panel title="Event log" subtitle="Transitions observed during this replay">
          {events.length === 0 ? (
            <p className="text-[11px] text-muted">
              No health or anomaly escalation in the frames received so far.
            </p>
          ) : (
            <ul className="space-y-2">
              {events.map((event, index) => (
                <li key={`${event.cycle}-${index}`} className="raised px-2.5 py-2">
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.08em]">
                    <span className={event.tone === 'bad' ? 'text-[var(--color-bad)]' : 'text-[var(--color-warn)]'}>
                      {event.tone === 'bad' ? 'Critical' : 'Warning'}
                    </span>
                    <span className="numeric text-faint">cycle {event.cycle}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted">{event.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <p className="text-[10px] leading-relaxed text-faint">
        {meta?.source ?? 'Recorded C-MAPSS trajectory replayed from the build artifact.'}{' '}
        {mode === 'local'
          ? 'Artifact series in use; the replay API is not connected.'
          : 'Frames and estimates are served over the API WebSocket.'}{' '}
        Gateway and manual feeds live in the{' '}
        <button onClick={() => navigate('/twins')} className="text-[var(--color-accent)] hover:underline">
          machine twin studio
        </button>.
      </p>
    </div>
  )
}
