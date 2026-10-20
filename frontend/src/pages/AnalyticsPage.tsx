import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState, ErrorNotice, PageTitle, Panel, StatCard } from '../components/ui'
import { api } from '../services/api'
import type { AblationResponse, AnalyticsSummary } from '../types'

const chartColors = ['#A78BFA', '#F5B942', '#45C98A', '#D69E35', '#EF6675', '#8B70DC', '#A7ADBA']

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [ablation, setAblation] = useState<AblationResponse | null>(null)
  const [selectedVariant, setSelectedVariant] = useState('PHASE4_STABILITY')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([api.analytics(), api.ablation()])
      .then(([data, ablationData]) => {
        if (active) { setSummary(data); setAblation(ablationData); setError('') }
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Analytics are unavailable.')
      })
    return () => { active = false }
  }, [])

  const hasData = Boolean(summary?.total_decisions)

  return (
    <div>
      <PageTitle
        eyebrow="SQLite-backed measurements"
        title="Analytics"
        description="Charts distinguish persisted decision history from fixed software-level ablation outputs. Missing or unavailable metrics remain unavailable; no synthetic results are inserted."
      />
      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      {ablation ? (
        <Panel className="mb-6">
          <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200">Fixed software-level scenario evaluation · separate from Mininet</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Phase 1–4 ablation analysis</h3>
          <p className="mt-1 text-xs text-slate-400">{ablation.summary.scenario_count} fixed scenarios, evaluated through {ablation.summary.variant_count} available variants. These are controller outputs, not throughput, latency, or packet-loss measurements.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(ablation.summary.policy_distribution).map(([variant, distribution]) => {
              const riskRate = ablation.summary.risk_constraint_violation_rate[variant]
              const utility = ablation.summary.mean_qos_utility[variant]
              const trend = ablation.summary.temporal_trend_counts[variant]
              const sequences = Object.values(ablation.summary.policy_switching_metrics[variant] ?? {})
              return (
                <div key={variant} className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
                  <h4 className="text-xs font-semibold text-white">{variant}</h4>
                  <p className="mt-2 text-xs text-slate-400">Utility: {utility == null ? 'Unavailable' : utility.toFixed(2)}</p>
                  <p className="mt-1 text-xs text-slate-400">Risk violations: {riskRate ? `${riskRate.numerator}/${riskRate.denominator} · ${(riskRate.rate ?? 0) * 100}%` : 'Unavailable'}</p>
                  <p className="mt-1 text-xs text-slate-400">Security overrides: {ablation.summary.security_override_rate[variant] ? `${ablation.summary.security_override_rate[variant]!.numerator}/${ablation.summary.security_override_rate[variant]!.denominator}` : 'Unavailable'}</p>
                  <p className="mt-1 text-xs text-slate-400">Policies: {Object.entries(distribution.counts ?? {}).filter(([, count]) => count > 0).map(([name, count]) => `${name} ${count}`).join(' · ') || '—'}</p>
                  <p className="mt-1 text-xs text-slate-400">Mean raw/effective risk: {ablation.summary.mean_raw_security_risk[variant] ?? 'Unavailable'} / {ablation.summary.mean_effective_security_risk[variant] ?? 'Unavailable'}</p>
                  <p className="mt-1 text-xs text-slate-400">Trends: {trend ? Object.entries(trend).map(([name, count]) => `${name.replace('TRENDING_', '')} ${count}`).join(' · ') : 'Unavailable'}</p>
                  <p className="mt-1 text-xs text-slate-400">PSR / PSI by sequence: {sequences.length ? sequences.map((item) => `${item.psr.toFixed(3)} / ${item.psi.toFixed(3)}`).join(' · ') : 'No ordered sequence'}</p>
                </div>
              )
            })}
          </div>
          <h4 className="mt-5 text-sm font-semibold text-white">Phase-to-phase absolute differences</h4>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {Object.entries(ablation.summary.phase_differences).map(([pair, differences]) => (
              <div key={pair} className="rounded-lg border border-slate-800 px-3 py-2 text-[11px]">
                <p className="font-medium text-cyan-100">{pair.replaceAll('_', ' ')}</p>
                <p className="mt-1 text-slate-400">Utility Δ {String(differences.mean_qos_utility ?? 'Unavailable')} · raw risk Δ {String(differences.mean_raw_security_risk ?? 'Unavailable')} · effective risk Δ {String(differences.mean_effective_security_risk ?? 'Unavailable')}</p>
              </div>
            ))}
          </div>
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-white">Per-scenario risk and utility</h4>
                <p className="mt-1 text-[11px] text-slate-500">Values are actual deterministic software evaluation outputs for the selected variant.</p>
              </div>
              <select aria-label="Ablation variant risk chart" value={selectedVariant} onChange={(event) => setSelectedVariant(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200">
                {Object.keys(ablation.summary.policy_distribution).map((variant) => <option key={variant}>{variant}</option>)}
              </select>
            </div>
            <div className="mt-3 grid gap-5 xl:grid-cols-2">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={ablation.runs.filter((run) => run.variant === selectedVariant).map((run) => ({
                    scenario: run.scenario_id,
                    rawRisk: run.result.raw_security_risk ?? null,
                    effectiveRisk: run.result.effective_security_risk ?? null,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
                    <XAxis dataKey="scenario" stroke="#A7ADBA" fontSize={8} interval={2} angle={-22} textAnchor="end" height={65} />
                    <YAxis domain={[0, 100]} stroke="#A7ADBA" fontSize={9} />
                    <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                    <Legend />
                    <Bar dataKey="rawRisk" name="Raw risk" fill="#A78BFA" />
                    <Bar dataKey="effectiveRisk" name="Effective risk" fill="#F5B942" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={ablation.runs.filter((run) => run.variant === selectedVariant).map((run) => ({
                    scenario: run.scenario_id,
                    utility: run.result.qos_utility ?? null,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
                    <XAxis dataKey="scenario" stroke="#A7ADBA" fontSize={8} interval={2} angle={-22} textAnchor="end" height={65} />
                    <YAxis domain={[0, 100]} stroke="#A7ADBA" fontSize={9} />
                    <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                    <Bar dataKey="utility" name="QoS utility" fill="#45C98A" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            {ablation.summary.hysteresis_effect ? (
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/35 p-3 text-xs">
                <p className="font-medium text-white">Hysteresis sequence · actual Phase 4 outputs</p>
                <p className="mt-1 text-slate-400">Candidate switches: {ablation.summary.hysteresis_effect.candidate_switch_count} · final switches: {ablation.summary.hysteresis_effect.final_switch_count}</p>
                <p className="mt-1 break-words text-slate-500">Candidate: {ablation.summary.hysteresis_effect.candidate_policies.join(' → ')}</p>
                <p className="mt-1 break-words text-slate-500">Final: {ablation.summary.hysteresis_effect.final_policies.join(' → ')}</p>
              </div>
            ) : null}
        </Panel>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label="Total decisions" value={summary?.total_decisions ?? '—'} detail="Stored decision records" />
        <StatCard label="Average decision score" value={summary?.average_score == null ? '—' : summary.average_score.toFixed(2)} detail="0–100 baseline score" tone="blue" />
        <StatCard label="Security overrides" value={summary?.security_overrides ?? '—'} detail="RESTRICT and QUARANTINE" tone="amber" />
        <StatCard label="Most common QoS policy" value={summary?.most_common_policy ?? '—'} detail="Most frequent recorded policy" tone="green" />
        <StatCard label="Average bandwidth allocation" value={summary?.average_bandwidth_allocation == null ? '—' : `${summary.average_bandwidth_allocation.toFixed(2)} Mbps`} detail="Recommended allocation" />
        <StatCard label="Average latency" value={summary?.average_latency == null ? '—' : `${summary.average_latency.toFixed(2)} ms`} detail="Raw input latency" tone="blue" />
      </div>

      {!hasData ? (
        <div className="mt-6"><Panel><EmptyState title="No analytics records yet" detail="Run one or more decisions or a scenario simulation. Charts will be derived from the saved SQLite records." /></Panel></div>
      ) : (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <TimeChart title="Decision score over time" data={summary!.decision_score_over_time} />
          <TimeChart title="Threat level over time · raw / 10" data={summary!.threat_level_over_time} />
          <TimeChart title="Congestion over time · raw / 10" data={summary!.congestion_over_time} />
          <Distribution title="Policy distribution" data={summary!.policy_distribution} />
          <Distribution title="Security action distribution" data={summary!.security_distribution} />
          <Distribution title="Traffic type distribution" data={summary!.traffic_distribution} />
        </div>
      )}
    </div>
  )
}

function TimeChart({
  title,
  data,
}: {
  title: string
  data: AnalyticsSummary['decision_score_over_time']
}) {
  const isScore = title.startsWith('Decision score')
  return (
    <Panel>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <div className="mt-4 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
            <XAxis dataKey="time" tickFormatter={(value: string) => new Date(value).toLocaleTimeString()} stroke="#A7ADBA" fontSize={9} />
            <YAxis domain={isScore ? [0, 100] : [0, 10]} stroke="#A7ADBA" fontSize={9} />
            <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
            <Line type="monotone" dataKey="value" name={title} stroke={isScore ? '#A78BFA' : '#F5B942'} strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  )
}

function Distribution({ title, data }: { title: string; data: Array<{ name: string; value: number }> }) {
  return (
    <Panel>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_0.9fr]">
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            {title === 'Policy distribution' ? (
              <BarChart data={data} layout="vertical" margin={{ left: 15, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" horizontal={false} />
                <XAxis type="number" stroke="#A7ADBA" fontSize={9} allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={115} stroke="#A7ADBA" fontSize={9} />
                <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                <Bar dataKey="value" fill="#A78BFA" radius={[0, 5, 5, 0]} />
              </BarChart>
            ) : (
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} paddingAngle={3}>
                  {data.map((entry, index) => <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
              </PieChart>
            )}
          </ResponsiveContainer>
        </div>
        <div className="flex flex-col justify-center gap-2">
          {data.map((item, index) => (
            <div key={item.name} className="flex items-center justify-between gap-3 text-xs">
              <span className="flex min-w-0 items-center gap-2 text-slate-400"><span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartColors[index % chartColors.length] }} /><span className="truncate">{item.name}</span></span>
              <span className="font-medium text-slate-200">{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  )
}
