import { Database, ShieldCheck, SlidersHorizontal, Terminal } from 'lucide-react'

import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { API_BASE, SNAPSHOT } from '../lib/api'
import { useData } from '../lib/data-context'
import { money, number, percent, relativeTime } from '../lib/format'

export function SettingsPage() {
  const { data, source, error } = useData()
  const settings = data.settings

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Platform · Configuration"
        title="System settings"
        description="Runtime configuration, decision-model assumptions and platform limits. Values here are the ones used by the build that produced the current data."
        actions={<Badge tone={source === 'live' ? 'healthy' : 'medium'}>{source === 'live' ? 'Live API' : 'Artifact snapshot'}</Badge>}
      />

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
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> API keys read from environment only; mutating routes accept an optional X-API-Key.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> CORS limited to local UI origins.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Uploads size-limited and schema-validated before storage.</li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3 shrink-0 text-[var(--color-good)]" /> Dataset and model binaries are git-ignored.</li>
          </ul>
        </Panel>

        <Panel title="Known limitations" subtitle="Explicit, not hidden">
          <ul className="space-y-1.5 text-[10.5px] leading-relaxed text-muted">
            <li>· Deep learning modules and MLflow are not installed in this environment.</li>
            <li>· Metadata store is SQLite locally; PostgreSQL via SENTINEL_DATABASE_URL.</li>
            <li>· Telemetry is recorded C-MAPSS data; no live sensor or MQTT connection exists.</li>
            <li>· Health and cost models are documented engineering assumptions.</li>
            <li>· Snapshot bundle reflects the last build ({SNAPSHOT.meta.build_version}).</li>
          </ul>
        </Panel>
      </div>
    </div>
  )
}
