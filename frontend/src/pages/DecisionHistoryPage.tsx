import { Search, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { EmptyState, ErrorNotice, PageTitle, Panel, formatDate, policyTone } from '../components/ui'
import { api } from '../services/api'
import type { DecisionRecord } from '../types'

export function DecisionHistoryPage() {
  const [records, setRecords] = useState<DecisionRecord[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [securityAction, setSecurityAction] = useState('')
  const [policy, setPolicy] = useState('')
  const [sortBy, setSortBy] = useState('created_at')
  const [order, setOrder] = useState('desc')
  const [selected, setSelected] = useState<DecisionRecord | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    setLoading(true)
    const params = new URLSearchParams({
      q: search,
      security_action: securityAction,
      qos_policy: policy,
      sort_by: sortBy,
      order,
      limit: '200',
    })
    try {
      const data = await api.decisions(params)
      setRecords(data.items)
      setTotal(data.total)
      setError('')
      if (selected && !data.items.some((record) => record.id === selected.id)) setSelected(null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Decision history could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 180)
    return () => window.clearTimeout(timer)
  }, [search, securityAction, policy, sortBy, order])

  useEffect(() => {
    if (!selected) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [selected])

  const showDetails = async (id: number) => {
    setDetailLoading(true)
    try {
      setSelected(await api.decision(id))
      setError('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Decision details could not be loaded.')
    } finally {
      setDetailLoading(false)
    }
  }

  const remove = async (record: DecisionRecord) => {
    const confirmed = window.confirm(`Delete decision #${record.id} (${record.input.traffic_type})? This action cannot be undone.`)
    if (!confirmed) return
    try {
      await api.deleteDecision(record.id)
      if (selected?.id === record.id) setSelected(null)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The decision could not be deleted.')
    }
  }

  return (
    <div>
      <PageTitle
        eyebrow="Persistent SQLite records"
        title="Decision history"
        description="Search, inspect, and explicitly delete persisted controller decisions. Phase 1 fields are shown alongside integrated risk and final-policy values when the integrated controller was used."
      />
      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      <Panel>
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_170px_190px_170px_110px]">
          <label className="relative block">
            <span className="sr-only">Search decision history</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search traffic, policy, or rationale" className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-9 pr-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-500/50" />
          </label>
          <select aria-label="Filter by security action" value={securityAction} onChange={(event) => setSecurityAction(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200">
            <option value="">All security actions</option>
            <option>ALLOW</option><option>MONITOR</option><option>RESTRICT</option><option>QUARANTINE</option>
          </select>
          <select aria-label="Filter by QoS policy" value={policy} onChange={(event) => setPolicy(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200">
            <option value="">All QoS policies</option>
            <option>CRITICAL PRIORITY</option><option>HIGH PRIORITY</option><option>NORMAL</option><option>LOW / RATE LIMITED</option><option>RATE LIMITED</option><option>QUARANTINED</option>
          </select>
          <select aria-label="Sort decisions" value={sortBy} onChange={(event) => setSortBy(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200">
            <option value="created_at">Sort: Time</option><option value="decision_score">Sort: Score</option><option value="threat_level">Sort: Threat</option><option value="latency">Sort: Latency</option><option value="traffic_type">Sort: Traffic</option>
          </select>
          <button type="button" onClick={() => setOrder((current) => current === 'desc' ? 'asc' : 'desc')} className="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800">
            {order === 'desc' ? 'Newest first' : 'Oldest first'}
          </button>
        </div>

        <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
          <span>{loading ? 'Refreshing records…' : `${total} matching decision${total === 1 ? '' : 's'}`}</span>
          <span>Showing up to 200 records</span>
        </div>

        {records.length ? (
          <div className="mt-3 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[920px] border-collapse text-left text-xs">
              <thead className="bg-slate-900/70 text-[9px] uppercase tracking-[0.14em] text-slate-500">
                <tr>
                  <th className="px-3 py-3 font-medium">Recorded at</th>
                  <th className="px-3 py-3 font-medium">Traffic</th>
                  <th className="px-3 py-3 font-medium">Threat</th>
                  <th className="px-3 py-3 font-medium">Congestion</th>
                  <th className="px-3 py-3 font-medium">Bandwidth</th>
                  <th className="px-3 py-3 font-medium">Latency</th>
                  <th className="px-3 py-3 font-medium">Score</th>
                  <th className="px-3 py-3 font-medium">Raw risk</th>
                  <th className="px-3 py-3 font-medium">Effective risk</th>
                  <th className="px-3 py-3 font-medium">Policy</th>
                  <th className="px-3 py-3 font-medium">Security</th>
                  <th className="px-3 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id} className="border-t border-slate-800/80 text-slate-300 hover:bg-slate-900/35">
                    <td className="whitespace-nowrap px-3 py-3 text-slate-500">{formatDate(record.created_at)}</td>
                    <td className="px-3 py-3 font-medium text-slate-100">{record.input.traffic_type}</td>
                    <td className="px-3 py-3">{record.input.threat_level} / 10</td>
                    <td className="px-3 py-3">{record.input.congestion} / 10</td>
                    <td className="px-3 py-3">{record.input.bandwidth_available} Mbps</td>
                    <td className="px-3 py-3">{record.input.latency} ms</td>
                    <td className="px-3 py-3 font-medium text-cyan-100">{record.result.decision_score.toFixed(2)}</td>
                    <td className="px-3 py-3">{record.integrated_result?.raw_security_risk.toFixed(2) ?? '—'}</td>
                    <td className="px-3 py-3">{record.integrated_result?.effective_security_risk.toFixed(2) ?? '—'}</td>
                    <td className="px-3 py-3">{record.integrated_result?.final_policy ?? record.result.qos_policy}</td>
                    <td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 text-[9px] ${policyTone(record.result.security_action)}`}>{record.result.security_action}</span></td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => void showDetails(record.id)} className="rounded-lg border border-slate-700 px-2 py-1.5 text-[10px] text-slate-200 hover:border-cyan-600/50">Details</button>
                        <button type="button" aria-label={`Delete decision ${record.id}`} onClick={() => void remove(record)} className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:border-rose-500/40 hover:text-rose-200"><Trash2 className="h-3.5 w-3.5" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4"><EmptyState title={total === 0 ? 'No matching decisions' : 'No saved decisions'} detail={total === 0 ? 'Change the search or filters, or run a network analysis to add a record.' : 'Saved decisions will appear here.'} /></div>
        )}
      </Panel>

      {selected ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-3 sm:p-6"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelected(null)
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="decision-details-title"
            className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl sm:p-6"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Record #{selected.id} · {formatDate(selected.created_at)}</p>
                <h2 id="decision-details-title" className="mt-2 text-lg font-semibold text-white">Decision details</h2>
              </div>
              <div className="flex items-center gap-3">
                <span className={`rounded-full border px-2.5 py-1 text-xs ${policyTone(selected.result.security_action)}`}>{selected.result.security_action}</span>
                <button
                  type="button"
                  aria-label="Close decision details"
                  onClick={() => setSelected(null)}
                  className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:border-cyan-600/50 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Detail label="Traffic type" value={selected.input.traffic_type} />
              <Detail label="Threat level" value={`${selected.input.threat_level} / 10`} />
              <Detail label="Network congestion" value={`${selected.input.congestion} / 10`} />
              <Detail label="Available bandwidth" value={`${selected.input.bandwidth_available} Mbps`} />
              <Detail label="Latency" value={`${selected.input.latency} ms`} />
              <Detail label="Application priority" value={`${selected.input.application_priority} / 10`} />
              <Detail label="Device trust" value={`${selected.input.device_trust} / 100`} />
              <Detail label="Phase 1 decision score" value={formatNumber(selected.result.decision_score)} />
              <Detail label="Raw security risk" value={formatNumber(selected.integrated_result?.raw_security_risk)} />
              <Detail label="Effective security risk" value={formatNumber(selected.integrated_result?.effective_security_risk)} />
              <Detail label="QoS utility" value={formatNumber(selected.integrated_result?.qos_utility)} />
              <Detail label="Threat trend" value={selected.integrated_result?.threat_trend ?? NOT_RECORDED} />
              <Detail label="EWMA smoothed threat" value={formatNumber(selected.integrated_result?.smoothed_threat)} />
              <Detail label="Temporal adjustment" value={formatNumber(selected.integrated_result?.temporal_adjustment)} />
              <Detail label="R_MAX" value={formatNumber(selected.integrated_result?.r_max)} />
              <Detail label="Risk budget status" value={formatBoolean(selected.integrated_result?.risk_budget_satisfied)} />
              <Detail label="Candidate policy" value={selected.integrated_result?.candidate_policy ?? NOT_RECORDED} />
              <Detail label="Final policy" value={selected.integrated_result?.final_policy ?? NOT_RECORDED} />
              <Detail label="Previous policy" value={selected.integrated_result ? selected.integrated_result.previous_policy ?? 'None (first decision)' : NOT_RECORDED} />
              <Detail label="Switching cost" value={formatNumber(selected.integrated_result?.switching_cost)} />
              <Detail label="Stability objective" value={formatNumber(selected.integrated_result?.stability_objective?.stability_aware_objective)} />
              <Detail label="QoS policy" value={selected.result.qos_policy} />
              <Detail label="Bandwidth allocation" value={formatWithUnit(selected.result.bandwidth_allocation, 'Mbps')} />
              <Detail label="Security action" value={selected.result.security_action} />
            </div>
            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              <section>
                <h3 className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Rationale / explanation</h3>
                <p className="mt-2 min-h-20 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm leading-6 text-slate-300">
                  {selected.integrated_result?.explanation || selected.result.reason || NOT_RECORDED}
                </p>
              </section>
              <section>
                <h3 className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Factor contributions</h3>
                {Object.keys(selected.result.factor_contributions ?? {}).length ? (
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {Object.entries(selected.result.factor_contributions).map(([factor, contribution]) => (
                      <Detail key={factor} label={factor} value={formatNumber(contribution)} />
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-400">{NOT_RECORDED}</p>
                )}
              </section>
            </div>
          </section>
        </div>
      ) : null}
      {detailLoading ? (
        <div role="status" className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-6">
          <p className="rounded-xl border border-slate-700 bg-slate-900 px-5 py-4 text-sm text-slate-200">Loading persisted decision details…</p>
        </div>
      ) : null}
    </div>
  )
}

const NOT_RECORDED = 'Not recorded'

function formatNumber(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : NOT_RECORDED
}

function formatWithUnit(value: number | null | undefined, unit: string) {
  return typeof value === 'number' && Number.isFinite(value) ? `${formatNumber(value)} ${unit}` : NOT_RECORDED
}

function formatBoolean(value: boolean | null | undefined) {
  return typeof value === 'boolean' ? (value ? 'Satisfied' : 'Violated') : NOT_RECORDED
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[9px] uppercase tracking-wide text-slate-500">{label}</p><p className="mt-1 text-xs text-slate-200">{value}</p></div>
}
