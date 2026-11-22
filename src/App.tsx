import { lazy, Suspense } from 'react'

import { AppShell } from './components/layout/AppShell'
import { DataProvider } from './lib/data-context'
import { usePath } from './lib/router'
import { ThemeProvider } from './lib/theme'
import { useSentinelData } from './lib/useSentinelData'

// Route-level code splitting: each page ships only when it is first opened.
const FleetOverview = lazy(() => import('./pages/FleetOverview').then((m) => ({ default: m.FleetOverview })))
const LiveMonitoring = lazy(() => import('./pages/LiveMonitoring').then((m) => ({ default: m.LiveMonitoring })))
const DigitalTwin = lazy(() => import('./pages/DigitalTwin').then((m) => ({ default: m.DigitalTwin })))
const MachineIntelligence = lazy(() => import('./pages/MachineIntelligence').then((m) => ({ default: m.MachineIntelligence })))
const PredictiveAnalytics = lazy(() => import('./pages/PredictiveAnalytics').then((m) => ({ default: m.PredictiveAnalytics })))
const AnomalyCentre = lazy(() => import('./pages/AnomalyCentre').then((m) => ({ default: m.AnomalyCentre })))
const RULIntelligence = lazy(() => import('./pages/RULIntelligence').then((m) => ({ default: m.RULIntelligence })))
const ForecastPage = lazy(() => import('./pages/ForecastPage').then((m) => ({ default: m.ForecastPage })))
const Explainability = lazy(() => import('./pages/Explainability').then((m) => ({ default: m.Explainability })))
const MaintenanceOptimiser = lazy(() => import('./pages/MaintenanceOptimiser').then((m) => ({ default: m.MaintenanceOptimiser })))
const HistoricalAnalytics = lazy(() => import('./pages/HistoricalAnalytics').then((m) => ({ default: m.HistoricalAnalytics })))
const ModelLaboratory = lazy(() => import('./pages/ModelLaboratory').then((m) => ({ default: m.ModelLaboratory })))
const DatasetManagement = lazy(() => import('./pages/DatasetManagement').then((m) => ({ default: m.DatasetManagement })))
const DataOnboarding = lazy(() => import('./pages/DataOnboarding').then((m) => ({ default: m.DataOnboarding })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const AssetDetail = lazy(() => import('./pages/AssetDetail').then((m) => ({ default: m.AssetDetail })))

function RouteFallback() {
  return (
    <div className="grid min-h-[40vh] place-items-center">
      <div className="flex items-center gap-3 text-[12px] text-muted">
        <span className="size-2 animate-[pulse-soft_1.4s_ease-in-out_infinite] rounded-full bg-[var(--color-accent)]" />
        Loading view…
      </div>
    </div>
  )
}

function Routes() {
  const path = usePath()
  if (path.startsWith('/assets/')) {
    return <AssetDetail assetId={decodeURIComponent(path.replace('/assets/', ''))} />
  }
  switch (path) {
    case '/twins':
      return <DigitalTwin />
    case '/assets':
      return <MachineIntelligence />
    case '/predictive':
      return <PredictiveAnalytics />
    case '/anomalies':
      return <AnomalyCentre />
    case '/live':
      return <LiveMonitoring />
    case '/rul':
      return <RULIntelligence />
    case '/forecast':
      return <ForecastPage />
    case '/explainability':
      return <Explainability />
    case '/maintenance':
      return <MaintenanceOptimiser />
    case '/analytics':
      return <HistoricalAnalytics />
    case '/models':
      return <ModelLaboratory />
    case '/datasets':
      return <DatasetManagement />
    case '/onboarding':
      return <DataOnboarding />
    case '/settings':
      return <SettingsPage />
    default:
      return <FleetOverview />
  }
}

export function App() {
  const { dataset, loading, refresh } = useSentinelData()

  return (
    <ThemeProvider>
      {loading || !dataset ? (
        <div className="grid min-h-screen place-items-center bg-bg">
          <div className="flex items-center gap-3 text-[12px] text-muted">
            <span className="size-2 animate-[pulse-soft_1.4s_ease-in-out_infinite] rounded-full bg-[var(--color-accent)]" />
            Loading SENTINEL artifacts…
          </div>
        </div>
      ) : (
        <DataProvider value={dataset}>
          <AppShell dataset={dataset} refresh={refresh}>
            <Suspense fallback={<RouteFallback />}>
              <Routes />
            </Suspense>
          </AppShell>
        </DataProvider>
      )}
    </ThemeProvider>
  )
}
