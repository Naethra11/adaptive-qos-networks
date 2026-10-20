import { useEffect, useState } from 'react'
import { ErrorNotice, PageTitle, Panel } from '../components/ui'
import { api } from '../services/api'
import type { EvaluationScenario, IntegratedDecisionResult, TestbedStatus } from '../types'

export function LiveTestbedPage() {
  const [status, setStatus] = useState<TestbedStatus | null>(null)
  const [scenarios, setScenarios] = useState<EvaluationScenario[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [decision, setDecision] = useState<IntegratedDecisionResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    try {
      const current = await api.testbedStatus()
      setStatus(current)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Testbed status could not be checked.')
    }
  }

  useEffect(() => {
    let active = true
    void Promise.all([api.testbedStatus(), api.evaluationScenarios()])
      .then(([testbed, matrix]) => {
        if (!active) return
        setStatus(testbed)
        setScenarios(matrix.items)
        setSelectedId(matrix.items[0]?.scenario_id ?? '')
        setError('')
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Live Testbed services are unavailable.')
      })
    return () => { active = false }
  }, [])

  const runSimulation = async () => {
    const scenario = scenarios.find((item) => item.scenario_id === selectedId)
    if (!scenario) return
    setLoading(true)
    setError('')
    try {
      setDecision(await api.integratedDecision(scenario.network_input, {
        previous_smoothed_threat: null,
        previous_policy: null,
      }))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Simulation-mode decision failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <PageTitle
        eyebrow="Phase 5 · controlled testbed"
        title="Live Testbed"
        description="Read-only telemetry is shown only when the backend can collect it from the configured Mininet interface. The page never fabricates live values or applies QoS enforcement."
        action={<button type="button" onClick={() => void refresh()} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 hover:border-cyan-500/40">Refresh status</button>}
      />
      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Telemetry connection</p>
            <h3 className={`mt-2 text-xl font-semibold ${status?.connected ? 'text-emerald-200' : 'text-amber-200'}`}>
              {status?.connected ? 'Controlled Mininet testbed connected' : 'Controlled Mininet testbed not connected'}
            </h3>
            <p className="mt-2 text-sm text-slate-400">{status?.message ?? 'Checking read-only interface telemetry…'}</p>
          </div>
          <span className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300">Interface · {status?.interface ?? 's1-eth3'}</span>
        </div>
        {status?.connected && status.telemetry ? (
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <TelemetryValue label="Configured capacity" value={`${status.telemetry.htb_configured_rate} · live tc value`} />
            <TelemetryValue label="RTT" value="Not collected by the qdisc telemetry endpoint" />
            <TelemetryValue label="Congestion proxy · qdisc drops" value={String(status.telemetry.qdisc_dropped_packets)} />
            <TelemetryValue label="Qdisc overlimits" value={String(status.telemetry.qdisc_overlimits)} />
            <TelemetryValue label="Qdisc backlog" value={`${status.telemetry.qdisc_backlog_packets} packets`} />
            <TelemetryValue label="Interface TX" value={`${status.telemetry.interface_tx_bytes} bytes`} />
            <TelemetryValue label="Interface RX" value={`${status.telemetry.interface_rx_bytes} bytes`} />
            <TelemetryValue label="QoS enforcement" value="Not applied by this dashboard" />
          </div>
        ) : (
          <div className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/[0.05] p-4">
            <p className="text-sm font-medium text-amber-100">Simulation Mode</p>
            <p className="mt-1 text-xs leading-5 text-slate-400">No network telemetry is available. The following result will come from the integrated software decision API and is not a live measurement.</p>
          </div>
        )}
        <p className="mt-4 text-[11px] text-slate-500">This dashboard does not change tc settings. Any manual Phase 6.4 experiment remains a separate, explicit controlled-testbed operation.</p>
      </Panel>

      <Panel className="mt-6">
        <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200">Software decision · not live enforcement</p>
        <h3 className="mt-1 text-lg font-semibold text-white">Simulation Mode</h3>
        <div className="mt-4 flex flex-wrap gap-2">
          <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} className="min-w-64 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100">
            {scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.scenario_id}</option>)}
          </select>
          <button type="button" disabled={loading || !selectedId} onClick={() => void runSimulation()} className="rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">{loading ? 'Running…' : 'Run software decision'}</button>
        </div>
        {decision ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <TelemetryValue label="Candidate / final policy" value={`${decision.candidate_policy} / ${decision.final_policy}`} />
            <TelemetryValue label="Raw / effective risk" value={`${decision.raw_security_risk.toFixed(2)} / ${decision.effective_security_risk.toFixed(2)}`} />
            <TelemetryValue label="QoS utility" value={decision.qos_utility.toFixed(2)} />
            <TelemetryValue label="Security action" value={decision.security_action} />
          </div>
        ) : null}
      </Panel>
    </div>
  )
}

function TelemetryValue({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-[9px] uppercase tracking-[0.15em] text-slate-500">{label}</p><p className="mt-1 break-words text-sm font-medium text-slate-100">{value}</p></div>
}
