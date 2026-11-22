import { Check, Database, KeyRound, Lock, Palette, ShieldCheck, SlidersHorizontal, Terminal } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { API_BASE, setApiKey, storedApiKey } from '../lib/api'
import { cx } from '../lib/cx'
import { useData } from '../lib/data-context'
import { money, number, percent, relativeTime } from '../lib/format'
import { useTheme } from '../lib/theme'

export function SettingsPage() {
  const { data, source, error } = useData()
  const settings = data.settings
  const { theme, setTheme, themes } = useTheme()
  const [keyDraft, setKeyDraft] = useState(storedApiKey() ?? '')
  const [keySaved, setKeySaved] = useState(Boolean(storedApiKey()))

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Platform · Configuration"
        title="System settings"
        description="Runtime configuration, decision-model assumptions and platform limits. Values here are the ones used by the build that produced the current data."
        actions={<Badge tone={source === 'live' ? 'healthy' : 'medium'}>{source === 'live' ? 'Live API' : 'Artifact snapshot'}</Badge>}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Appearance" subtitle="Five palettes, applied instantly and remembered on this device"
          action={<Palette className="size-4 text-faint" />}>
          <div className="grid gap-2 sm:grid-cols-2">
            {themes.map((entry) => (
              <button
                key={entry.id}
                onClick={() => setTheme(entry.id)}
                className={cx(
                  'flex items-start gap-2.5 rounded-[8px] border px-2.5 py-2 text-left transition-colors',
                  entry.id === theme
                    ? 'border-[var(--accent-line)] bg-[var(--accent-soft)]'
                    : 'border-[var(--color-line)] bg-[var(--overlay-1)] hover:border-[var(--color-line-strong)]',
                )}
              >
                <span className="mt-0.5 flex shrink-0">
                  {entry.swatch.map((color) => (
                    <span key={color} className="-ml-1 size-3.5 rounded-full border border-[var(--color-line)] first:ml-0"
                      style={{ background: color }} />
                  ))}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11.5px] text-fg">{entry.name}</span>
                  <span className="block text-[10px] leading-snug text-faint">{entry.description}</span>
                </span>
                {entry.id === theme && <Check className="mt-0.5 size-3.5 shrink-0 text-[var(--color-accent)]" />}
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Access control" subtitle="Session-only API key for mutating routes"
          action={<KeyRound className="size-4 text-faint" />}>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setApiKey(keyDraft)
              setKeySaved(Boolean(keyDraft.trim()))
            }}
            className="space-y-2"
          >
            <label className="block">
              <span className="text-[10px] uppercase tracking-[0.12em] text-faint">SENTINEL_API_KEY</span>
              <input
                type="password"
                autoComplete="off"
                value={keyDraft}
                onChange={(event) => setKeyDraft(event.target.value)}
                placeholder="Paste the operator key"
                className="numeric mt-1 w-full rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-1.5 text-[11.5px] outline-none focus:border-[var(--accent-line)]"
              />
            </label>
            <div className="flex items-center gap-2">
              <button type="submit"
                className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-2.5 py-1.5 text-[11px] text-[var(--color-accent)]">
                <Lock className="size-3.5" /> Save for this session
              </button>
              <button type="button"
                onClick={() => { setKeyDraft(''); setApiKey(null); setKeySaved(false) }}
                className="text-[11px] text-faint hover:text-fg">Clear</button>
              <Badge tone={keySaved ? 'healthy' : 'neutral'} dot>{keySaved ? 'Key set' : 'No key'}</Badge>
            </div>
          </form>
          <div className="mt-3 space-y-1.5 text-[10.5px] leading-relaxed text-muted">
            <p>The key stays in <span className="numeric text-fg">sessionStorage</span>, is sent only as <span className="numeric text-fg">X-API-Key</span>, and is cleared when the tab closes. It is never written into a build or bundle.</p>
            <p>Device telemetry uses a separate per-device token; the server stores only its PBKDF2 digest.</p>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Runtime" subtitle="Build artifact identity"
          action={<Terminal className="size-4 text-faint" />}>
          <div className="space-y-1.5 text-[11px]">
            {[
              ['Product', `${data.meta.product} ${data.meta.build_version}`],
              ['Generated', `${relativeTime(data.meta.generated_at)} (${data.meta.generated_at.slice(0, 19)}Z)`],
              ['Pipeline', data.meta.pipeline],
              ['Build duration', `${number(data.meta.duration_seconds, 1)} s`],
              ['Feature specifications', number(data.meta.feature_specs, 0)],
              ['Python', data.meta.runtime.python],
              ['Platform', data.meta.runtime.platform],
              ['API base', API_BASE],
              ['API status', source === 'live' ? 'reachable' : `unreachable (${error ?? 'no response'})`],
            ].map(([label, value]) => (
              <div key={label} className="flex items-start justify-between gap-4 border-b border-[var(--color-line)] pb-1.5 last:border-0">
                <span className="shrink-0 text-faint">{label}</span>
                <span className="text-right text-muted break-all">{value}</span>
              </div>
            ))}
          </div>
          <div className="mt-3">
            <Note>
              The UI loads the FastAPI service when reachable and otherwise reads the snapshot
              produced by <span className="numeric">python -m sentinel.pipelines.build</span>. The
              indicator in the top bar always shows which source is active.
            </Note>
          </div>
        </Panel>

        <Panel title="Health scoring model" subtitle={settings.health.method}
          action={<SlidersHorizontal className="size-4 text-faint" />}>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(settings.health.weights).map(([key, value]) => (
              <div key={key} className="raised px-2.5 py-2">
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-faint">{key}</div>
                <div className="numeric mt-0.5 text-[13px]">{percent(value, 0)}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(settings.health.bands).map(([band, floor]) => (
              <Badge key={band} tone={band as 'healthy'}>
                {band} ≥ {number(floor, 0)}
              </Badge>
            ))}
          </div>
          <ul className="mt-3 space-y-1.5 text-[10.5px] leading-relaxed text-muted">
            {settings.health.limitations.map((limitation) => (
              <li key={limitation}>· {limitation}</li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <Panel title="Cost model" subtitle="Assumptions used by threshold tuning and maintenance optimisation" bodyClassName="p-0">
          <Table head={['Parameter', 'Value', 'Used for']}>
            <Row><Cell className="text-fg">False negative</Cell><Cell className="numeric">{money(settings.costs.false_negative_cost)}</Cell><Cell className="text-muted">missed failure</Cell></Row>
            <Row><Cell className="text-fg">False positive</Cell><Cell className="numeric">{money(settings.costs.false_positive_cost)}</Cell><Cell className="text-muted">unnecessary inspection</Cell></Row>
            <Row><Cell className="text-fg">Planned maintenance</Cell><Cell className="numeric">{money(settings.costs.planned_maintenance_cost)}</Cell><Cell className="text-muted">scheduled service</Cell></Row>
            <Row><Cell className="text-fg">Unplanned failure</Cell><Cell className="numeric">{money(settings.costs.unplanned_failure_cost)}</Cell><Cell className="text-muted">reactive failure</Cell></Row>
            <Row><Cell className="text-fg">Downtime / hour</Cell><Cell className="numeric">{money(settings.costs.downtime_cost_per_hour)}</Cell><Cell className="text-muted">scenario downtime</Cell></Row>
            <Row><Cell className="text-fg">Planned downtime</Cell><Cell className="numeric">{number(settings.costs.planned_downtime_hours, 1)} h</Cell><Cell className="text-muted">service window</Cell></Row>
            <Row><Cell className="text-fg">Unplanned downtime</Cell><Cell className="numeric">{number(settings.costs.unplanned_downtime_hours, 1)} h</Cell><Cell className="text-muted">failure window</Cell></Row>
          </Table>
        </Panel>

        <Panel title="Model and data thresholds" subtitle="Recorded in the build artifact" bodyClassName="p-0">
          <Table head={['Setting', 'Value']}>
            <Row><Cell className="text-muted">Failure probability threshold</Cell><Cell className="numeric">{number(settings.failure_threshold, 2)}</Cell></Row>
            <Row><Cell className="text-muted">RUL target clip</Cell><Cell className="numeric">{settings.rul_clip} cycles</Cell></Row>
            <Row><Cell className="text-muted">Risk horizons</Cell><Cell className="numeric">{settings.horizons.join(' / ')} cycles</Cell></Row>
            <Row><Cell className="text-muted">Rolling windows</Cell><Cell className="numeric">{settings.rolling_windows.join(' / ')}</Cell></Row>
            <Row><Cell className="text-muted">Maintenance budget</Cell><Cell className="numeric">{money(settings.budget)}</Cell></Row>
            <Row><Cell className="text-muted">C-MAPSS subset</Cell><Cell className="numeric">{settings.cmapss_subset}</Cell></Row>
            <Row><Cell className="text-muted">RUL model</Cell><Cell className="text-muted">{data.models.find((m) => m.name === 'cmapss_rul')?.algorithm}</Cell></Row>
            <Row><Cell className="text-muted">Classifier</Cell><Cell className="text-muted">{data.models.find((m) => m.name === 'ai4i_failure_classifier')?.algorithm}</Cell></Row>
          </Table>
        </Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Panel title="Datasets" subtitle="Versioned and validated at build time">
          <div className="flex items-center gap-2">
            <Database className="size-4 text-faint" />
            <span className="text-[11px] text-muted">{Object.keys(data.meta.dataset_versions).length} integrations</span>
          </div>
          <div className="mt-2 space-y-1.5 text-[10.5px]">
            {Object.entries(data.meta.dataset_versions).map(([name, version]) => (
              <div key={name} className="flex justify-between">
                <span className="uppercase text-muted">{name}</span>
                <span className="numeric text-faint">{version.version} · Q{version.quality_score}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Security posture" subtitle="Local-first, no committed secrets">
          <ul className="space-y-1.5 text-[10.5px] leading-relaxed text-muted">
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Mutating routes require X-API-Key once SENTINEL_API_KEY is configured; SENTINEL_REQUIRE_API_KEY fails closed.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Device ingest needs a per-device token, stored only as a PBKDF2 digest with constant-time comparison.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Security headers, 8 MB body cap, per-client rate limit and 25 samples/second/device ingest throttle.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> CORS is limited to the console origins and its actual verbs.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Uploads size-limited and schema-validated; dataset and model binaries are git-ignored.</li>
          </ul>
        </Panel>

        <Panel title="Known limitations" subtitle="Explicit, not hidden">
          <ul className="space-y-1.5 text-[10.5px] leading-relaxed text-muted">
            <li>· Deep learning modules and MLflow are not installed in this environment.</li>
            <li>· Metadata store is SQLite locally; PostgreSQL via SENTINEL_DATABASE_URL.</li>
            <li>· Bundled fleet telemetry is recorded C-MAPSS data; twin ingest accepts samples from a real gateway.</li>
            <li>· Twin health is baseline-relative arithmetic over ingested channels, not a physics simulation.</li>
            <li>· Health and cost models are documented engineering assumptions.</li>
            <li>· Snapshot bundle reflects build {data.meta.build_version}.</li>
          </ul>
        </Panel>
      </div>
    </div>
  )
}
