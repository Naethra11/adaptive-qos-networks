import {
  Activity,
  BarChart3,
  ChevronRight,
  FlaskConical,
  History,
  Home,
  Layers3,
  RadioTower,
  Menu,
  Network,
  Settings2,
  ShieldCheck,
  X,
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { DecisionEnginePage } from './pages/DecisionEnginePage'
import { DecisionHistoryPage } from './pages/DecisionHistoryPage'
import { OverviewPage } from './pages/OverviewPage'
import { ScenariosPage } from './pages/ScenariosPage'
import { SimulationLabPage } from './pages/SimulationLabPage'
import { LiveTestbedPage } from './pages/LiveTestbedPage'
import { ArchitecturePage, SettingsPage } from './pages/SystemPages'
import { api } from './services/api'
import type { Scenario, SystemStatus } from './types'

const navigation = [
  { id: 'overview', label: 'Overview', icon: Home },
  { id: 'engine', label: 'Decision Engine', icon: Activity },
  { id: 'simulation', label: 'Simulation Lab', icon: FlaskConical },
  { id: 'testbed', label: 'Live Testbed', icon: RadioTower },
  { id: 'history', label: 'Decision History', icon: History },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'scenarios', label: 'Scenarios', icon: Layers3 },
  { id: 'architecture', label: 'System Architecture', icon: Network },
  { id: 'settings', label: 'Settings', icon: Settings2 },
] as const

type PageId = (typeof navigation)[number]['id']

function StatusBadge({ label, connected }: { label: string; connected: boolean }) {
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
        connected
          ? 'border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-200'
          : 'border-rose-400/25 bg-rose-400/5 text-rose-200'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          connected ? 'bg-emerald-400' : 'bg-rose-400'
        }`}
      />
      {label}: {connected ? 'Connected' : 'Unavailable'}
    </div>
  )
}

function App() {
  const [page, setPage] = useState<PageId>('overview')
  const [status, setStatus] = useState<SystemStatus>({
    api_connected: false,
    database_connected: false,
    database: 'SQLite',
    decision_engine_active: false,
    temporal_risk_active: false,
    stability_active: false,
  })
  const [statusError, setStatusError] = useState('')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [requestedScenario, setRequestedScenario] = useState<Scenario | null>(null)

  useEffect(() => {
    let active = true
    const refreshStatus = async () => {
      try {
        const nextStatus = await api.status()
        if (active) {
          setStatus(nextStatus)
          setStatusError('')
        }
      } catch (error) {
        if (active) {
          setStatus({
            api_connected: false,
            database_connected: false,
            database: 'SQLite',
            decision_engine_active: false,
            temporal_risk_active: false,
            stability_active: false,
          })
          setStatusError(error instanceof Error ? error.message : 'Status check failed.')
        }
      }
    }

    void refreshStatus()
    const timer = window.setInterval(() => void refreshStatus(), 30000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const navigate = (target: PageId) => {
    setPage(target)
    setMobileMenuOpen(false)
  }

  const runScenario = (scenario: Scenario) => {
    setRequestedScenario(scenario)
    navigate('engine')
  }

  const currentPage = navigation.find((item) => item.id === page)
  const pageContent = (() => {
    switch (page) {
      case 'overview':
        return <OverviewPage status={status} onNavigate={navigate} />
      case 'engine':
        return (
          <DecisionEnginePage
            initialScenario={requestedScenario}
            onScenarioConsumed={() => setRequestedScenario(null)}
          />
        )
      case 'simulation':
        return <SimulationLabPage />
      case 'testbed':
        return <LiveTestbedPage />
      case 'history':
        return <DecisionHistoryPage />
      case 'analytics':
        return <AnalyticsPage />
      case 'scenarios':
        return <ScenariosPage onRunScenario={runScenario} />
      case 'architecture':
        return <ArchitecturePage />
      case 'settings':
        return <SettingsPage status={status} statusError={statusError} />
    }
  })()

  const navigationButtons = (
    <nav aria-label="Main navigation" className="space-y-1">
      {navigation.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => navigate(id)}
          aria-current={page === id ? 'page' : undefined}
          className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${
            page === id
              ? 'border border-violet-400/25 border-l-2 border-l-violet-400 bg-violet-400/[0.08] text-violet-100'
              : 'border border-transparent text-slate-400 hover:bg-slate-800/70 hover:text-slate-100'
          }`}
        >
          <Icon className={`h-4 w-4 ${page === id ? 'text-cyan-300' : 'text-slate-500 group-hover:text-slate-300'}`} />
          <span className="flex-1">{label}</span>
          {page === id ? <ChevronRight className="h-3.5 w-3.5 text-cyan-300" /> : null}
        </button>
      ))}
    </nav>
  )

  return (
    <div className="min-h-screen bg-[var(--console-bg)] text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-800 bg-[var(--console-sidebar)] px-4 py-5 lg:flex">
        <div className="mb-8 flex items-center gap-3 px-2">
          <div className="rounded-xl border border-cyan-400/25 bg-cyan-400/10 p-2 text-cyan-200">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wide text-white">Adaptive QoS</div>
            <div className="mt-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-500">Network intelligence</div>
          </div>
        </div>

        <div className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
          Workspace
        </div>
        {navigationButtons}

        <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
            <ShieldCheck className="h-4 w-4 text-cyan-300" />
            Integrated research controller
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Phases 1–6 · software decisions and controlled testbed tools.
          </p>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-slate-800 bg-[var(--console-header)] px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="rounded-lg border border-slate-700 p-2 text-slate-300 lg:hidden"
                aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
                onClick={() => setMobileMenuOpen((open) => !open)}
              >
                {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
              </button>
              <div>
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Adaptive Network Intelligence Platform</p>
                <h1 className="mt-0.5 text-sm font-semibold text-white sm:text-base">{currentPage?.label}</h1>
              </div>
            </div>
            <div className="hidden flex-wrap justify-end gap-2 md:flex">
              <StatusBadge label="API" connected={status.api_connected} />
              <StatusBadge label="Database" connected={status.database_connected} />
            </div>
          </div>

          <AnimatePresence>
            {mobileMenuOpen ? (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden lg:hidden"
              >
                <div className="mt-4 border-t border-slate-800 pt-3">{navigationButtons}</div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </header>

        <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          {!status.api_connected ? (
            <div role="alert" className="mb-5 rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              Backend unavailable. Start FastAPI with <code className="rounded bg-black/20 px-1.5 py-0.5">uvicorn api:app --host 0.0.0.0 --port 8000</code> from the project root, then refresh. {statusError}
            </div>
          ) : null}
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.18 }}
            >
              {pageContent}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}

export default App
