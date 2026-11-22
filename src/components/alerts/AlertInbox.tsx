import { Check, CheckCheck, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import type { Alert, AlertInbox as AlertInboxData, AlertStatus } from '../../data/types'
import { acknowledgeAlert, fetchAlerts, resolveAlert } from '../../lib/api'
import { number } from '../../lib/format'
import { navigate } from '../../lib/router'
import { Badge, Label } from '../ui/Badge'
import { Note } from '../ui/PageHeader'
import { Panel } from '../ui/Panel'
import { Cell, Row, Table } from '../ui/Table'

const FILTERS = ['open', 'acknowledged', 'resolved', 'all'] as const
type Filter = (typeof FILTERS)[number]

const STATUS_TONE: Record<AlertStatus, 'attention' | 'healthy' | 'neutral'> = {
  open: 'neutral',
  acknowledged: 'attention',
  resolved: 'healthy',
}

export function AlertInbox({ fallback, live }: { fallback: Alert[]; live: boolean }) {
  const [inbox, setInbox] = useState<AlertInboxData | null>(null)
  const [filter, setFilter] = useState<Filter>('open')
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!live) return
    try {
      setInbox(await fetchAlerts())
      setError(null)
    } catch (cause) {
      setInbox(null)
      setError(cause instanceof Error ? cause.message : 'Alert API unreachable')
    }
  }, [live])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const act = async (id: number, action: 'acknowledge' | 'resolve') => {
    setBusy(id)
    try {
      if (action === 'acknowledge') await acknowledgeAlert(id)
      else await resolveAlert(id)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const rows = useMemo(() => {
    if (!inbox) return []
    return filter === 'all'
      ? inbox.alerts
      : inbox.alerts.filter((alert) => alert.status === filter)
  }, [inbox, filter])

  const action = (
    <div className="flex items-center gap-2">
      <Badge tone="neutral">{inbox ? `${inbox.counts.open} open` : `${fallback.length} generated`}</Badge>
      {live && (
        <button
          onClick={() => void refresh()}
          className="rounded-[6px] border border-[var(--color-line)] p-1.5 text-muted hover:text-fg"
          title="Reload alerts"
        >
          <RefreshCw className="size-3.5" />
        </button>
      )}
    </div>
  )

  return (
    <Panel
      title="Alert inbox"
      subtitle={
        live
          ? 'Acknowledge and resolve alerts; state survives rebuilds'
          : 'Read-only build output — start the API to manage alerts'
      }
      action={action}
      bodyClassName="p-0"
    >
      {live && inbox && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--color-line)] px-3 py-2">
          {FILTERS.map((option) => {
            const count = option === 'all' ? inbox.counts.total : inbox.counts[option]
            return (
              <button
                key={option}
                onClick={() => setFilter(option)}
                className={`rounded-full px-2.5 py-1 text-[10.5px] capitalize transition ${
                  filter === option
                    ? 'bg-[var(--overlay-3)] text-fg ring-1 ring-inset ring-[var(--color-line-strong)]'
                    : 'text-muted hover:text-fg'
                }`}
              >
                {option} <span className="numeric text-faint">{number(count, 0)}</span>
              </button>
            )
          })}
          <span className="ml-auto flex items-center gap-1.5">
            <Label>Operator</Label>
            <span className="numeric text-[10.5px] text-muted">console-operator</span>
          </span>
        </div>
      )}

      {error && (
        <div className="border-b border-[var(--color-line)] px-3 py-2">
          <Note tone="warn">{error}</Note>
        </div>
      )}

      {live && inbox ? (
        <Table head={['Asset', 'Severity', 'Signal', 'Message', 'Cycle', 'Status', 'Actions']}>
          {rows.map((alert) => (
            <Row key={alert.id}>
              <Cell>
                <button
                  className="text-fg hover:text-[var(--color-accent)]"
                  onClick={() => navigate(`/assets/${alert.asset_id}`)}
                >
                  {alert.label}
                </button>
              </Cell>
              <Cell>
                <Badge tone={alert.severity}>{alert.severity}</Badge>
              </Cell>
              <Cell className="text-faint">{alert.kind}</Cell>
              <Cell className="max-w-[380px] truncate whitespace-normal text-muted">{alert.message}</Cell>
              <Cell className="numeric text-muted">{alert.cycle}</Cell>
              <Cell>
                <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
              </Cell>
              <Cell>
                <div className="flex items-center gap-1.5">
                  {alert.status === 'open' && (
                    <button
                      disabled={busy === alert.id}
                      onClick={() => void act(alert.id, 'acknowledge')}
                      className="inline-flex items-center gap-1 rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted hover:text-fg disabled:opacity-40"
                    >
                      <Check className="size-3" /> Ack
                    </button>
                  )}
                  {alert.status !== 'resolved' && (
                    <button
                      disabled={busy === alert.id}
                      onClick={() => void act(alert.id, 'resolve')}
                      className="inline-flex items-center gap-1 rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted hover:text-[var(--color-good)] disabled:opacity-40"
                    >
                      <CheckCheck className="size-3" /> Resolve
                    </button>
                  )}
                  {alert.status === 'resolved' && (
                    <span className="text-[10.5px] text-faint">
                      {alert.resolved_by} · {alert.resolved_at?.slice(0, 16).replace('T', ' ')}
                    </span>
                  )}
                  {alert.status === 'acknowledged' && (
                    <span className="text-[10.5px] text-faint">by {alert.acknowledged_by}</span>
                  )}
                </div>
              </Cell>
            </Row>
          ))}
          {rows.length === 0 && (
            <Row>
              <Cell className="text-muted">
                {inbox.counts.total === 0
                  ? 'No alerts recorded yet. Run the build pipeline to generate them.'
                  : `No ${filter === 'all' ? '' : `${filter} `}alerts.`}
              </Cell>
            </Row>
          )}
        </Table>
      ) : (
        <Table head={['Asset', 'Severity', 'Score', 'Cycle', 'Signal', 'Affected channels', '']}>
          {fallback.map((alert, index) => (
            <Row key={`${alert.asset_id}-${index}`} onClick={() => navigate(`/assets/${alert.asset_id}`)}>
              <Cell className="text-fg">{alert.label}</Cell>
              <Cell>
                <Badge tone={alert.severity}>{alert.severity}</Badge>
              </Cell>
              <Cell className="numeric">{number(alert.score, 2)}</Cell>
              <Cell className="numeric text-muted">{alert.cycle}</Cell>
              <Cell className="max-w-[420px] truncate whitespace-normal text-muted">{alert.message}</Cell>
              <Cell className="text-faint">{alert.sensors.join(' · ') || '—'}</Cell>
              <Cell>
                <span className="text-[10px] text-faint">read-only</span>
              </Cell>
            </Row>
          ))}
          {fallback.length === 0 && (
            <Row>
              <Cell className="text-muted">No high-severity anomaly alerts in this build.</Cell>
            </Row>
          )}
        </Table>
      )}

      {live && inbox && (
        <div className="border-t border-[var(--color-line)] px-3 py-2 text-[10.5px] text-faint">
          Transitions are stored in the metadata database with actor and timestamp; acknowledged and
          resolved alerts are never deleted by a rebuild.
        </div>
      )}
    </Panel>
  )
}
