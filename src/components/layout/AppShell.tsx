import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronRight,
  Cpu,
  Database,
  FlaskConical,
  Gauge,
  History,
  LayoutDashboard,
  Menu,
  PlugZap,
  Radio,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Wrench,
  X,
  Wifi,
} from 'lucide-react'
import { useState } from 'react'

import { AssistantDock } from '../assistant/AssistantDock'
import type { DatasetState } from '../../lib/api'
import { cx } from '../../lib/cx'
import { navigate, usePath } from '../../lib/router'
import { relativeTime } from '../../lib/format'
import { ThemeMenu } from './ThemeMenu'

const NAV = [
  {
    group: 'Operations',
    items: [
      { href: '/', label: 'Fleet Overview', icon: LayoutDashboard },
      { href: '/live', label: 'Live Monitoring', icon: Wifi },
      { href: '/twins', label: 'Digital Twin', icon: Cpu },
      { href: '/assets', label: 'Machine Intelligence', icon: Gauge },
      { href: '/predictive', label: 'Predictive Analytics', icon: Activity },
      { href: '/anomalies', label: 'Anomaly Centre', icon: AlertTriangle },
      { href: '/rul', label: 'RUL Intelligence', icon: History },
      { href: '/forecast', label: 'Forecasting', icon: TrendingUp },
    ],
  },
  {
    group: 'Intelligence',
    items: [
      { href: '/explainability', label: 'Explainable AI', icon: Sparkles },
      { href: '/maintenance', label: 'Maintenance Optimiser', icon: Wrench },
      { href: '/analytics', label: 'Historical Analytics', icon: Radio },
    ],
  },
  {
    group: 'Platform',
    items: [
      { href: '/models', label: 'Model Laboratory', icon: FlaskConical },
      { href: '/onboarding', label: 'Data Onboarding', icon: PlugZap },
      { href: '/datasets', label: 'Dataset Management', icon: Database },
      { href: '/settings', label: 'System Settings', icon: Settings },
    ],
  },
]

const TITLES: Record<string, string> = {
  '/': 'Fleet Overview',
  '/live': 'Live Monitoring',
  '/twins': 'Machine Twin Studio',
  '/assets': 'Machine Intelligence',
  '/predictive': 'Predictive Analytics',
  '/anomalies': 'Anomaly Detection Centre',
  '/rul': 'RUL Intelligence',
  '/forecast': 'Sensor Forecasting',
  '/explainability': 'Explainable AI',
  '/maintenance': 'Maintenance Optimiser',
  '/analytics': 'Historical Analytics',
  '/models': 'Model Laboratory',
  '/onboarding': 'Plant Data Onboarding',
  '/datasets': 'Dataset Management',
  '/settings': 'System Settings',
}

export function AppShell({
  dataset,
  children,
  refresh,
}: {
  dataset: DatasetState
  children: React.ReactNode
  refresh: () => void
}) {
  const path = usePath()
  const [open, setOpen] = useState(false)
  const title = path.startsWith('/assets/') ? 'Machine Digital Twin' : (TITLES[path] ?? 'SENTINEL')
  const snapshot = dataset.data
  const live = dataset.source === 'live'

  return (
    <div className="flex min-h-screen bg-bg text-fg">
      {open && (
        <button className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)}
          aria-label="Close navigation" />
      )}
      <aside
        className={cx(
          'fixed inset-y-0 left-0 z-40 flex w-[244px] flex-col border-r border-[var(--color-line)] bg-[var(--color-bg-deep)] transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-2.5 px-4 py-4">
          <div className="relative grid size-8 place-items-center rounded-[9px] border border-[var(--accent-line)] bg-[var(--accent-soft)]">
            <ShieldCheck className="size-4 text-[var(--color-accent)]" />
          </div>
          <div className="leading-tight">
            <div className="text-[13.5px] font-semibold tracking-[0.16em]">SENTINEL</div>
            <div className="text-[9px] uppercase tracking-[0.14em] text-faint">Industrial Intelligence</div>
          </div>
          <button className="ml-auto text-faint lg:hidden" onClick={() => setOpen(false)} aria-label="Close">
            <X className="size-4" />
          </button>
        </div>

        <div className="mx-3 mb-3 rounded-[9px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-2">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.1em] text-faint">
            <span>Active fleet</span>
            <span className="numeric text-[var(--color-accent)]">{snapshot.fleet.summary.total}</span>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-muted">
            {snapshot.meta.dataset_versions.cmapss ? `C-MAPSS ${snapshot.settings.cmapss_subset}` : 'C-MAPSS'}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {NAV.map((section) => (
            <div key={section.group} className="mb-4">
              <div className="px-3 pb-1.5 text-[9.5px] font-medium uppercase tracking-[0.16em] text-faint">
                {section.group}
              </div>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const active = path === item.href || (item.href !== '/' && path.startsWith(item.href))
                  return (
                    <li key={item.href}>
                      <button
                        onClick={() => { navigate(item.href); setOpen(false) }}
                        className={cx(
                          'group flex w-full items-center gap-2.5 rounded-[8px] px-3 py-[7px] text-left text-[12px] transition-colors',
                          active
                            ? 'bg-[var(--accent-soft)] text-fg'
                            : 'text-muted hover:bg-[var(--overlay-2)] hover:text-fg',
                        )}
                      >
                        <item.icon className={cx('size-[15px]', active ? 'text-[var(--color-accent)]' : 'text-faint group-hover:text-muted')} />
                        <span className="truncate">{item.label}</span>
                        {active && <span className="ml-auto size-1 rounded-full bg-[var(--color-accent)]" />}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-[var(--color-line)] px-4 py-3 text-[10px] text-faint">
          <div className="flex items-center justify-between">
            <span>Build</span>
            <span className="numeric">{snapshot.meta.build_version}</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span>Artifacts</span>
            <span className="numeric">{relativeTime(snapshot.meta.generated_at)}</span>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-[54px] items-center gap-3 border-b border-[var(--color-line)] bg-[var(--header-bg)] px-4 backdrop-blur">
          <button className="text-muted lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
            <Menu className="size-5" />
          </button>
          <div className="flex min-w-0 items-center gap-1.5 text-[12px]">
            <span className="hidden text-faint sm:inline">Command centre</span>
            <ChevronRight className="hidden size-3 text-faint sm:inline" />
            <span className="truncate font-medium">{title}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span
              className={cx(
                'hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.08em] sm:inline-flex',
                live
                  ? 'border-[var(--good-line)] bg-[var(--good-soft)] text-[var(--color-good)]'
                  : 'border-[var(--color-line-strong)] bg-[var(--overlay-1)] text-muted',
              )}
              title={live ? 'Reading live FastAPI responses' : `API unavailable (${dataset.error}). Showing exported build artifacts.`}
            >
              <span className={cx('size-1.5 rounded-full bg-current', live && 'animate-[pulse-soft_2.6s_ease-in-out_infinite]')} />
              {live ? 'Live API' : 'Snapshot'}
            </span>
            <ThemeMenu />
            <button
              onClick={refresh}
              className="flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted transition-colors hover:border-[var(--color-line-strong)] hover:text-fg"
              title="Reload data"
            >
              <RefreshCw className="size-3.5" />
              <span className="hidden sm:inline">Refresh</span>
            </button>
            <div className="hidden items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted md:flex">
              <Bell className="size-3.5" />
              <span className="numeric">{snapshot.alerts.length}</span>
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 px-4 py-4 lg:px-6 lg:py-5">{children}</main>
      </div>

      <AssistantDock />
    </div>
  )
}
