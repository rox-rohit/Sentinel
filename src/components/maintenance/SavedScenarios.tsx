import { GitCompare, Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import type { ScenarioComparison, ScenarioSummary, Snapshot } from '../../data/types'
import { compareScenarios, deleteScenario, fetchScenarios, saveScenario } from '../../lib/api'
import { money, number } from '../../lib/format'
import { Badge } from '../ui/Badge'
import { Note } from '../ui/PageHeader'
import { Panel } from '../ui/Panel'
import { Cell, Row, Table } from '../ui/Table'

const MAX_SELECTED = 4

function formatMetric(value: number | null, unit: string) {
  if (value === null || value === undefined) return '—'
  if (unit === 'currency') return money(value)
  if (unit === 'hours') return `${number(value, 0)} h`
  return number(value, 0)
}

export function SavedScenarios({ plan, live }: {
  plan: Snapshot['maintenance']
  live: boolean
}) {
  const [saved, setSaved] = useState<ScenarioSummary[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState<'save' | 'compare' | number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!live) return
    try {
      setSaved(await fetchScenarios())
      setError(null)
    } catch (cause) {
      setSaved([])
      setError(cause instanceof Error ? cause.message : 'Scenario API unreachable')
    }
  }, [live])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleSave() {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Give the scenario a name before saving.')
      return
    }
    setBusy('save')
    setError(null)
    setMessage(null)
    try {
      const created = await saveScenario(trimmed, plan.budget)
      setName('')
      setMessage(`Saved “${created.name}” at ${money(created.budget)} budget.`)
      setSelected((current) => [...current, created.id].slice(-MAX_SELECTED))
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the scenario')
    } finally {
      setBusy(null)
    }
  }

  function toggle(id: number) {
    setError(null)
    setSelected((current) => {
      if (current.includes(id)) return current.filter((entry) => entry !== id)
      if (current.length >= MAX_SELECTED) {
        setError(`Select at most ${MAX_SELECTED} scenarios at a time.`)
        return current
      }
      return [...current, id]
    })
  }

  async function handleCompare() {
    if (selected.length < 2) {
      setError('Select at least two saved scenarios to compare.')
      return
    }
    setBusy('compare')
    setError(null)
    try {
      setComparison(await compareScenarios(selected))
    } catch (cause) {
      setComparison(null)
      setError(cause instanceof Error ? cause.message : 'Comparison failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleDelete(id: number) {
    setBusy(id)
    setError(null)
    try {
      await deleteScenario(id)
      setSelected((current) => current.filter((entry) => entry !== id))
      setComparison((current) =>
        current && current.scenarios.some((scenario) => scenario.id === id) ? null : current,
      )
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Delete failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Panel
      title="Saved scenarios"
      subtitle="Persist an optimisation result and compare budgets side by side"
      action={<Badge tone="neutral">{saved.length} saved</Badge>}
      bodyClassName="p-0"
    >
      {!live ? (
        <div className="px-4 py-3">
          <Note tone="warn">
            Saving and comparing scenarios needs the FastAPI service. The build plan above is
            read-only in snapshot mode.
          </Note>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-line)] px-3 py-2.5">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={`Name this run (${money(plan.budget)} budget)`}
              className="min-w-[220px] flex-1 rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-1.5 text-[11.5px] outline-none focus:border-[var(--accent-line)]"
            />
            <button
              onClick={() => void handleSave()}
              disabled={busy === 'save'}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] hover:bg-[var(--accent-soft-strong)] disabled:opacity-50"
            >
              <Save className="size-3.5" />
              {busy === 'save' ? 'Saving…' : 'Save current plan'}
            </button>
            <button
              onClick={() => void handleCompare()}
              disabled={busy === 'compare' || selected.length < 2}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-3 py-1.5 text-[11px] text-muted hover:text-fg disabled:opacity-40"
            >
              <GitCompare className="size-3.5" />
              Compare {selected.length > 0 ? `(${selected.length})` : ''}
            </button>
          </div>

          {(error || message) && (
            <div className="border-b border-[var(--color-line)] px-3 py-2">
              {error ? <Note tone="warn">{error}</Note> : <Note>{message}</Note>}
            </div>
          )}

          {saved.length > 0 ? (
            <Table head={['', 'Scenario', 'Budget', 'Spent', 'Avoided loss', 'Serviced', 'Saved', '']}>
              {saved.map((scenario) => (
                <Row key={scenario.id}>
                  <Cell>
                    <input
                      type="checkbox"
                      checked={selected.includes(scenario.id)}
                      onChange={() => toggle(scenario.id)}
                      aria-label={`Select ${scenario.name}`}
                      className="size-3.5 accent-[var(--color-accent)]"
                    />
                  </Cell>
                  <Cell className="text-fg">
                    {scenario.name}
                    {scenario.note && <p className="text-[10px] text-faint">{scenario.note}</p>}
                  </Cell>
                  <Cell className="numeric">{money(scenario.budget)}</Cell>
                  <Cell className="numeric">{money(scenario.spent)}</Cell>
                  <Cell className="numeric text-[var(--color-good)]">
                    {money(scenario.expected_avoided_loss)}
                  </Cell>
                  <Cell className="numeric">{scenario.assets_serviced}</Cell>
                  <Cell className="text-faint">
                    {scenario.created_at ? new Date(scenario.created_at).toLocaleDateString() : '—'}
                  </Cell>
                  <Cell>
                    <button
                      onClick={() => void handleDelete(scenario.id)}
                      disabled={busy === scenario.id}
                      title="Delete scenario"
                      className="rounded-[6px] border border-[var(--color-line)] p-1.5 text-faint hover:text-[var(--color-bad)] disabled:opacity-40"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </Cell>
                </Row>
              ))}
            </Table>
          ) : (
            <p className="px-4 py-4 text-[11.5px] text-muted">
              No saved scenarios yet. Re-optimise at a different budget, name the run and save it,
              then select two or more to compare.
            </p>
          )}

          {comparison && (
            <div className="border-t border-[var(--color-line)]">
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <span className="text-[11px] text-fg">Side-by-side comparison</span>
                <span className="text-[10px] text-faint">
                  {comparison.assets.shared_count} assets in every plan ·{' '}
                  {comparison.assets.union_count} distinct assets across plans
                </span>
              </div>
              <Table head={['Metric', ...comparison.scenarios.map((scenario) => scenario.name)]}>
                {comparison.metrics.map((metric) => (
                  <Row key={metric.key}>
                    <Cell className="text-muted">
                      {metric.label}
                      <span className="ml-1 text-[9.5px] text-faint">
                        ({metric.better} is better)
                      </span>
                    </Cell>
                    {comparison.scenarios.map((scenario) => {
                      const value = metric.values[String(scenario.id)] ?? null
                      const best = metric.best_ids.includes(String(scenario.id))
                      return (
                        <Cell
                          key={scenario.id}
                          className={`numeric ${best ? 'text-[var(--color-good)]' : 'text-fg'}`}
                        >
                          {formatMetric(value, metric.unit)}
                          {best && <span className="ml-1 text-[9px] uppercase">best</span>}
                        </Cell>
                      )
                    })}
                  </Row>
                ))}
              </Table>
              <div className="px-3 py-2 text-[10.5px] leading-relaxed text-faint">
                {comparison.note}
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  )
}
