import { Badge } from '../components/ui/Badge'
import { BarsChart } from '../components/charts/Charts'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'
import { navigate } from '../lib/router'

export function PredictiveAnalytics() {
  const { data } = useData()
  const predictive = data.predictive
  const risks = predictive.highest_risk

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Prediction"
        title="Predictive analytics"
        description={`Failure horizon risk from the ${predictive.model} RUL model, with the empirical residual distribution as the uncertainty source.`}
        actions={<Badge tone="neutral">{predictive.method}</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Assets in fleet" value={data.fleet.summary.total} hint="Held-out test trajectories" />
        <Stat label="Risk ≥ 50% @ 30 cycles" value={data.fleet.summary.predicted_failures_30}
          tone="bad" hint={`${data.fleet.summary.predicted_failures_10} within 10 cycles`} />
        <Stat label="Mean predicted RUL" value={number(data.fleet.summary.avg_rul, 0)} unit="cycles"
          tone="accent" hint="Across the current fleet snapshot" />
        <Stat label="Mean 80% interval width" value={number(predictive.confidence.mean_interval_width, 0)}
          unit="cycles" hint="Residual p10–p90 band" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Predicted failures by horizon" subtitle="Assets whose P(RUL ≤ horizon) exceeds 50%">
          <BarsChart
            data={predictive.horizon_curve.map((entry) => ({
              horizon: `≤${entry.horizon} cyc`,
              high_risk: entry.high_risk,
            }))}
            xKey="horizon"
            yKey="high_risk"
            height={230}
            color="#f5a524"
          />
          <div className="mt-2 grid grid-cols-4 gap-2 text-center">
            {predictive.horizon_curve.map((entry) => (
              <div key={entry.horizon} className="raised px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-[0.08em] text-faint">≤{entry.horizon} cyc</div>
                <div className="numeric mt-0.5 text-[11px] text-fg">mean {percent(entry.mean_risk, 1)}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Risk distribution" subtitle="P(RUL ≤ 30 cycles) per asset">
          <div className="space-y-3">
            {predictive.risk_distribution.map((band) => {
              const total = data.fleet.summary.total || 1
              return (
                <div key={band.band}>
                  <div className="mb-1 flex items-center justify-between text-[11px]">
                    <span className="text-muted">{band.band}</span>
                    <span className="numeric text-fg">{band.count}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                    <div className="h-full rounded-full bg-[var(--color-accent)]"
                      style={{ width: `${Math.max(1, (band.count / total) * 100)}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-4 border-t border-[var(--color-line)] pt-3 text-[11px] text-muted">
            <div className="flex justify-between"><span>Median residual</span>
              <span className="numeric">{number(Number(predictive.confidence.residual_quantiles.p50), 1)} cyc</span></div>
            <div className="mt-1 flex justify-between"><span>Residual p10 / p90</span>
              <span className="numeric">
                {number(Number(predictive.confidence.residual_quantiles.p10), 1)} / {number(Number(predictive.confidence.residual_quantiles.p90), 1)}
              </span></div>
            <div className="mt-1 flex justify-between"><span>Residual sample</span>
              <span className="numeric">{String(predictive.confidence.residual_quantiles.count)} rows</span></div>
          </div>
        </Panel>
      </div>

      <Panel title="Highest-risk assets" subtitle="Ranked by 30-cycle failure risk" bodyClassName="p-0">
        <Table head={['Asset', 'RUL estimate', 'Band', 'Risk ≤10', 'Risk ≤30', 'Risk ≤50', 'State']}>
          {risks.map((asset) => (
            <Row key={asset.id} onClick={() => navigate(`/assets/${asset.id}`)}>
              <Cell className="text-fg">{asset.label}</Cell>
              <Cell className="numeric">{number(asset.rul, 0)} cyc</Cell>
              <Cell className="numeric text-muted">{number(asset.lower, 0)}–{number(asset.upper, 0)}</Cell>
              <Cell className="numeric">{percent(asset.risk_10)}</Cell>
              <Cell className="numeric">{percent(asset.risk_30)}</Cell>
              <Cell className="numeric">{percent(asset.risk_50)}</Cell>
              <Cell><Badge tone={asset.status}>{asset.status}</Badge></Cell>
            </Row>
          ))}
        </Table>
      </Panel>

      <Note>
        Horizon risk is <span className="numeric">P(RUL ≤ H)</span> computed by applying the empirical
        residual CDF from held-out engines to each RUL prediction. It is a model-derived probability
        under stated assumptions — not a guarantee, and not a substitute for inspection.
      </Note>
    </div>
  )
}
