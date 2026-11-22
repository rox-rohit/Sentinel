import { BarsChart } from '../components/charts/Charts'
import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number, percent, relativeTime } from '../lib/format'

interface ComparisonRow {
  model: string
  cv_pr_auc?: number
  cv_roc_auc?: number
  threshold?: number
  train_seconds?: number
  test?: { pr_auc: number; recall: number; precision: number; f1: number; expected_cost: number }
}

export function ModelLaboratory() {
  const { data } = useData()
  const rulModel = data.models.find((model) => model.name === 'cmapss_rul')
  const classifier = data.models.find((model) => model.name === 'ai4i_failure_classifier')
  const rulMetrics = (rulModel?.metrics.official_test ?? {}) as Record<string, number>
  const classifierTest = (classifier?.metrics.test ?? {}) as Record<string, number>
  const confusion = (classifierTest.confusion_matrix as unknown as number[][]) ?? [[0, 0], [0, 0]]
  const comparison = ((classifier?.metrics.comparison ?? []) as unknown as ComparisonRow[])
  const driftRows = [
    ...data.drift.cmapss.features.map((row) => ({ ...row, scope: 'C-MAPSS' })),
    ...data.drift.ai4i.features.map((row) => ({ ...row, scope: 'AI4I' })),
  ].sort((a, b) => b.psi - a.psi).slice(0, 10)

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Platform · MLOps"
        title="Model laboratory"
        description="Registered model versions, evaluation metrics and distribution drift. Models are only promoted by the build pipeline after held-out evaluation."
        actions={<Badge tone="healthy">{data.models.length} registered</Badge>}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="RUL regression" subtitle={`${rulModel?.algorithm ?? '—'} · ${rulModel?.version ?? '—'}`}
          action={<Badge tone={rulModel?.status === 'active' ? 'healthy' : 'neutral'}>{rulModel?.status ?? 'missing'}</Badge>}>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            {[
              ['MAE', number(rulMetrics.mae, 2)],
              ['RMSE', number(rulMetrics.rmse, 2)],
              ['NASA score', number(rulMetrics.nasa_score, 1)],
              ['Test units', String(rulMetrics.units ?? '—')],
              ['Dataset', 'C-MAPSS FD001'],
              ['Task', 'RUL regression'],
            ].map(([label, value]) => (
              <div key={label} className="raised px-2.5 py-2">
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-faint">{label}</div>
                <div className="numeric mt-0.5 text-[12px] text-fg">{value}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[10.5px] leading-relaxed text-muted">
            Engine-wise split; official test scored once at each unit's final cycle. Registered{' '}
            {rulModel ? relativeTime(rulModel.created_at) : '—'}.
          </p>
        </Panel>

        <Panel title="Failure classification" subtitle={`${classifier?.algorithm ?? '—'} · ${classifier?.version ?? '—'}`}
          action={<Badge tone={classifier?.status === 'active' ? 'healthy' : 'neutral'}>{classifier?.status ?? 'missing'}</Badge>}>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            {[
              ['PR-AUC', number(classifierTest.pr_auc, 3)],
              ['Recall', percent(classifierTest.recall)],
              ['Precision', percent(classifierTest.precision)],
              ['F1', number(classifierTest.f1, 3)],
              ['Threshold', number(classifierTest.threshold, 2)],
              ['Expected cost', number(classifierTest.expected_cost, 0)],
            ].map(([label, value]) => (
              <div key={label} className="raised px-2.5 py-2">
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-faint">{label}</div>
                <div className="numeric mt-0.5 text-[12px] text-fg">{value}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-4">
            <div>
              <div className="text-[9.5px] uppercase tracking-[0.08em] text-faint">Confusion (TN FP / FN TP)</div>
              <div className="numeric mt-1 text-[11px] text-muted">
                {confusion[0][0]} &nbsp;{confusion[0][1]} / {confusion[1][0]} &nbsp;{confusion[1][1]}
              </div>
            </div>
            <div className="ml-auto text-right text-[10.5px] text-muted">
              Dataset AI4I · held-out 25%
              <br />threshold tuned on out-of-fold probabilities
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Classifier comparison" subtitle="5-fold stratified CV on the training split" bodyClassName="p-0">
          <Table head={['Model', 'CV PR-AUC', 'CV ROC-AUC', 'Threshold', 'Test PR-AUC', 'Test recall', 'Cost', 's']}>
            {comparison.map((row) => (
              <Row key={row.model}>
                <Cell className={row.model === classifier?.algorithm ? 'text-[var(--color-accent)]' : 'text-fg'}>
                  {row.model}
                </Cell>
                <Cell className="numeric">{number(row.cv_pr_auc, 3)}</Cell>
                <Cell className="numeric">{number(row.cv_roc_auc, 3)}</Cell>
                <Cell className="numeric">{number(row.threshold, 2)}</Cell>
                <Cell className="numeric">{number(row.test?.pr_auc, 3)}</Cell>
                <Cell className="numeric">{percent(row.test?.recall)}</Cell>
                <Cell className="numeric text-muted">{number(row.test?.expected_cost, 0)}</Cell>
                <Cell className="numeric text-faint">{number(row.train_seconds, 1)}</Cell>
              </Row>
            ))}
          </Table>
          <div className="border-t border-[var(--color-line)] px-4 py-2 text-[10.5px] text-muted">
            Selection uses CV PR-AUC, not accuracy; expected cost uses the configured failure/inspection costs.
          </div>
        </Panel>

        <Panel title="RUL model comparison" subtitle="Held-out engine validation" bodyClassName="p-0">
          <Table head={['Model', 'MAE', 'RMSE', 'NASA']}>
            {data.rul.benchmark.comparison.map((row) => (
              <Row key={String(row.model)}>
                <Cell className={row.model === rulModel?.algorithm ? 'text-[var(--color-accent)]' : 'text-fg'}>
                  {String(row.model)}
                </Cell>
                <Cell className="numeric">{number(Number(row.mae), 2)}</Cell>
                <Cell className="numeric">{number(Number(row.rmse), 2)}</Cell>
                <Cell className="numeric">{number(Number(row.nasa_score), 0)}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>
      </div>

      <Panel title="Feature drift (PSI)" subtitle={data.drift.method}>
        <BarsChart
          data={driftRows.map((row) => ({ feature: `${row.scope} · ${row.feature}`, psi: row.psi }))}
          xKey="feature"
          yKey="psi"
          horizontal
          height={260}
          color="var(--chart-3)"
        />
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[10.5px] text-muted">
          <span>Overall: <Badge tone={data.drift.overall_status === 'drift' ? 'medium' : 'healthy'}>{data.drift.overall_status}</Badge></span>
          <span className="numeric">worst PSI {number(data.drift.worst_psi, 3)}</span>
          <span className="text-faint">stable &lt; 0.10 · monitor 0.10–0.25 · drift ≥ 0.25</span>
        </div>
        <p className="mt-2 text-[10.5px] leading-relaxed text-muted">{data.drift.note}</p>
      </Panel>

      <div className="grid gap-3 md:grid-cols-2">
        <Note>
          Registry versions are content-addressed from their metrics, so an unchanged rebuild does not
          create a new version. Promotion is manual: the active status is written by the build, and the
          API exposes promotion and rollback metadata without auto-replacing a model.
        </Note>
        <Note tone="warn">
          Not yet implemented: MLflow experiment tracking and PyTorch sequence models. Both are blocked
          by the local environment (disk / no CUDA PyTorch) and are listed in TASKS.md rather than
          presented as working.
        </Note>
      </div>
    </div>
  )
}
