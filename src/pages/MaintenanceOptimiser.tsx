import { useState } from 'react'

import { BarsChart } from '../components/charts/Charts'
import { Badge } from '../components/ui/Badge'
import { PageHeader, Note } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Stat } from '../components/ui/Stat'
import { Cell, Row, Table } from '../components/ui/Table'
import { useData } from '../lib/data-context'
import { optimizeMaintenance } from '../lib/api'
import { money, number, percent } from '../lib/format'
import { navigate } from '../lib/router'

type Plan = ReturnType<typeof usePlan>['plan']

function usePlan() {
  const { data, source } = useData()
  const [plan, setPlan] = useState(data.maintenance)
  const [budget, setBudget] = useState(String(data.maintenance.budget))
  const [status, setStatus] = useState<'idle' | 'running' | 'error'>('idle')
  const [message, setMessage] = useState<string | null>(null)

  async function recompute() {
    const value = Number(budget)
    if (!Number.isFinite(value) || value <= 0) {
      setStatus('error')
      setMessage('Enter a positive budget.')
      return
    }
    if (source === 'snapshot') {
      setStatus('error')
      setMessage('Live API unavailable — re-optimisation needs the FastAPI service. Showing the build plan.')
      return
    }
    setStatus('running')
    setMessage(null)
    try {
      const next = (await optimizeMaintenance(value)) as unknown as Plan
      setPlan(next)
      setStatus('idle')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Request failed')
    }
  }

  return { plan, budget, setBudget, status, message, recompute }
}

export function MaintenanceOptimiser() {
  const { data } = useData()
  const { plan, budget, setBudget, status, message, recompute } = usePlan()
  const reactive = plan.scenarios.find((scenario) => scenario.strategy === 'reactive')
  const preventive = plan.scenarios.find((scenario) => scenario.strategy === 'preventive')
  const predictive = plan.scenarios.find((scenario) => scenario.strategy === 'predictive')

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Intelligence · Decisions"
        title="Maintenance optimiser"
        description="Priority ranking and budget-constrained selection from predicted 30-cycle risk, RUL, criticality and the configured cost model."
        actions={<Badge tone="neutral">knapsack · 25-unit steps</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Budget" value={money(plan.budget)} hint="Configurable in settings / API" />
        <Stat label="Planned spend" value={money(plan.spent)} tone="accent"
          hint={`${plan.selected.length} assets scheduled`} />
        <Stat label="Expected avoided loss" value={money(plan.expected_avoided_loss)} tone="good"
          hint="Σ risk × failure cost − planned cost" />
        <Stat label="Expected downtime" value={number(plan.expected_downtime_hours, 1)} unit="h"
          hint="Planned service hours" />
      </div>

      <Panel title="Scenario comparison" subtitle="Same fleet, same cost assumptions, three strategies">
        <BarsChart
          data={plan.scenarios.map((scenario) => ({
            strategy: scenario.strategy,
            cost: Math.round(scenario.cost),
          }))}
          xKey="strategy"
          yKey="cost"
          height={210}
          color="#35d6f2"
        />
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {plan.scenarios.map((scenario) => (
            <div key={scenario.strategy} className="raised px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-fg">{scenario.label}</span>
                <span className="numeric text-[12px] text-[var(--color-accent)]">{money(scenario.cost)}</span>
              </div>
              <p className="mt-1 text-[10.5px] leading-relaxed text-muted">{scenario.description}</p>
              <div className="mt-1 text-[10px] text-faint">
                {scenario.serviced} serviced · {number(scenario.downtime_hours, 0)} h downtime
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="Recommended plan" subtitle="Ordered by RUL urgency" bodyClassName="p-0">
          <Table head={['Asset', 'Window', 'Risk 30', 'RUL', 'Planned', 'Expected loss avoided', 'Priority']}>
            {plan.selected.map((row) => (
              <Row key={row.asset_id} onClick={() => navigate(`/assets/${row.asset_id}`)}>
                <Cell className="text-fg">{row.asset_id}</Cell>
                <Cell><Badge tone={row.window === 'immediate' ? 'critical' : row.window === 'next_30_cycles' ? 'medium' : 'healthy'}>
                  {row.window.replace(/_/g, ' ')}
                </Badge></Cell>
                <Cell className="numeric">{percent(row.failure_risk)}</Cell>
                <Cell className="numeric">{number(row.predicted_rul, 0)}</Cell>
                <Cell className="numeric">{money(row.planned_cost)}</Cell>
                <Cell className="numeric text-[var(--color-good)]">{money(row.expected_benefit)}</Cell>
                <Cell className="numeric text-muted">{number(row.priority_score, 2)}</Cell>
              </Row>
            ))}
          </Table>
        </Panel>

        <div className="space-y-3">
          <Panel title="Re-optimise" subtitle="Calls the live optimiser; disabled when offline">
            <div className="flex gap-2">
              <input
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
                inputMode="numeric"
                className="w-full rounded-[7px] border border-[var(--color-line)] bg-white/[0.02] px-3 py-1.5 text-[12px] outline-none focus:border-[rgb(53_214_242_/_0.4)]"
                placeholder="Budget"
              />
              <button
                onClick={recompute}
                disabled={status === 'running'}
                className="shrink-0 rounded-[7px] border border-[rgb(53_214_242_/_0.35)] bg-[rgb(53_214_242_/_0.1)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] transition-colors hover:bg-[rgb(53_214_242_/_0.16)] disabled:opacity-50"
              >
                {status === 'running' ? 'Solving…' : 'Optimise'}
              </button>
            </div>
            {message && <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--color-warn)]">{message}</p>}
            <div className="mt-3 space-y-1 text-[10.5px] text-muted">
              {plan.notes.map((note) => <p key={note}>· {note}</p>)}
            </div>
          </Panel>

          <Panel title="Cost assumptions" subtitle="Explicit, configurable, not measured plant data">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[10.5px]">
              {Object.entries(plan.assumptions)
                .filter(([key]) => key !== 'budget' && key !== 'acute_risk_window_cycles')
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <span className="truncate capitalize text-faint">{key.replace(/_/g, ' ')}</span>
                    <span className="numeric text-fg">{number(Number(value), 0)}</span>
                  </div>
                ))}
            </div>
            <div className="mt-3 border-t border-[var(--color-line)] pt-2 text-[10.5px] text-muted">
              Predictive cost {money(predictive?.cost)} vs preventive {money(preventive?.cost)} vs reactive{' '}
              {money(reactive?.cost)} under these assumptions.
            </div>
          </Panel>
        </div>
      </div>

      <Panel title="Deferred to monitoring" subtitle="Positive-benefit assets that did not fit the budget" bodyClassName="p-0">
        <Table head={['Asset', 'Risk 30', 'RUL', 'Expected benefit', 'Recommended action']}>
          {plan.deferred.slice(0, 12).map((row) => (
            <Row key={row.asset_id} onClick={() => navigate(`/assets/${row.asset_id}`)}>
              <Cell className="text-fg">{row.asset_id}</Cell>
              <Cell className="numeric">{percent(row.failure_risk)}</Cell>
              <Cell className="numeric">{number(row.predicted_rul, 0)}</Cell>
              <Cell className="numeric text-muted">{money(row.expected_benefit)}</Cell>
              <Cell className="text-muted">continue condition monitoring</Cell>
            </Row>
          ))}
        </Table>
      </Panel>

      <Note tone="warn">
        Savings are scenario estimates under the stated cost model and predicted risk. They are not
        validated plant savings. Missing a failure is assumed to cost 10× an unnecessary inspection;
        change the cost model in <span className="text-fg">System Settings</span> or through the API.
        Data: {data.meta.dataset_versions.cmapss?.rows.toLocaleString()} C-MAPSS cycles.
      </Note>
    </div>
  )
}
