import { motion } from 'framer-motion'
import { ArrowDown, CheckCircle2, Database, Network, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ErrorNotice, PageTitle, Panel, StatCard } from '../components/ui'
import { api } from '../services/api'
import type { SystemSettings, SystemStatus } from '../types'

const architecture = [
  { phase: 'INPUTS', title: 'Seven validated network factors', description: 'Traffic type, threat, congestion, available bandwidth, application priority, device trust, and latency. Values are validated by the existing NetworkInput/API rules.' },
  { phase: 'PHASE 1', title: 'Multi-factor QoS decision context', description: 'Existing normalization, dynamic weights, weighted decision score, policy selection, allocation recommendation, security action, and factor contributions are preserved as the native Phase 1 result.' },
  { phase: 'PHASE 2', title: 'QoS utility and security admissibility', description: 'Existing risk-aware evaluator calculates QoS utility and raw security risk, applies configured R_MAX admissibility, and selects the best available risk-aware policy.' },
  { phase: 'PHASE 3', title: 'Temporal threat awareness', description: 'Caller-supplied prior smoothed threat feeds the existing EWMA/trend implementation. Temporal adjustment produces effective risk without hidden history.' },
  { phase: 'PHASE 4', title: 'Policy stability and hysteresis', description: 'Caller-supplied previous policy enters existing hysteresis. Switching cost and stability-aware objective are reported separately; the objective does not rerank candidates. Risk-budget breach forces quarantine.' },
  { phase: 'PHASE 5', title: 'Read-only telemetry and optional enforcement', description: 'The existing closed-loop telemetry path adapts collected telemetry and supports explicit opt-in QoS enforcement. It is separate from the integrated Phase 1–4 UI decision API; this dashboard only displays telemetry and does not enforce.' },
  { phase: 'PHASE 6', title: 'Software ablation and controlled experiment harness', description: 'A fixed scenario matrix supports reproducible Phase 1–4 comparisons and descriptive metrics. Mininet measurements are separate controlled-testbed observations; no live testbed values are fabricated.' },
]

export function ArchitecturePage() {
  return (
    <div>
      <PageTitle
        eyebrow="Adaptive Smart QoS · research prototype"
        title="Integrated system architecture"
        description="A presentation view of implemented components and boundaries. The integrated controller orchestrates Phase 1–4; telemetry/enforcement and experimental measurement remain separate paths."
      />
      <div className="mx-auto max-w-3xl">
        {architecture.map((step, index) => (
          <div key={step.title}>
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.04 }}
              className="flex gap-4 rounded-2xl border border-slate-800 bg-slate-900/65 p-4 sm:p-5"
            >
              <div className="grid h-9 min-w-16 shrink-0 place-items-center rounded-xl border border-cyan-500/20 bg-cyan-500/[0.06] px-2 text-[9px] font-semibold text-cyan-200">{step.phase}</div>
              <div>
                <h3 className="text-sm font-semibold text-white">{step.title}</h3>
                <p className="mt-1 text-xs leading-5 text-slate-400">{step.description}</p>
              </div>
              {index === architecture.length - 1 ? <CheckCircle2 className="ml-auto h-5 w-5 shrink-0 text-emerald-300" /> : null}
            </motion.div>
            {index < architecture.length - 1 ? <div className="flex h-8 justify-start pl-7"><ArrowDown className="h-5 w-5 text-cyan-500/50" /></div> : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export function SettingsPage({
  status,
  statusError,
}: {
  status: SystemStatus
  statusError: string
}) {
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.settings()
      .then((data) => { if (active) { setSettings(data); setError('') } })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Configuration could not be loaded.')
      })
    return () => { active = false }
  }, [])

  return (
    <div>
      <PageTitle
        eyebrow="Platform configuration"
        title="System status and settings"
        description="Read-only operational settings are served from the current backend configuration. Thresholds and baseline weights are not modified here."
      />
      {statusError || error ? <div className="mb-5"><ErrorNotice>{statusError || error}</ErrorNotice></div> : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="FastAPI service" value={status.api_connected ? 'Online' : 'Unavailable'} detail="Status probe" tone={status.api_connected ? 'green' : 'rose'} />
        <StatCard label="Decision engine" value={status.api_connected ? 'Active' : 'Unavailable'} detail="Python baseline" tone={status.api_connected ? 'cyan' : 'rose'} />
        <StatCard label="Database" value={status.database_connected ? 'Connected' : 'Unavailable'} detail="SQLite · SQLAlchemy" tone={status.database_connected ? 'green' : 'rose'} />
        <StatCard label="Control mode" value={settings?.control_mode ?? 'Loading'} detail="No physical device control" tone="blue" />
      </div>
      {settings ? (
        <Panel className="mt-6">
          <h3 className="text-sm font-semibold text-white">Runtime information</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <RuntimeValue label="API endpoint" value={settings.api_endpoint} />
            <RuntimeValue label="SQLite database" value={settings.database_location} />
            <RuntimeValue label="Application version" value={settings.application_version} />
            <RuntimeValue label="Baseline status" value={settings.baseline_status} />
          </div>
        </Panel>
      ) : null}
      {settings ? (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <ConfigCard title="Baseline decision weights" values={settings.weights} format={(value) => `${(value * 100).toFixed(1)}%`} />
          <ConfigCard title="QoS policy thresholds" values={settings.policy_thresholds} />
          <ConfigCard title="Security thresholds" values={settings.security_thresholds} />
          <ConfigCard title="Traffic type score mapping" values={settings.traffic_type_scores} />
        </div>
      ) : null}
      <Panel className="mt-6">
        <div className="flex items-start gap-3">
          <Database className="mt-0.5 h-5 w-5 text-cyan-300" />
          <div>
            <h3 className="text-sm font-semibold text-white">Persistence information</h3>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              Decision, scenario, and simulation records are held in the project SQLite database and accessed through SQLAlchemy. Use Decision History to inspect or explicitly remove a saved decision.
            </p>
          </div>
          <Network className="ml-auto h-5 w-5 text-slate-600" />
          <ShieldCheck className="h-5 w-5 text-emerald-300" />
        </div>
      </Panel>
    </div>
  )
}

function RuntimeValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm font-medium text-slate-200">{value}</p>
    </div>
  )
}

function ConfigCard({
  title,
  values,
  format = (value: number) => String(value),
}: {
  title: string
  values: Record<string, number>
  format?: (value: number) => string
}) {
  return (
    <Panel>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <div className="mt-3 divide-y divide-slate-800/80">
        {Object.entries(values).map(([name, value]) => (
          <div key={name} className="flex items-center justify-between gap-4 py-2.5 text-xs">
            <span className="text-slate-400">{name.replaceAll('_', ' ')}</span>
            <span className="font-medium text-slate-200">{format(value)}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}
