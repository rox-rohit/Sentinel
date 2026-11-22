import { ScatterPlot } from '../components/charts/Charts'
import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number } from '../lib/format'
import { navigate } from '../lib/router'

export function RULIntelligence() {
  const { data } = useData()
  const { benchmark, points, fleet, warnings, limitations } = data.rul
  const official = benchmark.official
  const residuals = benchmark.residuals

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Intelligence · Prognostics"
        title="RUL intelligence"
        description={benchmark.protocol}
        actions={<Badge tone="neutral">target clipped at {benchmark.clip} cycles</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Official test MAE" value={number(official.mae, 2)} unit="cycles" tone="accent"
          hint={`${official.units} held-out units`} />
        <Stat label="RMSE" value={number(official.rmse, 2)} unit="cycles" hint="Same held-out units" />
        <Stat label="NASA score" value={number(official.nasa_score, 1)} hint="Lower is better; late errors penalised" />
        <Stat label="Mean bias" value={number(official.bias, 2)} unit="cycles"
          tone={Math.abs(Number(official.bias)) < 3 ? 'good' : 'warn'} hint="Predicted − actual" />
        <Stat label="p90 absolute error" value={number(official.p90_abs_error, 1)} unit="cycles"
          hint="Tail error on the test set" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <Panel title="Predicted vs actual RUL" subtitle="Official C-MAPSS test units at their final recorded cycle">
          <ScatterPlot
            data={points.map((point) => ({ x: point.actual, y: point.predicted, z: 40, name: point.asset_id }))}
            height={270}
            xLabel="Actual RUL (cycles)"
            yLabel="Predicted RUL"
            color="var(--chart-1)"
          />
          <p className="mt-1 text-[10.5px] text-muted">
            Points on the diagonal are exact. Errors above the diagonal are early (conservative) predictions.
          </p>
        </Panel>

        <Panel title="Model comparison" subtitle="Engine-wise validation split, all cycles" bodyClassName="p-0">
          <Table head={['Model', 'MAE', 'RMSE', 'NASA', 'Bias']}>
            {benchmark.comparison.map((row) => (
              <Row key={String(row.model)}>
                <Cell className={row.model === data.models.find((m) => m.name === 'cmapss_rul')?.algorithm ? 'text-[var(--color-accent)]' : 'text-fg'}>
                  {String(row.model)}
                </Cell>
                <Cell className="numeric">{number(Number(row.mae), 2)}</Cell>
                <Cell className="numeric">{number(Number(row.rmse), 2)}</Cell>
                <Cell className="numeric">{number(Number(row.nasa_score), 1)}</Cell>
                <Cell className="numeric text-muted">{number(Number(row.bias), 2)}</Cell>
              </Row>
            ))}
          </Table>
          <div className="border-t border-[var(--color-line)] px-4 py-3 text-[11px] text-muted">
            <div className="flex justify-between"><span>Validation MAE</span>
              <span className="numeric">{number(Number(benchmark.validation.mae), 2)}</span></div>
            <div className="mt-1 flex justify-between"><span>Residual p10 / p90</span>
              <span className="numeric">{number(Number(residuals.p10), 1)} / {number(Number(residuals.p90), 1)}</span></div>
            <div className="mt-1 flex justify-between"><span>Residual std</span>
              <span className="numeric">{number(Number(residuals.std), 2)}</span></div>
            <div className="mt-1 flex justify-between"><span>Residual sample</span>
              <span className="numeric">{String(residuals.count)} rows</span></div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Fleet RUL estimates" subtitle="Current state of every unit in the held-out fleet" bodyClassName="p-0">
          <div className="max-h-[340px] overflow-y-auto">
            <Table head={['Asset', 'Estimate', '80% band', 'State']}>
              {[...fleet].sort((a, b) => a.estimate - b.estimate).map((asset) => (
                <Row key={asset.id} onClick={() => navigate(`/assets/${asset.id}`)}>
                  <Cell className="text-fg">{asset.id}</Cell>
                  <Cell className="numeric">{number(asset.estimate, 0)}</Cell>
                  <Cell className="numeric text-muted">{number(asset.lower, 0)} – {number(asset.upper, 0)}</Cell>
                  <Cell><Badge tone={asset.status}>{asset.status}</Badge></Cell>
                </Row>
              ))}
            </Table>
          </div>
        </Panel>

        <div className="space-y-3">
          <Panel title="Assumptions and limits" subtitle="Read before acting on any RUL value">
            <ul className="space-y-2 text-[11.5px] leading-relaxed text-muted">
              {limitations.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-warn)]" />
                  {item}
                </li>
              ))}
            </ul>
          </Panel>
          {warnings.length > 0 && (
            <Panel title="Model warnings">
              {warnings.map((warning) => (
                <Note key={warning} tone="warn">{warning}</Note>
              ))}
            </Panel>
          )}
          <Note>
            The Ridge baseline wins the held-out comparison on NASA score despite simpler structure;
            tree ensembles reduce MAE marginally but penalise late predictions more. Model selection
            uses NASA score, not accuracy-like metrics, because late RUL errors are the costly ones.
          </Note>
        </div>
      </div>
    </div>
  )
}
