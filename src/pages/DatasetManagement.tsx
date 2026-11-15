import { Database, Upload } from 'lucide-react'
import { Fragment, useState } from 'react'

import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import { API_BASE } from '../lib/api'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'

export function DatasetManagement() {
  const { data, source } = useData()
  const [edaDataset, setEdaDataset] = useState<'cmapss' | 'ai4i'>('cmapss')
  const [uploadState, setUploadState] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const eda = data.eda[edaDataset]

  async function upload(file: File | null, schema: 'ai4i' | 'cmapss') {
    if (!file) return
    if (source === 'snapshot') {
      setUploadState('Upload requires the live FastAPI service.')
      return
    }
    setUploading(true)
    setUploadState(null)
    try {
      const text = await file.text()
      const response = await fetch(`${API_BASE}/datasets/upload?schema=${schema}&name=${encodeURIComponent(file.name.replace(/\.[^.]+$/, ''))}`, {
        method: 'POST',
        headers: { 'Content-Type': 'text/csv' },
        body: text,
      })
      const payload = (await response.json()) as {
        error?: { message?: string }
        accepted?: boolean
        rows?: number
        quality?: { score: number }
        saved_to?: string
      }
      if (!response.ok) throw new Error(payload?.error?.message ?? `HTTP ${response.status}`)
      setUploadState(
        `${payload.accepted ? 'Accepted' : 'Accepted with errors'} · ${payload.rows ?? 0} rows, ` +
        `quality ${payload.quality?.score ?? 0}/100 · saved ${payload.saved_to ?? 'n/a'}`,
      )
    } catch (error) {
      setUploadState(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Platform · Data"
        title="Dataset management"
        description="Registered dataset versions, validation findings and automatically generated exploratory statistics."
        actions={<Badge tone="neutral">{data.datasets.length} versions</Badge>}
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {data.datasets.map((dataset) => (
          <Panel key={`${dataset.name}-${dataset.version}`}
            title={dataset.display_name}
            subtitle={`v${dataset.version} · ${number(dataset.rows, 0)} rows`}
            action={<Badge tone={dataset.quality.ok ? 'healthy' : 'critical'}>Q {dataset.quality.score}</Badge>}
          >
            <div className="space-y-1.5 text-[11px]">
              <div className="flex justify-between"><span className="text-faint">Columns</span><span className="numeric">{dataset.columns}</span></div>
              <div className="flex justify-between"><span className="text-faint">Errors</span><span className="numeric">{dataset.quality.error_count}</span></div>
              <div className="flex justify-between"><span className="text-faint">Warnings</span><span className="numeric">{dataset.quality.warning_count}</span></div>
              <div className="flex justify-between"><span className="text-faint">Source</span>
                <span className="truncate pl-2 text-right text-muted">{dataset.source_url.includes('uci') ? 'UCI' : dataset.source_url.includes('nasa') ? 'NASA' : dataset.source_url}</span>
              </div>
            </div>
            <ul className="mt-2 max-h-24 space-y-1 overflow-y-auto text-[10px] leading-relaxed text-muted">
              {dataset.quality.issues.slice(0, 5).map((issue, index) => (
                <li key={index} className="flex gap-1.5">
                  <span className={
                    issue.severity === 'error' ? 'text-[var(--color-critical)]'
                      : issue.severity === 'warning' ? 'text-[var(--color-warn)]' : 'text-faint'
                  }>•</span>
                  {issue.message}
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Panel
          title="Exploratory data analysis"
          subtitle={`${edaDataset.toUpperCase()} · ${number(eda.rows, 0)} rows · ${eda.columns} columns`}
          action={
            <div className="flex gap-1">
              {(['cmapss', 'ai4i'] as const).map((option) => (
                <button key={option} onClick={() => setEdaDataset(option)}
                  className={`rounded-[5px] px-2 py-1 text-[10px] uppercase ${
                    edaDataset === option ? 'bg-[rgb(53_214_242_/_0.12)] text-[var(--color-accent)]' : 'text-faint hover:text-fg'
                  }`}>
                  {option}
                </button>
              ))}
            </div>
          }
          bodyClassName="p-0"
        >
          <Table head={['Channel', 'Mean', 'Std', 'Min', 'Median', 'Max', 'Skew', 'Missing']}>
            {eda.descriptive.map((row) => (
              <Row key={row.column}>
                <Cell className="text-fg">{row.column}</Cell>
                <Cell className="numeric">{number(row.mean, 3)}</Cell>
                <Cell className="numeric text-muted">{number(row.std, 3)}</Cell>
                <Cell className="numeric text-muted">{number(row.min, 3)}</Cell>
                <Cell className="numeric">{number(row.median, 3)}</Cell>
                <Cell className="numeric text-muted">{number(row.max, 3)}</Cell>
                <Cell className="numeric text-faint">{number(row.skew, 2)}</Cell>
                <Cell className="numeric text-faint">{row.missing}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>

        <div className="space-y-3">
          <Panel title="Correlation matrix" subtitle="Selected sensor channels (Pearson)">
            <div className="overflow-x-auto">
              <div className="inline-grid gap-px" style={{ gridTemplateColumns: `36px repeat(${eda.correlation.features.length}, 22px)` }}>
                <span />
                {eda.correlation.features.map((feature) => (
                  <span key={feature} className="rotate-90 text-[8px] text-faint">{feature.replace('s', '')}</span>
                ))}
                {eda.correlation.matrix.map((row, rowIndex) => (
                  <Fragment key={rowIndex}>
                    <span className="text-[8.5px] text-faint">
                      {eda.correlation.features[rowIndex].replace('s', 'S')}
                    </span>
                    {row.map((value, columnIndex) => (
                      <span
                        key={`${rowIndex}-${columnIndex}`}
                        title={`${eda.correlation.features[rowIndex]} / ${eda.correlation.features[columnIndex]}: ${value}`}
                        className="block size-[22px] rounded-[2px]"
                        style={{
                          background: value >= 0
                            ? `rgb(53 214 242 / ${Math.abs(value) * 0.85})`
                            : `rgb(244 73 93 / ${Math.abs(value) * 0.85})`,
                        }}
                      />
                    ))}
                  </Fragment>
                ))}
              </div>
            </div>
            <div className="mt-2 flex items-center gap-3 text-[9.5px] text-faint">
              <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm bg-[rgb(53_214_242_/_0.7)]" /> positive</span>
              <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm bg-[rgb(244_73_93_/_0.7)]" /> negative</span>
              <span>intensity = |r|</span>
            </div>
          </Panel>

          <Panel title="Upload for validation" subtitle="CSV · max 5 MB · schema-checked, not auto-trained">
            <div className="space-y-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-[7px] border border-dashed border-[var(--color-line-strong)] px-3 py-2.5 text-[11px] text-muted hover:text-fg">
                <Upload className="size-3.5" />
                {uploading ? 'Validating…' : 'Choose AI4I-shaped CSV'}
                <input type="file" accept=".csv,text/csv" className="hidden"
                  onChange={(event) => upload(event.target.files?.[0] ?? null, 'ai4i')} />
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-[7px] border border-dashed border-[var(--color-line-strong)] px-3 py-2.5 text-[11px] text-muted hover:text-fg">
                <Upload className="size-3.5" />
                {uploading ? 'Validating…' : 'Choose C-MAPSS-shaped TXT'}
                <input type="file" accept=".txt,text/plain" className="hidden"
                  onChange={(event) => upload(event.target.files?.[0] ?? null, 'cmapss')} />
              </label>
              {uploadState && <p className="text-[10.5px] leading-relaxed text-[var(--color-accent-3)]">{uploadState}</p>}
              <p className="text-[10px] leading-relaxed text-faint">
                Uploads are parsed, mapped to the canonical schema, validated and stored as parquet.
                They never trigger training automatically.
              </p>
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Top correlations" subtitle={edaDataset.toUpperCase()}>
          <Table head={['A', 'B', '|r|']}>
            {eda.top_correlations.map((row) => (
              <Row key={`${row.a}-${row.b}`}>
                <Cell className="text-muted">{row.a}</Cell>
                <Cell className="text-muted">{row.b}</Cell>
                <Cell className="numeric">{number(row.abs_correlation, 3)}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>

        <Panel title="Fleet / failure balance" subtitle="Real labels, no synthetic augmentation">
          {eda.failure_balance ? (
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between"><span className="text-muted">Failure rate</span>
                <span className="numeric">{percent(eda.failure_balance.overall.rate, 2)} ({eda.failure_balance.overall.positives}/{eda.failure_balance.overall.rows})</span></div>
              {eda.failure_balance.modes.map((mode) => (
                <div key={mode.column} className="flex justify-between border-t border-[var(--color-line)] pt-1.5">
                  <span className="text-muted">{mode.label}</span>
                  <span className="numeric">{mode.count} ({percent(mode.rate, 2)})</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between"><span className="text-muted">Units in dataset</span>
                <span className="numeric">{eda.fleet_size ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-muted">Rows</span>
                <span className="numeric">{number(eda.rows, 0)}</span></div>
              <p className="pt-2 text-[10.5px] leading-relaxed text-faint">
                C-MAPSS has no per-row failure label: trajectories run to failure and RUL is derived
                from cycle position, which is why the fleet uses RUL and anomaly models rather than a
                failure classifier.
              </p>
            </div>
          )}
        </Panel>
      </div>

      <Note>
        Datasets are not merged. C-MAPSS (cycles, RUL) and AI4I (independent process steps, failure
        labels) have different units and failure definitions, so each has its own adapter and models.
      </Note>
      <div className="flex items-center gap-1.5 text-[10px] text-faint">
        <Database className="size-3" /> Raw files stay in data/raw (git-ignored); processed parquet in data/processed.
      </div>
    </div>
  )
}
