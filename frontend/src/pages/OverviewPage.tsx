import { ArrowRight, Activity, Database, Network, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState, ErrorNotice, Panel, StatCard, formatDate, policyTone } from '../components/ui'
import { api } from '../services/api'
import type { AnalyticsSummary, DecisionRecord, SystemStatus, TestbedStatus } from '../types'

type OverviewPageProps = {
  status: SystemStatus
  onNavigate: (page: 'engine' | 'simulation' | 'testbed' | 'history' | 'analytics' | 'scenarios' | 'architecture' | 'settings') => void
}

export function OverviewPage({ status, onNavigate }: OverviewPageProps) {
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const [recent, setRecent] = useState<DecisionRecord[]>([])
  const [error, setError] = useState('')
  const [testbed, setTestbed] = useState<TestbedStatus | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([
      api.analytics(),
      api.decisions(new URLSearchParams({ limit: '6' })),
      api.testbedStatus(),
    ])
      .then(([summary, history, testbedStatus]) => {
        if (!active) return
        setAnalytics(summary)
        setRecent(history.items)
        setTestbed(testbedStatus)
        setError('')
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Unable to load overview data.')
      })
    return () => {
      active = false
    }
  }, [])

  const latest = recent[0]

  return (
    <div className="space-y-6">
      <Panel className="relative">
        <div className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr] lg:items-center">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/[0.06] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
              <Network className="h-3.5 w-3.5" />
              Integrated research controller · Phases 1–6
            </div>
            <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Adaptive Smart QoS</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
              Continuous traffic evaluation for latency, security posture, priority, and network state.
              Review a clear recommendation, its rationale, and the decisions already recorded.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onNavigate('engine')}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
              >
                Run Decision <ArrowRight className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => onNavigate('simulation')}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/60"
              >
                Open simulation lab
              </button>
              <button type="button" onClick={() => onNavigate('architecture')} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/60">View architecture</button>
              <button type="button" onClick={() => onNavigate('analytics')} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/60">View analytics</button>
              <button type="button" onClick={() => onNavigate('testbed')} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-slate-800/60">Live Testbed</button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <StatusTile label="System online" active={status.api_connected} icon={<Activity className="h-4 w-4" />} />
            <StatusTile label="Decision engine active" active={status.api_connected} icon={<ShieldCheck className="h-4 w-4" />} />
            <StatusTile label="SQLite database connected" active={status.database_connected} icon={<Database className="h-4 w-4" />} />
            <StatusTile label="Temporal risk active" active={status.temporal_risk_active} icon={<Activity className="h-4 w-4" />} />
            <StatusTile label="Policy stability active" active={status.stability_active} icon={<ShieldCheck className="h-4 w-4" />} />
            <StatusTile label={testbed?.connected ? 'Controlled testbed connected' : 'Testbed not connected'} active={Boolean(testbed?.connected)} icon={<Network className="h-4 w-4" />} />
          </div>
        </div>
      </Panel>

      {error ? <ErrorNotice>{error}</ErrorNotice> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Decisions recorded" value={analytics?.total_decisions ?? '—'} detail="Persistent SQLite history" />
        <StatCard
          label="Average decision score"
          value={analytics?.average_score == null ? '—' : analytics.average_score.toFixed(2)}
          detail="Across saved decisions"
          tone="blue"
        />
        <StatCard label="Security overrides" value={analytics?.security_overrides ?? '—'} detail="Restrict or quarantine outcomes" tone="amber" />
        <StatCard label="Most common policy" value={analytics?.most_common_policy ?? '—'} detail="From recorded outcomes" tone="green" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel>
          <div className="mb-4">
            <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Recorded outcomes</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Decision score over time</h3>
          </div>
          {analytics?.decision_score_over_time.length ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analytics.decision_score_over_time}>
                  <defs>
                    <linearGradient id="overviewScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#A78BFA" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#A78BFA" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
                  <XAxis dataKey="time" tickFormatter={(v: string) => new Date(v).toLocaleTimeString()} stroke="#A7ADBA" fontSize={10} />
                  <YAxis domain={[0, 100]} stroke="#A7ADBA" fontSize={10} />
                  <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                  <Area type="monotone" dataKey="value" stroke="#A78BFA" strokeWidth={2} fill="url(#overviewScore)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No decision data yet" detail="Run an analysis or simulation to populate the overview with actual stored results." />
          )}
        </Panel>

        <Panel>
          <div className="mb-4 flex items-end justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Persistent activity</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Recent decisions</h3>
            </div>
            <button type="button" onClick={() => onNavigate('history')} className="text-xs text-cyan-200 hover:text-white">
              View history
            </button>
          </div>
          {recent.length ? (
            <div className="space-y-2">
              {recent.slice(0, 5).map((record) => (
                <div key={record.id} className="rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-medium text-slate-100">{record.input.traffic_type}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${policyTone(record.result.security_action)}`}>
                      {record.result.security_action}
                    </span>
                  </div>
                  <div className="mt-2 flex justify-between gap-3 text-xs text-slate-500">
                    <span>{record.result.qos_policy} · score {record.result.decision_score.toFixed(2)}</span>
                    <time>{formatDate(record.created_at)}</time>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="History is empty" detail="Saved decisions will appear here after an analysis." />
          )}
          {latest ? (
            <p className="mt-4 text-xs leading-5 text-slate-500">
              Latest recommendation: {latest.result.priority} priority via {latest.result.queue}.
            </p>
          ) : null}
        </Panel>
      </div>
    </div>
  )
}

function StatusTile({
  label,
  active,
  icon,
}: {
  label: string
  active: boolean
  icon: React.ReactNode
}) {
  return (
    <div className={`flex items-center gap-3 rounded-xl border px-3 py-3 ${
      active ? 'border-emerald-400/15 bg-emerald-400/[0.04]' : 'border-rose-400/20 bg-rose-400/[0.04]'
    }`}>
      <span className={active ? 'text-emerald-300' : 'text-rose-300'}>{icon}</span>
      <span className="flex-1 text-xs text-slate-300">{label}</span>
      <span className={`h-2 w-2 rounded-full ${active ? 'bg-emerald-400' : 'bg-rose-400'}`} />
    </div>
  )
}
