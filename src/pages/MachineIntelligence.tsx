import { ArrowUpRight, Filter } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '../components/ui/Badge'
import { HealthMeter } from '../components/ui/Meter'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import type { HealthCategory } from '../data/types'
import { useData } from '../lib/data-context'
import { number, percent } from '../lib/format'
import { navigate } from '../lib/router'

const FILTERS: (HealthCategory | 'all')[] = ['all', 'healthy', 'attention', 'warning', 'critical']

export function MachineIntelligence() {
  const { data } = useData()
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    return [...data.assets]
      .filter((asset) => (filter === 'all' ? true : asset.status === filter))
      .filter((asset) => asset.label.toLowerCase().includes(query.trim().toLowerCase()))
      .sort((a, b) => a.health_score - b.health_score)
  }, [data.assets, filter, query])

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operations · Assets"
        title="Machine intelligence"
        description="Condition, estimated remaining life and anomaly state for every monitored unit. Sorted by health, lowest first."
        actions={<Badge tone="neutral">{rows.length} assets</Badge>}
      />

      <Panel bodyClassName="p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Filter className="size-3.5 text-faint" />
          {FILTERS.map((option) => (
            <button
              key={option}
              onClick={() => setFilter(option)}
              className={`rounded-[7px] border px-2.5 py-1 text-[11px] capitalize transition-colors ${
                filter === option
                  ? 'border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--color-accent)]'
                  : 'border-[var(--color-line)] text-muted hover:text-fg'
              }`}
            >
              {option}
            </button>
          ))}
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search unit…"
            className="ml-auto w-40 rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-1 text-[11px] outline-none placeholder:text-faint focus:border-[var(--accent-line)]"
          />
        </div>
      </Panel>

      <Panel bodyClassName="p-0">
        <Table head={['Asset', 'State', 'Health', 'RUL estimate', 'Interval', 'Risk 30', 'Anomaly', 'Cycle', '']}>
          {rows.map((asset) => (
            <Row key={asset.id} onClick={() => navigate(`/assets/${asset.id}`)}>
              <Cell className="text-fg">{asset.label}</Cell>
              <Cell><Badge tone={asset.status}>{asset.status}</Badge></Cell>
              <Cell className="w-32">
                <div className="flex items-center gap-2">
                  <HealthMeter value={asset.health_score} className="w-16" />
                  <span className="numeric text-[11px] text-muted">{number(asset.health_score, 0)}</span>
                </div>
              </Cell>
              <Cell className="numeric">{number(asset.rul.estimate, 0)} cyc</Cell>
              <Cell className="numeric text-muted">
                {number(asset.rul.lower, 0)} – {number(asset.rul.upper, 0)}
              </Cell>
              <Cell className="numeric">{percent(asset.rul.horizon_risk['30'] ?? 0)}</Cell>
              <Cell>
                <div className="flex items-center gap-2">
                  <Badge tone={asset.anomaly.severity}>{asset.anomaly.severity}</Badge>
                  <span className="numeric text-[10.5px] text-faint">{number(asset.anomaly.score, 2)}</span>
                </div>
              </Cell>
              <Cell className="numeric text-muted">{asset.cycle}</Cell>
              <Cell><ArrowUpRight className="size-3.5 text-faint" /></Cell>
            </Row>
          ))}
          {rows.length === 0 && (
            <Row><Cell className="text-muted">No assets match this filter.</Cell></Row>
          )}
        </Table>
      </Panel>

      <Note>
        Each asset is a held-out C-MAPSS test trajectory. “Cycle” is the unit's current operating
        cycle, not a timestamp. Intervals are 80% empirical residual bands, not guarantees.
      </Note>
    </div>
  )
}
