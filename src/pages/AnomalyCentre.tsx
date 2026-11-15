import { AlertTriangle, ScanLine } from 'lucide-react'

import { BarsChart } from '../components/charts/Charts'
import { Badge, Label } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number } from '../lib/format'
import { navigate } from '../lib/router'

export function AnomalyCentre() {
  const { data } = useData()
  const centre = data.anomalies
  const histogram = centre.score_histogram.counts.map((count, index) => ({
    score: ((centre.score_histogram.edges[index] + centre.score_histogram.edges[index + 1]) / 2).toFixed(1),
    rows: count,
  }))

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Anomaly"
        title="Anomaly detection centre"
        description={centre.summary.ensemble}
        actions={<Badge tone="neutral">{number(centre.scored_rows, 0)} scored cycles</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {(['normal', 'low', 'medium', 'high', 'critical'] as const).map((severity) => (
          <Stat
            key={severity}
            label={severity}
            value={centre.severity_distribution[severity] ?? 0}
            tone={severity === 'critical' || severity === 'high' ? 'bad' : severity === 'medium' ? 'warn' : 'default'}
            icon={<ScanLine className="size-4" />}
            hint={
              centre.summary.thresholds[severity] !== undefined
                ? `score ≥ ${number(centre.summary.thresholds[severity], 2)}`
                : 'highest band'
            }
          />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="Score distribution" subtitle="Ensemble score across every scored cycle (clipped at 5)">
          <BarsChart data={histogram} xKey="score" yKey="rows" height={220} color="#35d6f2" />
        </Panel>

        <Panel title="Most affected sensors" subtitle="How often each channel is among an asset's top deviations">
          <div className="space-y-2.5">
            {centre.affected_sensors.map((entry) => {
              const max = centre.affected_sensors[0]?.assets || 1
              return (
                <div key={entry.sensor}>
                  <div className="mb-1 flex items-center justify-between text-[11px]">
                    <span className="truncate text-muted">{entry.sensor}</span>
                    <span className="numeric text-fg">{entry.assets}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                    <div className="h-full rounded-full bg-[var(--color-warn)]"
                      style={{ width: `${Math.max(3, (entry.assets / max) * 100)}%` }} />
                  </div>
                </div>
              )
            })}
            {centre.affected_sensors.length === 0 && <p className="text-[11px] text-muted">No attributed anomalies.</p>}
          </div>
          <div className="mt-4 border-t border-[var(--color-line)] pt-3 text-[11px] text-muted">
            <div className="flex justify-between"><span>Detectors fitted on</span>
              <span className="numeric">{number(centre.summary.fit_rows, 0)} healthy rows</span></div>
            <div className="mt-1 flex justify-between"><span>Healthy mean score</span>
              <span className="numeric">{number(centre.summary.healthy_score_mean, 2)}</span></div>
          </div>
        </Panel>
      </div>

      <Panel title="Recent anomaly alerts" subtitle="Generated from the latest scored cycle per asset" bodyClassName="p-0">
        <Table head={['Asset', 'Severity', 'Score', 'Cycle', 'Signal', 'Affected channels', '']}>
          {centre.recent.map((alert, index) => (
            <Row key={`${alert.asset_id}-${index}`} onClick={() => navigate(`/assets/${alert.asset_id}`)}>
              <Cell className="text-fg">{alert.label}</Cell>
              <Cell><Badge tone={alert.severity}>{alert.severity}</Badge></Cell>
              <Cell className="numeric">{number(alert.score, 2)}</Cell>
              <Cell className="numeric text-muted">{alert.cycle}</Cell>
              <Cell className="max-w-[420px] truncate whitespace-normal text-muted">{alert.message}</Cell>
              <Cell className="text-faint">{alert.sensors.join(' · ') || '—'}</Cell>
              <Cell><AlertTriangle className="size-3.5 text-faint" /></Cell>
            </Row>
          ))}
          {centre.recent.length === 0 && (
            <Row><Cell className="text-muted">No high-severity anomaly alerts in this build.</Cell></Row>
          )}
        </Table>
      </Panel>

      <Panel title="Severity calibration" subtitle="Percentile cuts of the healthy score distribution">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2 text-[11px]">
            {Object.entries(centre.summary.thresholds).map(([band, threshold]) => (
              <div key={band} className="flex items-center justify-between rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5">
                <span className="capitalize text-muted">{band}</span>
                <span className="numeric text-fg">{number(threshold, 2)}</span>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {centre.summary.limitations.map((limitation) => (
              <Note key={limitation}>{limitation}</Note>
            ))}
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Label>Method</Label>
          <span className="text-[11px] text-muted">
            IsolationForest (full feature set) · LOF (compact degradation subset) · PCA reconstruction error,
            each normalised to its healthy p99 and averaged.
          </span>
        </div>
      </Panel>
    </div>
  )
}
