import { AppShell } from './components/layout/AppShell'
import { DataProvider } from './lib/data-context'
import { usePath } from './lib/router'
import { useSentinelData } from './lib/useSentinelData'
import { AnomalyCentre } from './pages/AnomalyCentre'
import { AssetDetail } from './pages/AssetDetail'
import { MachineIntelligence } from './pages/MachineIntelligence'
import { DatasetManagement } from './pages/DatasetManagement'
import { Explainability } from './pages/Explainability'
import { FleetOverview } from './pages/FleetOverview'
import { ForecastPage } from './pages/ForecastPage'
import { HistoricalAnalytics } from './pages/HistoricalAnalytics'
import { LiveMonitoring } from './pages/LiveMonitoring'
import { MaintenanceOptimiser } from './pages/MaintenanceOptimiser'
import { ModelLaboratory } from './pages/ModelLaboratory'
import { PredictiveAnalytics } from './pages/PredictiveAnalytics'
import { RULIntelligence } from './pages/RULIntelligence'
import { SettingsPage } from './pages/SettingsPage'

function Routes() {
  const path = usePath()
  if (path.startsWith('/assets/')) {
    return <AssetDetail assetId={decodeURIComponent(path.replace('/assets/', ''))} />
  }
  switch (path) {
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
    case '/settings':
      return <SettingsPage />
    default:
      return <FleetOverview />
  }
}

export function App() {
  const { dataset, loading, refresh } = useSentinelData()

  if (loading || !dataset) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg">
        <div className="flex items-center gap-3 text-[12px] text-muted">
          <span className="size-2 animate-[pulse-soft_1.4s_ease-in-out_infinite] rounded-full bg-[var(--color-accent)]" />
          Loading SENTINEL artifacts…
        </div>
      </div>
    )
  }

  return (
    <DataProvider value={dataset}>
      <AppShell dataset={dataset} refresh={refresh}>
        <Routes />
      </AppShell>
    </DataProvider>
  )
}
