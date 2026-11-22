import { Activity, ArrowLeft, Gauge, Timer, Wrench } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { TelemetryChart, AreaTrend } from '../components/charts/Charts'
import { Badge, Label } from '../components/ui/Badge'
import { HealthMeter, Ring } from '../components/ui/Meter'
import { Note, PageHeader } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { MiniStat, Stat } from '../components/ui/Stat'
import { useData } from '../lib/data-context'
import { API_BASE } from '../lib/api'
import type { Asset } from '../data/types'
import { number, percent } from '../lib/format'
import { navigate } from '../lib/router'

export function AssetDetail({ assetId }: { assetId: string }) {
  const { data, source } = useData()
  const listed = data.assets.find((entry) => entry.id.toUpperCase() === assetId.toUpperCase())
  const [fullAsset, setFullAsset] = useState<Asset | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // The list endpoint returns summaries; the detail endpoint carries telemetry.
  useEffect(() => {
    setFullAsset(null)
    setLoadError(null)
    if (!listed || listed.series || source !== 'live') return
    let cancelled = false
    fetch(`${API_BASE}/fleet/assets/${encodeURIComponent(listed.id)}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Asset request failed (${response.status})`)
        return response.json() as Promise<Asset>
      })
      .then((payload) => { if (!cancelled) setFullAsset(payload) })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : 'Asset request failed')
      })
    return () => { cancelled = true }
  }, [listed, source])

  const asset = fullAsset ?? listed
  const sensorKeys = Object.keys(asset?.series?.sensors ?? {})
  const [sensor, setSensor] = useState(sensorKeys[0] ?? 's2')

  const telemetry = useMemo(() => {
    if (!asset?.series) return []
    return asset.series.cycle.map((cycle, index) => ({
      cycle,
      value: asset.series.sensors[sensor]?.[index] ?? null,
    }))
  }, [asset, sensor])

  const healthTrend = useMemo(() => {
    if (!asset?.series) return []
    return asset.series.cycle.map((cycle, index) => ({
      cycle,
      health: asset.series.health[index],
      anomaly: asset.series.anomaly[index],
    }))
  }, [asset])

  const rulTrend = useMemo(() => {
    if (!asset?.series) return []
    return asset.series.cycle.map((cycle, index) => ({
      cycle,
      rul: asset.series.predicted_rul[index],
    }))
  }, [asset])

  if (!asset) {
    return (
      <div className="space-y-4">
        <PageHeader title="Asset not found" description={`No asset ${assetId} in the current fleet snapshot.`} />
        <button onClick={() => navigate('/assets')} className="text-[12px] text-[var(--color-accent)]">
          ← Back to machine intelligence
        </button>
      </div>
    )
  }

  if (!asset.series) {
    return (
      <div className="space-y-4">
        <PageHeader title={`${asset.label} · machine digital twin`} description="Loading telemetry…" />
        <Note>{loadError ?? 'Fetching the full asset record from the inference service.'}</Note>
      </div>
    )
  }

  const sensorLabel = asset.latest_sensors.find((entry) => entry.sensor === sensor)?.label ?? sensor
  const assetAlerts = data.alerts.filter((alert) => alert.asset_id === asset.id)

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={`Operations · ${asset.dataset.toUpperCase()}`}
        title={`${asset.label} · machine digital twin`}
        description={asset.source}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={asset.status}>{asset.status}</Badge>
            <button onClick={() => navigate('/assets')}
              className="inline-flex items-center gap-1 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted hover:text-fg">
              <ArrowLeft className="size-3.5" /> Fleet
            </button>
          </div>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[270px_1fr]">
        <Panel title="Asset state" subtitle={`Cycle ${asset.cycle} of recorded life ${asset.lifetime}`}>
          <div className="flex flex-col items-center gap-3">
            <Ring value={asset.health_score} label="Health" size={116} />
            <HealthMeter value={asset.health_score} className="w-full" />
            <p className="text-center text-[11px] leading-relaxed text-muted">{asset.health_explanation}</p>
            <div className="grid w-full grid-cols-2 gap-2">
              {Object.entries(asset.health_components).map(([key, value]) => (
                <div key={key} className="raised px-2 py-1.5">
                  <div className="text-[9px] uppercase tracking-[0.08em] text-faint">
                    {key.replace('_health', '').replace(/_/g, ' ')}
                  </div>
                  <div className="numeric mt-0.5 text-[12px]">{number(value, 0)}</div>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Estimated RUL" value={number(asset.rul.estimate, 0)} unit="cycles"
              icon={<Timer className="size-4" />} tone="accent"
              hint={`${number(asset.rul.lower, 0)} – ${number(asset.rul.upper, 0)} cycle band`} />
            <Stat label="Failure risk ≤ 30" value={percent(asset.rul.horizon_risk['30'] ?? 0)}
              icon={<Gauge className="size-4" />} tone={(asset.rul.horizon_risk['30'] ?? 0) > 0.5 ? 'bad' : 'default'}
              hint={`≤10 cycles ${percent(asset.rul.horizon_risk['10'] ?? 0)} · ≤50 ${percent(asset.rul.horizon_risk['50'] ?? 0)}`} />
            <Stat label="Anomaly score" value={number(asset.anomaly.score, 2)}
              icon={<Activity className="size-4" />} tone={asset.anomaly.severity === 'critical' ? 'bad' : 'warn'}
              hint={`Severity ${asset.anomaly.severity} · ensemble of 3 detectors`} />
            <Stat label="Degradation" value={number(asset.degradation.health_slope_per_cycle, 2)}
              unit="pts/cycle" icon={<Wrench className="size-4" />}
              hint={asset.degradation.direction} />
          </div>

          <Panel
            title="Sensor telemetry"
            subtitle={sensorLabel}
            action={
              <select
                value={sensor}
                onChange={(event) => setSensor(event.target.value)}
                className="rounded-[6px] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-2 py-1 text-[11px] text-muted outline-none"
              >
                {sensorKeys.map((key) => (
                  <option key={key} value={key}>
                    {asset.latest_sensors.find((entry) => entry.sensor === key)?.label ?? key}
                  </option>
                ))}
              </select>
            }
          >
            <TelemetryChart
              data={telemetry}
              xKey="cycle"
              series={[{ key: 'value', color: 'var(--chart-1)', label: sensorLabel }]}
              height={196}
            />
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Predicted RUL trajectory" subtitle="Model estimate at each recorded cycle">
          <AreaTrend data={rulTrend} xKey="cycle" yKey="rul" color="var(--chart-2)" height={190} name="Predicted RUL" />
          <div className="mt-2 flex items-center gap-3 text-[10px] text-faint">
            <span>Actual RUL at final recorded cycle: {asset.actual_rul_final ?? 'not labelled'}</span>
          </div>
        </Panel>
        <Panel title="Health and anomaly history" subtitle="Health score and ensemble anomaly score">
          <TelemetryChart
            data={healthTrend}
            xKey="cycle"
            series={[
              { key: 'health', color: 'var(--chart-4)', label: 'Health' },
              { key: 'anomaly', color: 'var(--chart-3)', label: 'Anomaly' },
            ]}
            height={190}
          />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Panel title="Current sensor snapshot" subtitle="Latest readings against the healthy baseline" bodyClassName="p-0">
          <div className="divide-y divide-[var(--color-line)]">
            {asset.latest_sensors.map((reading) => {
              const deviation = reading.healthy_mean
                ? ((reading.value - reading.healthy_mean) / Math.abs(reading.healthy_mean)) * 100
                : 0
              return (
                <div key={reading.sensor} className="flex items-center gap-3 px-4 py-2">
                  <span className="w-6 text-[10px] uppercase text-faint">{reading.sensor}</span>
                  <span className="min-w-0 flex-1 truncate text-[11.5px] text-muted">{reading.label}</span>
                  <span className="numeric text-[11.5px] text-fg">{number(reading.value, 2)}</span>
                  <span className={`numeric w-16 text-right text-[10.5px] ${Math.abs(deviation) > 8 ? 'text-[var(--color-warn)]' : 'text-faint'}`}>
                    {deviation > 0 ? '+' : ''}{deviation.toFixed(1)}%
                  </span>
                </div>
              )
            })}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Anomaly attribution" subtitle="Largest deviation from the healthy baseline">
            <div className="space-y-2.5">
              {asset.anomaly.top_sensors.map((entry) => (
                <div key={entry.sensor}>
                  <div className="mb-1 flex items-center justify-between text-[11px]">
                    <span className="text-muted">{entry.label}</span>
                    <span className="numeric text-fg">{entry.z_score > 0 ? '+' : ''}{entry.z_score.toFixed(1)} σ</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
                    <div className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, Math.abs(entry.z_score) * 4)}%`,
                        background: Math.abs(entry.z_score) > 3 ? 'var(--color-critical)' : 'var(--color-accent)',
                      }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {Object.entries(asset.anomaly.detectors).map(([name, value]) => (
                <MiniStat key={name} label={name.replace(/_/g, ' ')} value={number(value, 2)} />
              ))}
            </div>
          </Panel>

          <Panel title="Asset alerts" subtitle={`${assetAlerts.length} generated by the current build`}>
            {assetAlerts.length === 0 && <p className="text-[11.5px] text-muted">No alert for this asset.</p>}
            <ul className="space-y-2">
              {assetAlerts.map((alert, index) => (
                <li key={index} className="rounded-[8px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <Badge tone={alert.severity}>{alert.severity}</Badge>
                    <span className="text-[10px] uppercase tracking-[0.08em] text-faint">{alert.kind}</span>
                    <span className="ml-auto text-[10px] text-faint">cycle {alert.cycle}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted">{alert.message}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <p className="text-[10px] leading-relaxed text-faint">
        Analytical twin built from recorded telemetry and model outputs. The RUL band is an empirical residual interval;
        connect a machine to this asset in the{' '}
        <button onClick={() => navigate('/twins')} className="text-[var(--color-accent)] hover:underline">
          twin studio
        </button>{' '}
        to score incoming samples against the same baseline.
      </p>
      <div className="flex items-center gap-2 text-[10px] text-faint">
        <Label>Criticality</Label> {asset.criticality} (default) · <Label>Dataset</Label> {asset.dataset} ·
        <Label>Model</Label> {data.predictive.model}
      </div>
    </div>
  )
}
