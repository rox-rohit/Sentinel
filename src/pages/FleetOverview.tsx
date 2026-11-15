import { Activity, AlertTriangle, ArrowUpRight, Bell, Gauge, ShieldCheck, Wrench } from 'lucide-react'

import { Badge, Label } from '../components/ui/Badge'
import { HealthMeter } from '../components/ui/Meter'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import type { HealthCategory } from '../data/types'
import { useData } from '../lib/data-context'
import { money, number, percent, relativeTime } from '../lib/format'
import { navigate } from '../lib/router'

const CATEGORY_COLOR: Record<HealthCategory, string> = {
  healthy: 'var(--color-good)',
  attention: 'var(--color-accent)',
  warning: 'var(--color-warn)',
  critical: 'var(--color-critical)',
}

export function FleetOverview() {
  const { data, source } = useData()
  const { summary, health_distribution, risk_distribution, data_source } = data.fleet
  const top = data.predictive.highest_risk
  const alerts = data.alerts.slice(0, 7)
  const model = data.models.find((entry) => entry.name === 'cmapss_rul')
  const classifier = data.models.find((entry) => entry.name === 'ai4i_failure_classifier')

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Fleet"
        title="Fleet health overview"
        description={
          <>
            {data_source}. {source === 'live' ? 'Live inference service' : 'Exported build artifacts'} ·{' '}
            {relativeTime(data.meta.generated_at)} · pipeline {data.meta.pipeline}
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="neutral" dot>{data.settings.cmapss_subset} fleet</Badge>
            <Badge tone={summary.critical > 0 ? 'critical' : 'healthy'}>
              {summary.critical} critical
            </Badge>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Monitored assets" value={summary.total} icon={<ShieldCheck className="size-4" />}
          hint={`${summary.healthy} healthy · ${summary.attention} attention`} />
        <Stat label="Fleet health" value={number(summary.avg_health)} unit="/ 100"
          icon={<Gauge className="size-4" />} tone="accent"
          hint={`${summary.warning} warning · ${summary.critical} critical`} />
        <Stat label="Failures ≤ 30 cycles" value={summary.predicted_failures_30}
          icon={<AlertTriangle className="size-4" />}
          tone={summary.predicted_failures_30 > 0 ? 'bad' : 'good'}
          hint={`${summary.predicted_failures_10} within 10 cycles`} />
        <Stat label="Active anomalies" value={summary.active_anomalies}
          icon={<Activity className="size-4" />} tone="warn"
          hint="High or critical severity" />
        <Stat label="Maintenance queue" value={summary.maintenance_actions}
          icon={<Wrench className="size-4" />}
          hint={`${money(summary.planned_spend)} of ${money(summary.budget)} budget`} />
        <Stat label="Mean RUL" value={number(summary.avg_rul)} unit="cycles"
          icon={<Bell className="size-4" />}
          hint={`${summary.deferred} assets deferred to monitoring`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr]">
        <Panel
          title="Fleet health matrix"
          subtitle="Every unit in the held-out C-MAPSS test fleet · click to open the asset twin"
          action={<span className="text-[10px] uppercase tracking-[0.1em] text-faint">Health score</span>}
          bodyClassName="p-3"
        >
          <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-10">
            {[...data.assets]
              .sort((a, b) => a.health_score - b.health_score)
              .map((asset) => (
                <button
                  key={asset.id}
                  onClick={() => navigate(`/assets/${asset.id}`)}
                  title={`${asset.label} · health ${asset.health_score} · RUL ${asset.rul.estimate} cycles`}
                  className="group relative aspect-square overflow-hidden rounded-[5px] border border-white/[0.06]"
                  style={{ background: `${CATEGORY_COLOR[asset.status]}1f` }}
                >
                  <span
                    className="absolute inset-x-0 bottom-0"
                    style={{
                      height: `${Math.max(8, asset.health_score)}%`,
                      background: `${CATEGORY_COLOR[asset.status]}38`,
                    }}
                  />
                  <span className="relative z-10 flex h-full items-center justify-center">
                    <span className="numeric text-[9.5px] text-fg/80 group-hover:text-fg">
                      {asset.asset_id}
                    </span>
                  </span>
                </button>
              ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
            {health_distribution.map((entry) => (
              <span key={entry.category} className="inline-flex items-center gap-1.5">
                <span className="size-1.5 rounded-full" style={{ background: CATEGORY_COLOR[entry.category] }} />
                {entry.category} <span className="numeric text-fg">{entry.count}</span>
              </span>
            ))}
            <span className="ml-auto text-faint">colour = health band · fill = score</span>
          </div>
        </Panel>

        <div className="grid gap-4">
          <Panel title="Health distribution" subtitle="Weighted RUL · risk · anomaly · trend">
            <div className="space-y-3">
              {health_distribution.map((entry) => {
                const share = summary.total ? (entry.count / summary.total) * 100 : 0
                return (
                  <div key={entry.category}>
                    <div className="mb-1 flex items-center justify-between text-[11px]">
                      <span className="capitalize text-muted">{entry.category}</span>
                      <span className="numeric text-fg">{entry.count} <span className="text-faint">({share.toFixed(0)}%)</span></span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                      <div className="h-full rounded-full" style={{
                        width: `${Math.max(1, share)}%`,
                        background: CATEGORY_COLOR[entry.category],
                      }} />
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="mt-4 space-y-2 border-t border-[var(--color-line)] pt-3">
              <Label>Risk within 30 cycles</Label>
              {risk_distribution.map((band) => (
                <div key={band.band} className="flex items-center justify-between text-[11px]">
                  <span className="text-muted">{band.band}</span>
                  <span className="numeric text-fg">{band.count}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Model status" subtitle="Registered artifacts backing this view">
            <div className="space-y-3 text-[11px]">
              {model && (
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-fg">RUL · {model.algorithm}</div>
                    <div className="text-faint">{model.version} · {model.status}</div>
                  </div>
                  <div className="text-right">
                    <div className="numeric text-fg">
                      MAE {number((model.metrics.official_test as Record<string, number>).mae)}
                    </div>
                    <div className="text-faint">official test</div>
                  </div>
                </div>
              )}
              {classifier && (
                <div className="flex items-center justify-between gap-2 border-t border-[var(--color-line)] pt-3">
                  <div>
                    <div className="text-fg">Failure · {classifier.algorithm}</div>
                    <div className="text-faint">AI4I · held-out 25%</div>
                  </div>
                  <div className="text-right">
                    <div className="numeric text-fg">
                      PR-AUC {number((classifier.metrics.test as Record<string, number>).pr_auc, 3)}
                    </div>
                    <div className="text-faint">
                      recall {percent((classifier.metrics.test as Record<string, number>).recall)}
                    </div>
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between border-t border-[var(--color-line)] pt-3 text-faint">
                <span>Drift status</span>
                <Badge tone={data.drift.overall_status === 'stable' ? 'healthy' : 'medium'}>
                  {data.drift.overall_status}
                </Badge>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.25fr]">
        <Panel
          title="Recent alerts"
          subtitle="Generated by the anomaly ensemble and horizon risk model"
          action={<Badge tone="neutral">{alerts.length} shown</Badge>}
          bodyClassName="p-0"
        >
          <ul className="divide-y divide-[var(--color-line)]">
            {alerts.length === 0 && <li className="px-4 py-6 text-[12px] text-muted">No active alerts.</li>}
            {alerts.map((alert, index) => (
              <li key={`${alert.asset_id}-${alert.kind}-${index}`} className="flex gap-3 px-4 py-2.5">
                <span className="mt-1 size-1.5 shrink-0 rounded-full"
                  style={{ background: alert.severity === 'critical' ? 'var(--color-critical)' : 'var(--color-warn)' }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <button className="text-[11.5px] text-fg hover:text-[var(--color-accent)]"
                      onClick={() => navigate(`/assets/${alert.asset_id}`)}>
                      {alert.label}
                    </button>
                    <Badge tone={alert.severity}>{alert.severity}</Badge>
                    <span className="ml-auto shrink-0 text-[10px] text-faint">cycle {alert.cycle}</span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted">{alert.message}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title="Highest predicted risk"
          subtitle="P(RUL ≤ 30 cycles) from the residual distribution"
          action={
            <button className="inline-flex items-center gap-1 text-[11px] text-muted hover:text-fg"
              onClick={() => navigate('/predictive')}>
              Predictive analytics <ArrowUpRight className="size-3" />
            </button>
          }
          bodyClassName="p-0"
        >
          <Table head={['Asset', 'Health', 'RUL', 'Risk 30', 'Risk 50', 'State']}>
            {top.map((asset) => (
              <Row key={asset.id} onClick={() => navigate(`/assets/${asset.id}`)}>
                <Cell className="text-fg">{asset.label}</Cell>
                <Cell className="w-28">
                  <div className="flex items-center gap-2">
                    <HealthMeter value={asset.health} className="w-14" />
                    <span className="numeric text-[11px] text-muted">{number(asset.health, 0)}</span>
                  </div>
                </Cell>
                <Cell className="numeric">{number(asset.rul, 0)}</Cell>
                <Cell className="numeric">{percent(asset.risk_30)}</Cell>
                <Cell className="numeric text-muted">{percent(asset.risk_50)}</Cell>
                <Cell><Badge tone={asset.status}>{asset.status}</Badge></Cell>
              </Row>
            ))}
          </Table>
        </Panel>
      </div>

      <Note>
        Fleet values are computed from held-out C-MAPSS test trajectories. Health is a weighted
        decision score, not a validated physical measurement; RUL intervals come from the model's
        residual distribution (MAE {number(data.rul.benchmark.official.mae)} cycles on the official test set).
        No real-time sensor connection exists — this is recorded telemetry.
      </Note>
    </div>
  )
}
