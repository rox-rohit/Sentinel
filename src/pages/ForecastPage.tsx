import { Badge } from '../components/ui/Badge'
import { TelemetryChart } from '../components/charts/Charts'
import { Note, PageHeader } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'

const MODEL_LABELS: Record<string, string> = {
  persistence: 'Persistence',
  moving_average: 'Moving average',
  exponential_smoothing: 'Exp. smoothing',
  hist_gradient_boosting: 'Gradient boosting',
}

const MODEL_ORDER = ['persistence', 'moving_average', 'exponential_smoothing', 'hist_gradient_boosting']

export function ForecastPage() {
  const { data } = useData()
  const forecast = data.forecast
  const { summary, best, comparison, example, validation, limitations } = forecast

  const rows = best.map((entry) => {
    const candidates = comparison.filter(
      (row) => row.sensor === entry.sensor && row.horizon === entry.horizon,
    )
    const byModel = new Map(candidates.map((row) => [row.model, row]))
    const bestMase = Math.min(...candidates.map((row) => row.mase))
    return { entry, byModel, bestMase }
  })

  const exampleSeries = example.series[0]
  const chartData = exampleSeries
    ? exampleSeries.horizons.map((horizon, index) => ({
        horizon: `+${horizon}`,
        actual: exampleSeries.actual[index],
        forecast: exampleSeries.forecast[index],
      }))
    : []

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Intelligence · Forecasting"
        title="Sensor forecasting"
        description={validation.protocol}
        actions={
          <>
            <Badge tone="neutral">{forecast.all_horizons.length} horizons</Badge>
            <Badge tone="healthy">best: {MODEL_LABELS[summary.best_model] ?? summary.best_model}</Badge>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Best model" value={MODEL_LABELS[summary.best_model] ?? summary.best_model}
          tone="accent" hint={`Wins ${Math.max(...Object.values(summary.wins))} of ${best.length} sensor-horizon cells at h=1,5,10`} />
        <Stat label="Mean MASE (best)" value={summary.mean_best_mase === null ? '—' : number(summary.mean_best_mase, 3)}
          hint="Lower is better; < 1 beats the naive forecast" />
        <Stat label="Persistence MASE" value={summary.mean_persistence_mase === null ? '—' : number(summary.mean_persistence_mase, 3)}
          hint="Reference baseline" />
        <Stat label="Improvement vs naive"
          value={summary.improvement_vs_persistence_pct === null ? '—' : `${number(summary.improvement_vs_persistence_pct, 1)}%`}
          tone={summary.improvement_vs_persistence_pct !== null && summary.improvement_vs_persistence_pct > 0 ? 'good' : 'bad'}
          hint="Mean MASE reduction across reported cells" />
        <Stat label="Chronological test rows" value={number(validation.test_rows, 0)}
          hint={`${validation.units} engines · ${percent(1 - validation.train_fraction)} of each trajectory held out`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <Panel title="Accuracy by sensor and horizon" subtitle="MASE on the held-out tail of every engine; lowest per row is highlighted"
          bodyClassName="p-0">
          <Table head={['Sensor', 'h', ...MODEL_ORDER.map((model) => MODEL_LABELS[model]), 'MAE (best)']}>
            {rows.map(({ entry, byModel, bestMase }) => (
              <Row key={`${entry.sensor}-${entry.horizon}`}>
                <Cell className="text-fg">{entry.label}</Cell>
                <Cell className="numeric text-muted">+{entry.horizon}</Cell>
                {MODEL_ORDER.map((model) => {
                  const row = byModel.get(model)
                  if (!row) return <Cell key={model} className="numeric text-faint">—</Cell>
                  const isBest = Math.abs(row.mase - bestMase) < 1e-9
                  return (
                    <Cell key={model} className={isBest ? 'numeric text-[var(--color-accent)]' : 'numeric text-muted'}>
                      {number(row.mase, 3)}
                    </Cell>
                  )
                })}
                <Cell className="numeric">{number(entry.mae, 3)}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>

        <div className="space-y-3">
          <Panel title="Validation protocol" subtitle="Why these numbers are out-of-sample">
            <ul className="space-y-2 text-[11.5px] leading-relaxed text-muted">
              <li className="flex gap-2"><span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
                Per engine, the first {Math.round(validation.train_fraction * 100)}% of cycles train the model;
                the remaining cycles are scored.
              </li>
              <li className="flex gap-2"><span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
                Every feature at cycle t is lagged or uses a window shifted by one, so no future value leaks back.
              </li>
              <li className="flex gap-2"><span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
                MASE scales the error by the naive one-step error on the training rows, so sensors on different units are comparable.
              </li>
            </ul>
            <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-[11px] text-muted">
              <div className="flex justify-between"><span>Training rows</span>
                <span className="numeric">{number(validation.train_rows, 0)}</span></div>
              <div className="mt-1 flex justify-between"><span>Test rows</span>
                <span className="numeric">{number(validation.test_rows, 0)}</span></div>
              <div className="mt-1 flex justify-between"><span>Smoothing alpha</span>
                <span className="numeric">{validation.ses_alpha}</span></div>
            </div>
          </Panel>

          <Panel title="Assumptions and limits">
            <ul className="space-y-2 text-[11.5px] leading-relaxed text-muted">
              {limitations.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--color-warn)]" />
                  {item}
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel
        title="Example forecast"
        subtitle={
          exampleSeries
            ? `${exampleSeries.label} · ${exampleSeries.asset_id} · origin cycle ${example.origin_cycle}`
            : 'No example forecast available'
        }
      >
        {exampleSeries ? (
          <>
            <TelemetryChart
              data={chartData}
              xKey="horizon"
              height={230}
              series={[
                { key: 'actual', color: '#8b9bab', label: 'Actual' },
                { key: 'forecast', color: '#35d6f2', label: 'Forecast' },
              ]}
            />
            <p className="mt-1 text-[10.5px] text-muted">
              The forecast is produced from history up to cycle {example.origin_cycle} only; the actual line is
              the recorded trajectory after that point, shown for comparison.
            </p>
          </>
        ) : (
          <p className="text-[11px] text-muted">
            Run the build pipeline to produce forecast models and the example horizon window.
          </p>
        )}
      </Panel>

      <Note>
        Forecasting answers a different question from RUL: it projects sensor values a few cycles ahead, while RUL
        predicts time to end of life. MASE below 1 means the model beats the naive &ldquo;last value repeated&rdquo;
        forecast on the held-out tail; it is reported per sensor and horizon, never as a single accuracy figure.
      </Note>
    </div>
  )
}
