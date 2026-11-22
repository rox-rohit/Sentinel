import { useState } from 'react'

import { Badge, Label } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'

export function Explainability() {
  const { data } = useData()
  const xai = data.explainability
  const [sampleIndex, setSampleIndex] = useState(0)
  const sample = xai.samples[sampleIndex]
  const maxImportance = xai.global_importance[0]?.importance ?? 1

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Intelligence · Attribution"
        title="Explainable AI"
        description={xai.method}
        actions={<Badge tone="neutral">{xai.dataset.toUpperCase()} classifier</Badge>}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
        <Panel title="Global feature importance" subtitle="Permutation importance on the held-out split (PR-AUC drop)">
          <div className="space-y-2.5">
            {xai.global_importance.map((entry) => (
              <div key={entry.feature}>
                <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
                  <span className="truncate text-muted">{entry.label}</span>
                  <span className="numeric shrink-0 text-fg">{number(entry.importance, 3)}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
                  <div className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{ width: `${Math.max(2, (entry.importance / maxImportance) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-[var(--color-line)] pt-2 text-[10.5px] text-faint">
            Bars scaled to the strongest feature. Permutation importance measures predictive dependence,
            not physical causation.
          </div>
        </Panel>

        <Panel
          title="Individual prediction explanation"
          subtitle={sample ? `${sample.title} · row ${sample.row_id}` : 'No sample'}
          action={
            <div className="flex gap-1">
              {xai.samples.map((entry, index) => (
                <button
                  key={entry.row_id}
                  onClick={() => setSampleIndex(index)}
                  className={`rounded-[5px] px-2 py-1 text-[10px] ${
                    index === sampleIndex
                      ? 'bg-[var(--accent-soft)] text-[var(--color-accent)]'
                      : 'text-faint hover:text-fg'
                  }`}
                >
                  {index + 1}
                </button>
              ))}
            </div>
          }
        >
          {sample && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-3">
                <div>
                  <Label>Predicted probability</Label>
                  <div className="numeric mt-0.5 text-[22px] text-fg">{percent(sample.probability, 1)}</div>
                </div>
                <div>
                  <Label>Threshold</Label>
                  <div className="numeric mt-0.5 text-[22px] text-muted">{percent(sample.threshold, 1)}</div>
                </div>
                <div>
                  <Label>Decision</Label>
                  <div className="mt-1"><Badge tone={sample.decision === 'alert' ? 'high' : 'healthy'}>{sample.decision}</Badge></div>
                </div>
                <div className="ml-auto text-right">
                  <Label>Recorded outcome</Label>
                  <div className="mt-1 text-[12px] text-muted">
                    {sample.actual_failure ? 'failure recorded' : 'no failure'}
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                {sample.contributions.map((contribution) => {
                  const scale = Math.max(...sample.contributions.map((c) => Math.abs(c.contribution)), 0.001)
                  const width = (Math.abs(contribution.contribution) / scale) * 50
                  const positive = contribution.contribution > 0
                  return (
                    <div key={contribution.feature}>
                      <div className="mb-0.5 flex items-center justify-between text-[10.5px]">
                        <span className="truncate text-muted">{contribution.label}</span>
                        <span className={`numeric ${positive ? 'text-[var(--color-bad)]' : 'text-[var(--color-good)]'}`}>
                          {positive ? '+' : ''}{contribution.contribution.toFixed(3)}
                        </span>
                      </div>
                      <div className="relative h-2 rounded-full bg-[var(--overlay-2)]">
                        <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" />
                        <div
                          className="absolute inset-y-0 rounded-full"
                          style={{
                            width: `${width}%`,
                            left: positive ? '50%' : `${50 - width}%`,
                            background: positive ? 'var(--color-bad)' : 'var(--color-good)',
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 border-t border-[var(--color-line)] pt-2 text-[11px] leading-relaxed text-muted">
                {sample.narrative}
              </p>
            </>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Panel title="Probability calibration" subtitle="Reliability on the held-out split" bodyClassName="p-0">
          <Table head={['Predicted bin', 'Mean predicted', 'Observed rate', 'Records']}>
            {xai.calibration.reliability.map((row) => (
              <Row key={`${row.bin_lower}-${row.bin_upper}`}>
                <Cell className="numeric text-muted">
                  {percent(row.bin_lower, 0)}–{percent(row.bin_upper, 0)}
                </Cell>
                <Cell className="numeric">{percent(row.mean_predicted, 1)}</Cell>
                <Cell className="numeric">{percent(row.observed_rate, 1)}</Cell>
                <Cell className="numeric text-muted">{row.count}</Cell>
              </Row>
            ))}
          </Table>
          <div className="border-t border-[var(--color-line)] px-4 py-2 text-[10.5px] text-muted">
            Brier score {number(xai.calibration.brier_score, 4)} vs base-rate {number(xai.calibration.brier_baseline_rate, 4)}.
            {' '}No post-hoc calibrator is applied.
          </div>
        </Panel>

        <Panel title="Failure-mode models" subtitle={xai.failure_modes.method} bodyClassName="p-0">
          <Table head={['Mode', 'Train support', 'PR-AUC', 'Recall', 'Status']}>
            {xai.failure_modes.labels.map((mode) => (
              <Row key={mode.column}>
                <Cell className="text-fg">{mode.label}</Cell>
                <Cell className="numeric text-muted">{mode.train_support}</Cell>
                <Cell className="numeric">{mode.pr_auc === null ? '—' : number(mode.pr_auc, 3)}</Cell>
                <Cell className="numeric">{mode.recall === null ? '—' : percent(mode.recall)}</Cell>
                <Cell>
                  <Badge tone={mode.status === 'supported' ? 'healthy' : mode.status === 'insufficient_support' ? 'critical' : 'medium'}>
                    {mode.status.replace(/_/g, ' ')}
                  </Badge>
                </Cell>
              </Row>
            ))}
          </Table>
        </Panel>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {xai.limitations.map((limitation) => (
          <Note key={limitation} tone="warn">{limitation}</Note>
        ))}
      </div>
    </div>
  )
}
