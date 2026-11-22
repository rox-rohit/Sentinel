import {
  Activity,
  ArrowUpRight,
  Check,
  Copy,
  Gauge,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Wifi,
  Zap,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AreaTrend } from '../components/charts/Charts'
import { TwinSchematic } from '../components/twin/TwinSchematic'
import { Badge } from '../components/ui/Badge'
import { Ring } from '../components/ui/Meter'
import { PageHeader } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { MiniStat } from '../components/ui/Stat'
import { API_BASE } from '../lib/api'
import { cx } from '../lib/cx'
import { useData } from '../lib/data-context'
import { number, relativeTime } from '../lib/format'
import { pushTwinSample } from '../lib/twin'
import type { TwinSummary } from '../lib/twin'
import { useTwins } from '../lib/useTwins'

const INTERVALS = [250, 500, 1000, 1500, 3000]

function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1600)
        } catch {
          setCopied(false)
        }
      }}
      className="inline-flex items-center gap-1.5 rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted transition-colors hover:border-[var(--color-line-strong)] hover:text-fg"
    >
      {copied ? <Check className="size-3 text-[var(--color-good)]" /> : <Copy className="size-3" />}
      {copied ? 'Copied' : label}
    </button>
  )
}

function DeviceCard({
  entry,
  active,
  onSelect,
}: {
  entry: TwinSummary
  active: boolean
  onSelect: () => void
}) {
  const { device, twin, auto } = entry
  const status = twin?.category ?? null
  return (
    <button
      onClick={onSelect}
      className={cx(
        'w-full rounded-[10px] border px-3 py-2.5 text-left transition-colors',
        active
          ? 'border-[var(--accent-line)] bg-[var(--accent-soft)]'
          : 'border-[var(--color-line)] bg-[var(--overlay-1)] hover:border-[var(--color-line-strong)]',
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className="size-2 shrink-0 rounded-full"
          style={{ background: status ? `var(--color-${status === 'attention' ? 'accent' : status})` : 'var(--faint)' }}
        />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-fg">{device.name}</span>
        {auto.running && <Radio className="size-3 animate-[pulse-soft_2s_ease-in-out_infinite] text-[var(--color-accent)]" />}
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-faint">
        <span className="truncate">{device.asset_id ?? 'unbound'} · {device.mode}</span>
        <span className="numeric">
          {twin?.health_score != null ? `${number(twin.health_score, 0)}/100` : 'no sample'}
        </span>
      </div>
    </button>
  )
}

function CreateForm({
  assets,
  busy,
  onCreate,
  onCancel,
}: {
  assets: { id: string; label: string }[]
  busy: boolean
  onCreate: (input: { name: string; asset_id: string | null; mode: 'manual' | 'auto'; interval_ms: number }) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [assetId, setAssetId] = useState(assets[0]?.id ?? '')
  const [mode, setMode] = useState<'manual' | 'auto'>('manual')
  const [interval, setIntervalMs] = useState(1500)

  return (
    <div className="grid gap-3 md:grid-cols-[1.2fr_1fr_auto_auto_auto] md:items-end">
      <label className="block">
        <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Twin name</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Line 3 compressor"
          className="mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-1.5 text-[11.5px] outline-none focus:border-[var(--accent-line)]"
        />
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Baseline asset</span>
        <select
          value={assetId}
          onChange={(event) => setAssetId(event.target.value)}
          className="mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11.5px] text-fg"
        >
          {assets.map((asset) => (
            <option key={asset.id} value={asset.id}>{asset.label}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Mode</span>
        <select
          value={mode}
          onChange={(event) => setMode(event.target.value as 'manual' | 'auto')}
          className="mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11.5px] text-fg"
        >
          <option value="manual">Manual</option>
          <option value="auto">Auto</option>
        </select>
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Interval</span>
        <select
          value={interval}
          onChange={(event) => setIntervalMs(Number(event.target.value))}
          className="mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11.5px] text-fg"
        >
          {INTERVALS.map((value) => <option key={value} value={value}>{value} ms</option>)}
        </select>
      </label>
      <div className="flex items-center gap-2">
        <button
          onClick={() => name.trim() && onCreate({ name: name.trim(), asset_id: assetId || null, mode, interval_ms: interval })}
          disabled={!name.trim() || busy}
          className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] disabled:opacity-40"
        >
          <Plus className="size-3.5" /> Create
        </button>
        <button onClick={onCancel} className="px-1 py-1.5 text-[11px] text-faint hover:text-fg">Cancel</button>
      </div>
    </div>
  )
}

export function DigitalTwin() {
  const { data } = useData()
  const controller = useTwins()
  const { live, twins, snapshot, selectedId, token, error, busy, select } = controller
  const assets = useMemo(
    () => data.assets.map((asset) => ({ id: asset.id, label: `${asset.label} · ${asset.status}` })),
    [data.assets],
  )

  const [creating, setCreating] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [cycle, setCycle] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const initialisedFor = useRef<string | null>(null)

  useEffect(() => {
    if (!selectedId && twins.length > 0) select(twins[0].device.device_id)
  }, [selectedId, twins, select])

  useEffect(() => {
    if (!snapshot) return
    if (initialisedFor.current === snapshot.device.device_id) return
    initialisedFor.current = snapshot.device.device_id
    const latest = snapshot.latest?.sensors ?? {}
    const baseline = snapshot.baseline?.channels ?? {}
    const next: Record<string, string> = {}
    for (const sensor of snapshot.sensors) {
      const value = latest[sensor.key] ?? baseline[sensor.key]?.median
      next[sensor.key] = value === undefined ? '' : String(Number(value.toFixed(3)))
    }
    setValues(next)
  }, [snapshot])

  const pushSample = useCallback(async () => {
    if (!snapshot) return
    const sensors: Record<string, number> = {}
    for (const [key, raw] of Object.entries(values)) {
      if (raw.trim() === '') continue
      const parsed = Number(raw)
      if (Number.isFinite(parsed)) sensors[key] = parsed
    }
    if (Object.keys(sensors).length === 0) {
      setNotice('Enter at least one channel value.')
      return
    }
    try {
      await pushTwinSample(snapshot.device.device_id, token, sensors, cycle.trim() ? Number(cycle) : null)
      setNotice(`Sample accepted at ${new Date().toLocaleTimeString()}.`)
      await controller.refresh(snapshot.device.device_id)
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : 'Sample rejected')
    }
  }, [snapshot, values, cycle, token, controller])

  const connection = useMemo(() => {
    if (!snapshot) return ''
    const sample = Object.fromEntries(
      Object.entries(values)
        .filter(([, value]) => value.trim() !== '')
        .slice(0, 3)
        .map(([key, value]) => [key, Number(value)]),
    )
    return [
      `POST ${API_BASE}/devices/${snapshot.device.device_id}/telemetry`,
      'Content-Type: application/json',
      'X-Device-Token: <device token>',
      '',
      JSON.stringify({ sensors: sample, cycle: 42 }, null, 2),
    ].join('\n')
  }, [snapshot, values])

  const twin = snapshot?.twin ?? null
  const history = snapshot?.history ?? []
  const chartData = useMemo(
    () => history.map((entry) => ({ seq: entry.seq, health: entry.health, anomaly: entry.anomaly })),
    [history],
  )
  const readings = twin?.sensors ?? []
  const severityTone: 'high' | 'neutral' =
    twin?.severity === 'critical' || twin?.severity === 'high' ? 'high' : 'neutral'

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Digital twin"
        title="Machine twin studio"
        description="Bind a machine to its digital twin, push real readings by hand or stream them from a gateway, and watch health, deviation and model estimates update together."
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={live ? 'healthy' : 'neutral'} dot>
              {live ? 'Twin service' : 'API offline'}
            </Badge>
            <button
              onClick={() => setCreating((current) => !current)}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-2.5 py-1.5 text-[11px] text-[var(--color-accent)]"
            >
              <Plus className="size-3.5" /> New twin
            </button>
          </div>
        }
      />

      {!live ? (
        <Panel title="Twin ingest needs the API service"
          subtitle="The console is running on the exported build snapshot">
          <ol className="space-y-2 text-[11.5px] leading-relaxed text-muted">
            <li>1. Start the service: <span className="numeric text-fg">python -m uvicorn sentinel.api.main:app --port 8000</span></li>
            <li>2. Reopen this page with the console pointed at <span className="numeric text-fg">{API_BASE}</span>.</li>
            <li>3. Register a twin, then push a sample or start auto mode.</li>
          </ol>
          <p className="mt-3 text-[11px] text-faint">
            Snapshots are read-only build artifacts, so the twin needs the live store for samples.
          </p>
        </Panel>
      ) : (
        <>
          {creating && (
            <Panel title="Register a machine" subtitle="A token is issued once for gateway ingest">
              <CreateForm
                assets={assets}
                busy={busy === 'create'}
                onCancel={() => setCreating(false)}
                onCreate={async (input) => {
                  const device = await controller.create(input)
                  if (device) setCreating(false)
                }}
              />
            </Panel>
          )}

          {error && (
            <p className="rounded-[8px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-2 text-[11px] text-muted">
              {error}
            </p>
          )}

          <div className="grid gap-4 xl:grid-cols-[270px_1fr]">
            <Panel title="Registered twins" subtitle={`${twins.length} machine${twins.length === 1 ? '' : 's'}`}
              action={<button onClick={() => void controller.refresh()} className="text-faint hover:text-fg" aria-label="Refresh twins"><RefreshCw className="size-3.5" /></button>}>
              {twins.length === 0 ? (
                <div className="space-y-2 text-[11px] leading-relaxed text-muted">
                  <p>No twin yet. Register a machine to start.</p>
                  <button onClick={() => setCreating(true)}
                    className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] hover:text-fg">
                    <Plus className="size-3.5" /> Register the first machine
                  </button>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {twins.map((entry) => (
                    <DeviceCard
                      key={entry.device.device_id}
                      entry={entry}
                      active={entry.device.device_id === selectedId}
                      onSelect={() => controller.select(entry.device.device_id)}
                    />
                  ))}
                </div>
              )}
            </Panel>

            {!snapshot ? (
              <Panel title="Select a twin" subtitle="Choose a machine on the left">
                <p className="text-[11.5px] text-muted">Twin state, history and connection details appear here.</p>
              </Panel>
            ) : (
              <div className="space-y-4">
                <Panel
                  title={snapshot.device.name}
                  subtitle={`${snapshot.device.asset_id ?? 'No baseline asset'} · ${snapshot.sample_count} samples · updated ${snapshot.device.last_seen_at ? relativeTime(snapshot.device.last_seen_at) : 'never'}`}
                  action={
                    <div className="flex items-center gap-2">
                      <Badge tone={snapshot.device.mode === 'auto' ? 'attention' : 'neutral'} dot>
                        {snapshot.device.mode === 'auto' ? (snapshot.auto.running ? 'Auto · live' : 'Auto · idle') : 'Manual'}
                      </Badge>
                      <button
                        onClick={() => {
                          if (window.confirm(`Remove twin ${snapshot.device.name} and its samples?`)) {
                            void controller.remove(snapshot.device.device_id)
                          }
                        }}
                        className="text-faint transition-colors hover:text-[var(--color-bad)]"
                        aria-label="Delete twin"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  }
                >
                  <TwinSchematic
                    readings={readings}
                    sensors={snapshot.sensors}
                    running={snapshot.auto.running}
                    assetId={snapshot.device.asset_id}
                  />

                  <div className="mt-4 grid gap-3 sm:grid-cols-[auto_1fr]">
                    <div className="flex items-center gap-4">
                      <Ring value={twin?.health_score ?? 0} label="Twin health" size={104} />
                      <div className="space-y-1.5 text-[10.5px] text-muted">
                        <div className="flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-[var(--color-accent)]" />
                          Deviation index <span className="numeric text-fg">{number(twin?.anomaly_score, 2)}</span>
                        </div>
                        <div>Severity <Badge tone={severityTone}>{twin?.severity ?? 'none'}</Badge></div>
                        <div>Coverage <span className="numeric text-fg">{twin ? `${Math.round(twin.coverage.coverage * 100)}%` : '—'}</span></div>
                        <div>Trend <span className="text-fg">{snapshot.trend.direction}</span></div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
                      <MiniStat label="Channels" value={twin ? `${twin.coverage.matched}/${twin.coverage.expected}` : '—'} />
                      <MiniStat label="Samples" value={snapshot.sample_count} />
                      <MiniStat label="Last cycle" value={snapshot.latest?.cycle ?? '—'} />
                      <MiniStat label="Model RUL" value={snapshot.model ? `${number(snapshot.model.estimate, 0)} cyc` : '—'} />
                    </div>
                  </div>
                  {twin && (
                    <p className="mt-3 text-[11px] leading-relaxed text-muted">{twin.explanation}</p>
                  )}
                  {!twin && (
                    <p className="mt-3 text-[11px] text-muted">
                      No sample yet. Enter readings below, or start auto mode to stream the bound asset's recorded cycles.
                    </p>
                  )}
                </Panel>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Panel title="Connection" subtitle="Manual and automatic ingest paths">
                    <div className="space-y-3">
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Mode</span>
                          <div className="flex overflow-hidden rounded-[7px] border border-[var(--color-line)]">
                            {(['manual', 'auto'] as const).map((mode) => (
                              <button
                                key={mode}
                                onClick={() => void controller.patch(snapshot.device.device_id, { mode })}
                                className={cx(
                                  'px-2.5 py-1 text-[10.5px] capitalize transition-colors',
                                  snapshot.device.mode === mode
                                    ? 'bg-[var(--accent-soft)] text-[var(--color-accent)]'
                                    : 'text-muted hover:bg-[var(--overlay-2)] hover:text-fg',
                                )}
                              >
                                {mode}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      <label className="block">
                        <span className="text-[10px] uppercase tracking-[0.12em] text-faint">Baseline asset</span>
                        <select
                          value={snapshot.device.asset_id ?? ''}
                          onChange={(event) => void controller.patch(snapshot.device.device_id, { asset_id: event.target.value || null })}
                          className="mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11px] text-fg"
                        >
                          <option value="">Unbound</option>
                          {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.label}</option>)}
                        </select>
                      </label>

                      {snapshot.device.mode === 'auto' ? (
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              onClick={() => void (snapshot.auto.running
                                ? controller.stop(snapshot.device.device_id)
                                : controller.start(snapshot.device.device_id))}
                              disabled={busy === 'start' || busy === 'stop' || !snapshot.device.asset_id}
                              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-2.5 py-1.5 text-[11px] text-[var(--color-accent)] disabled:opacity-40"
                            >
                              {snapshot.auto.running ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                              {snapshot.auto.running ? 'Pause feed' : 'Start feed'}
                            </button>
                            <select
                              value={snapshot.device.interval_ms}
                              onChange={(event) => void controller.patch(snapshot.device.device_id, { interval_ms: Number(event.target.value) })}
                              className="rounded-[7px] border border-[var(--color-line)] bg-[var(--color-bg-deep)] px-2 py-1.5 text-[11px] text-fg"
                            >
                              {INTERVALS.map((value) => <option key={value} value={value}>{value} ms</option>)}
                            </select>
                            <span className="text-[10.5px] text-faint">
                              {snapshot.auto.cursor ?? 0} / {snapshot.auto.total_cycles ?? '—'} cycles
                            </span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
                            <div className="h-full rounded-full bg-[var(--color-accent)]"
                              style={{ width: `${snapshot.auto.total_cycles ? Math.min(100, ((snapshot.auto.cursor ?? 0) / snapshot.auto.total_cycles) * 100) : 0}%` }} />
                          </div>
                          <p className="text-[10.5px] leading-relaxed text-faint">
                            Steps through <span className="text-muted">{snapshot.device.asset_id}</span>'s recorded trajectory and scores each cycle exactly like a pushed sample.
                            {snapshot.auto.finished ? ' Feed finished; start again to replay.' : ''}
                          </p>
                        </div>
                      ) : (
                        <p className="text-[10.5px] leading-relaxed text-faint">
                          Push readings from a gateway or fill the form below. Every accepted sample is scored against the baseline and stored.
                        </p>
                      )}
                    </div>
                  </Panel>

                  <Panel title="Gateway credentials" subtitle={`Token prefix ${snapshot.device.token_prefix}…`}>
                    <div className="space-y-2.5 text-[11px] leading-relaxed text-muted">
                      <p>
                        Send <span className="numeric text-fg">X-Device-Token</span> with every sample. The token is shown once at
                        creation or rotation; only a PBKDF2 digest is stored.
                      </p>
                      {token ? (
                        <div className="raised px-2.5 py-2">
                          <div className="text-[9.5px] uppercase tracking-[0.1em] text-faint">Device token</div>
                          <div className="mt-1 flex items-center gap-2">
                            <code className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-fg">{token}</code>
                            <CopyButton value={token} />
                          </div>
                        </div>
                      ) : (
                        <p className="text-faint">
                          The token is not in this session. Rotate it to issue a new one.
                        </p>
                      )}
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => void controller.rotate(snapshot.device.device_id)}
                          className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted hover:text-fg"
                        >
                          <ShieldCheck className="size-3.5" /> Rotate token
                        </button>
                        <span className="text-[10px] text-faint">Previous token stops working immediately.</span>
                      </div>
                    </div>
                  </Panel>
                </div>

                {snapshot.device.mode === 'manual' && (
                  <Panel title="Manual sample" subtitle="Values are scored on submit, never interpolated">
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      {snapshot.sensors.map((sensor) => (
                        <label key={sensor.key} className="block">
                          <span className="text-[9.5px] uppercase tracking-[0.08em] text-faint" title={sensor.label}>
                            {sensor.key.toUpperCase()} · {sensor.label.split(' (')[0]}
                          </span>
                          <input
                            inputMode="decimal"
                            value={values[sensor.key] ?? ''}
                            onChange={(event) => setValues((current) => ({ ...current, [sensor.key]: event.target.value }))}
                            className="numeric mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2 py-1.5 text-[11.5px] outline-none focus:border-[var(--accent-line)]"
                          />
                        </label>
                      ))}
                      <label className="block">
                        <span className="text-[9.5px] uppercase tracking-[0.08em] text-faint">Cycle (optional)</span>
                        <input
                          inputMode="numeric"
                          value={cycle}
                          onChange={(event) => setCycle(event.target.value)}
                          className="numeric mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2 py-1.5 text-[11.5px] outline-none focus:border-[var(--accent-line)]"
                        />
                      </label>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => void pushSample()}
                        disabled={busy === 'push'}
                        className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] disabled:opacity-40"
                      >
                        <Zap className="size-3.5" /> Push sample
                      </button>
                      <span className="text-[10.5px] text-faint">{notice ?? 'Only filled channels are sent.'}</span>
                    </div>
                  </Panel>
                )}

                <div className="grid gap-4 lg:grid-cols-2">
                  <Panel title="Twin health" subtitle="Every accepted sample, in order">
                    <AreaTrend data={chartData} xKey="seq" yKey="health" color="var(--chart-4)" height={180} name="Health" />
                  </Panel>
                  <Panel title="Deviation index" subtitle="Peak-weighted channel deviation">
                    <AreaTrend data={chartData} xKey="seq" yKey="anomaly" color="var(--chart-3)" height={180} name="Deviation" />
                  </Panel>
                </div>

                <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
                  <Panel title="Channel readings" subtitle="Latest sample against the healthy baseline" bodyClassName="p-0">
                    <div className="max-h-[320px] overflow-auto">
                      <table className="w-full border-collapse text-left text-[11px]">
                        <thead className="sticky top-0 bg-[var(--color-surface)]">
                          <tr className="border-b border-[var(--color-line)]">
                            {['Channel', 'Value', 'Baseline', 'Δ', 'z'].map((head) => (
                              <th key={head} className="px-3 py-2 text-[9px] font-medium uppercase tracking-[0.1em] text-faint">{head}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {readings.map((reading) => (
                            <tr key={reading.sensor} className="border-b border-[var(--color-line)] last:border-0">
                              <td className="px-3 py-1.5">
                                <span className="numeric uppercase text-fg">{reading.sensor}</span>
                              </td>
                              <td className="numeric px-3 py-1.5 text-fg">{number(reading.value, 2)}</td>
                              <td className="numeric px-3 py-1.5 text-muted">{number(reading.median, 2)}</td>
                              <td className="numeric px-3 py-1.5 text-muted">
                                {reading.deviation_pct == null ? '—' : `${reading.deviation_pct > 0 ? '+' : ''}${reading.deviation_pct.toFixed(1)}%`}
                              </td>
                              <td className={cx(
                                'numeric px-3 py-1.5',
                                Math.abs(reading.z_score) >= 3.5 ? 'text-[var(--color-critical)]'
                                  : Math.abs(reading.z_score) >= 2.5 ? 'text-[var(--color-warn)]' : 'text-muted',
                              )}>
                                {reading.z_score > 0 ? '+' : ''}{reading.z_score.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                          {readings.length === 0 && (
                            <tr><td colSpan={5} className="px-3 py-3 text-[11px] text-muted">No sample stored for this twin.</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </Panel>

                  <Panel title="Machine gateway" subtitle="Point a PLC bridge or script at this endpoint">
                    <pre className="max-h-[220px] overflow-auto rounded-[8px] border border-[var(--color-line)] bg-[var(--code-bg)] p-2.5 font-mono text-[10px] leading-relaxed text-muted">
{connection}
                    </pre>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <CopyButton value={connection} label="Copy request" />
                      <a
                        href={`${API_BASE.replace(/\/api\/v1\/?$/, '')}/docs`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[10.5px] text-[var(--color-accent)] hover:underline"
                      >
                        OpenAPI console <ArrowUpRight className="size-3" />
                      </a>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <MiniStat label="Model RUL" value={snapshot.model ? `${number(snapshot.model.estimate, 0)} cyc` : '—'} />
                      <MiniStat label="Model band" value={snapshot.model ? `${number(snapshot.model.lower, 0)}–${number(snapshot.model.upper, 0)}` : '—'} />
                      <MiniStat label="Baseline cycles" value={snapshot.baseline?.cycles ?? '—'} />
                      <MiniStat label="Health trend" value={snapshot.trend.direction} />
                    </div>
                    <p className="mt-2 text-[10px] leading-relaxed text-faint">
                      {snapshot.model?.note ?? 'Bind a fleet asset to attach a model estimate.'}
                    </p>
                  </Panel>
                </div>

                <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-faint">
                  <span className="inline-flex items-center gap-1"><Gauge className="size-3" /> Health is baseline-relative arithmetic, not a model output.</span>
                  <span className="inline-flex items-center gap-1"><Activity className="size-3" /> Deviation index = 0.65 peak + 0.35 median |z|.</span>
                  <span className="inline-flex items-center gap-1"><Wifi className="size-3" /> Ingest over TLS in production.</span>
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
