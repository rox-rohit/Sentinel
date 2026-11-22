import { useState } from 'react'

import { BarsChart, TelemetryChart } from '../components/charts/Charts'
import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'

const CURVE_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)']

export function HistoricalAnalytics() {
  const { data } = useData()
  const [dataset, setDataset] = useState<'cmapss' | 'ai4i'>('cmapss')
  const eda = data.eda[dataset]

  const degradation = eda.degradation ?? []
  const series = degradation.slice(0, 3).map((curve, index) => ({
    key: curve.sensor,
    color: CURVE_COLORS[index % CURVE_COLORS.length],
    label: curve.sensor.toUpperCase(),
  }))
  const curveData = (degradation[0]?.life_fraction ?? []).map((fraction, fractionIndex) => {
    const point: Record<string, number | string> = { life: Number((fraction * 100).toFixed(0)) }
    for (const curve of degradation.slice(0, 3)) {
      point[curve.sensor] = curve.mean_value[fractionIndex]
    }
    return point
  })
  const machines = (eda.machine_comparison ?? []).slice(0, 14)

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Intelligence · History"
        title="Historical analytics"
        description="Dataset-derived statistics: distribution shape, sensor correlation structure, degradation trajectories and unit-to-unit comparison."
        actions={
          <div className="flex gap-1 rounded-[7px] border border-[var(--color-line)] p-0.5">
            {(['cmapss', 'ai4i'] as const).map((option) => (
              <button key={option} onClick={() => setDataset(option)}
                className={`rounded-[5px] px-2.5 py-1 text-[10.5px] uppercase ${
                  dataset === option ? 'bg-[var(--accent-soft)] text-[var(--color-accent)]' : 'text-faint hover:text-fg'
                }`}>
                {option}
              </button>
            ))}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="panel px-4 py-3">
          <div className="text-[9.5px] uppercase tracking-[0.12em] text-faint">Rows analysed</div>
          <div className="numeric mt-1 text-[20px]">{number(eda.rows, 0)}</div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-[9.5px] uppercase tracking-[0.12em] text-faint">Channels</div>
          <div className="numeric mt-1 text-[20px]">{eda.columns}</div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-[9.5px] uppercase tracking-[0.12em] text-faint">
            {dataset === 'cmapss' ? 'Units' : 'Failure rate'}
          </div>
          <div className="numeric mt-1 text-[20px]">
            {dataset === 'cmapss'
              ? (eda.fleet_size ?? '—')
              : percent(eda.failure_balance?.overall.rate, 2)}
          </div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-[9.5px] uppercase tracking-[0.12em] text-faint">Strongest |r|</div>
          <div className="numeric mt-1 text-[20px]">
            {number(eda.top_correlations[0]?.abs_correlation, 3)}
          </div>
        </div>
      </div>

      {degradation.length > 0 && (
        <Panel title="Sensor degradation trajectories" subtitle="Mean value by normalised life fraction across all units">
          <TelemetryChart data={curveData} xKey="life" series={series} height={250} />
          <div className="mt-1 flex items-center gap-4 text-[10px] text-faint">
            <span>x = % of recorded life</span>
            {series.map((item) => (
              <span key={item.key} className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4" style={{ background: item.color }} /> {item.label}
              </span>
            ))}
          </div>
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {dataset === 'cmapss' && machines.length > 0 && (
          <Panel title="Unit-to-unit comparison" subtitle={`Latest ${eda.descriptive[0]?.column ?? 'sensor'} reading per unit`}>
            <BarsChart
              data={machines.map((machine) => ({ unit: machine.unit, value: machine.latest }))}
              xKey="unit"
              yKey="value"
              height={230}
              color="var(--chart-2)"
            />
          </Panel>
        )}

        <Panel title="Distribution shape" subtitle="Skewness and missingness per channel" bodyClassName="p-0">
          <Table head={['Channel', 'Mean', 'Skew', 'Missing %', 'Range']}>
            {eda.descriptive.map((row) => (
              <Row key={row.column}>
                <Cell className="text-fg">{row.column}</Cell>
                <Cell className="numeric">{number(row.mean, 2)}</Cell>
                <Cell className={`numeric ${Math.abs(row.skew) > 1.5 ? 'text-[var(--color-warn)]' : 'text-muted'}`}>
                  {number(row.skew, 2)}
                </Cell>
                <Cell className="numeric text-muted">{percent(row.missing / Math.max(1, eda.rows), 2)}</Cell>
                <Cell className="numeric text-faint">{number(row.min, 1)} – {number(row.max, 1)}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Panel title="Top correlated pairs" subtitle="Pearson |r| — redundancy and co-degradation" bodyClassName="p-0">
          <Table head={['Channel A', 'Channel B', '|r|', 'Interpretation']}>
            {eda.top_correlations.map((row) => (
              <Row key={`${row.a}-${row.b}`}>
                <Cell className="text-muted">{row.a}</Cell>
                <Cell className="text-muted">{row.b}</Cell>
                <Cell className="numeric">{number(row.abs_correlation, 3)}</Cell>
                <Cell className="text-faint">
                  {row.abs_correlation > 0.9 ? 'near-duplicate signal' : row.abs_correlation > 0.7 ? 'strong co-movement' : 'moderate'}
                </Cell>
              </Row>
            ))}
          </Table>
        </Panel>

        <Panel title="EDA notes" subtitle="Generated from the processed dataset">
          <ul className="space-y-2 text-[11px] leading-relaxed text-muted">
            {eda.notes.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
                {note}
              </li>
            ))}
          </ul>
          {eda.failure_balance && (
            <div className="mt-3 border-t border-[var(--color-line)] pt-3">
              <div className="mb-2 flex items-center gap-2">
                <Badge tone="medium">imbalanced</Badge>
                <span className="text-[10.5px] text-muted">
                  {eda.failure_balance.overall.positives} failures in {number(eda.failure_balance.overall.rows, 0)} records
                </span>
              </div>
              {eda.failure_balance.modes.map((mode) => (
                <div key={mode.column} className="flex items-center justify-between py-0.5 text-[10.5px]">
                  <span className="text-muted">{mode.label}</span>
                  <span className="numeric">{mode.count} · {percent(mode.rate, 2)}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Note>
        Statistics are recomputed from the canonical dataset on every build; there are no cached or
        hardcoded charts. Correlation indicates redundancy and co-movement, not causation.
      </Note>
    </div>
  )
}
