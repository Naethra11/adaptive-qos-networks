import { Pause, Play, RotateCcw, Save, ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState, ErrorNotice, PageTitle, Panel, formatDate, policyTone } from '../components/ui'
import { api } from '../services/api'
import type { AblationResponse, EvaluationScenario, IntegratedDecisionResult, Scenario, Simulation } from '../types'

export function SimulationLabPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [savedRuns, setSavedRuns] = useState<Simulation[]>([])
  const [simulation, setSimulation] = useState<Simulation | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [evaluationScenarios, setEvaluationScenarios] = useState<EvaluationScenario[]>([])
  const [selectedEvaluationId, setSelectedEvaluationId] = useState('')
  const [evaluationResult, setEvaluationResult] = useState<IntegratedDecisionResult | null>(null)
  const [ablation, setAblation] = useState<AblationResponse | null>(null)
  const [temporalChart, setTemporalChart] = useState<Array<{
    scenario: string
    rawThreat: number
    smoothedThreat: number
    effectiveRisk: number
    trend: string
  }>>([])

  useEffect(() => {
    let active = true
    Promise.all([api.scenarios(), api.simulations(), api.evaluationScenarios()])
      .then(([scenarioResult, simulationResult, evaluationResult]) => {
        if (!active) return
        setScenarios(scenarioResult.items)
        setSelected(scenarioResult.items.map((item) => item.id))
        setSavedRuns(simulationResult.items)
        setEvaluationScenarios(evaluationResult.items)
        setSelectedEvaluationId(evaluationResult.items[0]?.scenario_id ?? '')
        setError('')
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Unable to load simulation data.')
      })
    return () => {
      active = false
    }
  }, [])

  const runFixedScenario = async () => {
    const scenario = evaluationScenarios.find((item) => item.scenario_id === selectedEvaluationId)
    if (!scenario) return
    setLoading(true)
    setError('')
    try {
      const result = await api.integratedDecision(scenario.network_input, {
        previous_smoothed_threat: null,
        previous_policy: null,
      })
      setEvaluationResult(result)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Evaluation scenario failed.')
    } finally {
      setLoading(false)
    }
  }

  const runRisingThreatSequence = async () => {
    const sequence = ['S09_RISING_T1', 'S10_RISING_T2', 'S11_RISING_T3']
      .map((id) => evaluationScenarios.find((scenario) => scenario.scenario_id === id))
      .filter((scenario): scenario is EvaluationScenario => scenario !== undefined)
    if (sequence.length !== 3) {
      setError('The fixed rising-threat sequence is not available from the backend.')
      return
    }
    setLoading(true)
    setError('')
    let previousSmoothedThreat: number | null = null
    let previousPolicy: string | null = null
    const points = []
    try {
      for (const scenario of sequence) {
        const result = await api.integratedDecision(scenario.network_input, {
          previous_smoothed_threat: previousSmoothedThreat,
          previous_policy: previousPolicy,
        })
        previousSmoothedThreat = result.smoothed_threat
        previousPolicy = result.final_policy
        points.push({
          scenario: scenario.scenario_id.replace('S', ''),
          rawThreat: scenario.network_input.threat_level * 10,
          smoothedThreat: result.smoothed_threat,
          effectiveRisk: result.effective_security_risk,
          trend: result.threat_trend,
        })
        setEvaluationResult(result)
      }
      setTemporalChart(points)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Threat sequence failed.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setActiveIndex((current) => current + 1)
    }, 1150)
    return () => window.clearInterval(timer)
  }, [playing])

  useEffect(() => {
    if (simulation && activeIndex >= simulation.results.length - 1) setPlaying(false)
  }, [activeIndex, simulation])

  const activeStep = simulation?.results[activeIndex]
  const chartData = useMemo(
    () => simulation?.results.map((step) => ({
      time: step['Time Step'],
      score: step['Decision Score'],
      threat: step.Threat * 10,
      congestion: step.Congestion * 10,
    })) ?? [],
    [simulation],
  )

  const run = async () => {
    setLoading(true)
    setError('')
    setPlaying(false)
    try {
      const result = await api.runSimulation(selected, 'Phase 1 scenario run')
      setSimulation(result)
      setSavedRuns((current) => [result, ...current.filter((run) => run.id !== result.id)])
      setActiveIndex(0)
      setPlaying(result.results.length > 1)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Simulation could not be completed.')
    } finally {
      setLoading(false)
    }

    useEffect(() => {
      let active = true
      api.ablation()
        .then((data) => { if (active) setAblation(data) })
        .catch((requestError: unknown) => {
          if (active) setError(requestError instanceof Error ? requestError.message : 'Ablation summary unavailable.')
        })
      return () => { active = false }
    }, [])
  }

  const loadSavedRun = async (id: number) => {
    setLoading(true)
    setError('')
    setPlaying(false)
    try {
      const result = await api.simulation(id)
      setSimulation(result)
      setActiveIndex(0)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Saved simulation could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  const toggleScenario = (id: number) => {
    setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  }

  return (
    <div>
      <PageTitle
        eyebrow="Backend-driven scenario testing"
        title="Simulation Lab"
        description="Run the existing Python simulator over stored scenarios. Each timeline result and static baseline comparison is computed by the backend and stored for later review."
        action={
          <button
            type="button"
            disabled={loading || selected.length === 0}
            onClick={() => void run()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play className="h-4 w-4" /> {loading ? 'Running…' : 'Run simulation'}
          </button>
        }
      />

      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      <Panel className="mb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200">Fixed Phase 6.2 matrix · backend evaluated</p>
            <h3 className="mt-1 text-lg font-semibold text-white">Integrated scenario runner</h3>
            <p className="mt-1 text-xs text-slate-400">Select an existing fixed scenario. No new or randomized inputs are generated.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select aria-label="Fixed evaluation scenario" value={selectedEvaluationId} onChange={(event) => setSelectedEvaluationId(event.target.value)} className="min-w-56 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100">
              {evaluationScenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.scenario_id}</option>)}
            </select>
            <button type="button" disabled={loading || !selectedEvaluationId} onClick={() => void runFixedScenario()} className="rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">Run scenario</button>
            <button type="button" disabled={loading} onClick={() => void runRisingThreatSequence()} className="rounded-xl border border-cyan-500/30 px-4 py-2.5 text-sm text-cyan-100 disabled:opacity-50">Run rising-threat demo</button>
          </div>
        </div>
        {evaluationScenarios.find((scenario) => scenario.scenario_id === selectedEvaluationId) ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
            {evaluationScenarios.find((scenario) => scenario.scenario_id === selectedEvaluationId)?.description}
            <div className="mt-2 grid gap-2 sm:grid-cols-4">
              {Object.entries(evaluationScenarios.find((scenario) => scenario.scenario_id === selectedEvaluationId)!.network_input).map(([key, value]) => <span key={key}>{key.replaceAll('_', ' ')}: <strong className="text-slate-200">{value}</strong></span>)}
            </div>
          </div>
        ) : null}
        {evaluationResult ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Phase 1 score" value={evaluationResult.decision_score.toFixed(2)} />
            <Metric label="Risk / R_MAX" value={`${evaluationResult.effective_security_risk.toFixed(2)} / ${evaluationResult.r_max}`} />
            <Metric label="Candidate → final" value={`${evaluationResult.candidate_policy} → ${evaluationResult.final_policy}`} />
            <Metric label="Threat trend" value={`${evaluationResult.threat_trend} · EWMA ${evaluationResult.smoothed_threat.toFixed(2)}`} />
            <p className="text-xs leading-5 text-slate-300 sm:col-span-2 xl:col-span-4">{evaluationResult.explanation}</p>
          </div>
        ) : null}
        {temporalChart.length ? (
          <div className="mt-5 grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={temporalChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
                  <XAxis dataKey="scenario" stroke="#A7ADBA" fontSize={10} />
                  <YAxis domain={[0, 100]} stroke="#A7ADBA" fontSize={10} />
                  <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                  <Legend />
                  <Line type="monotone" dataKey="rawThreat" name="Raw threat × 10" stroke="#EF6675" />
                  <Line type="monotone" dataKey="smoothedThreat" name="EWMA threat" stroke="#A78BFA" />
                  <Line type="monotone" dataKey="effectiveRisk" name="Effective security risk" stroke="#F5B942" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              {temporalChart.map((point) => <div key={point.scenario} className="rounded-xl border border-slate-800 p-3 text-xs"><strong className="text-white">{point.scenario}</strong><span className="ml-2 text-cyan-200">{point.trend}</span><div className="mt-1 text-slate-400">Raw {point.rawThreat.toFixed(1)} · smoothed {point.smoothedThreat.toFixed(2)} · adjustment/effective risk shown from the backend result</div></div>)}
            </div>
          </div>
        ) : null}
      </Panel>

      {ablation ? <Panel className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200">Software evaluation · not real-network measurements</p>
        <h3 className="mt-1 text-lg font-semibold text-white">Phase 1–4 ablation comparison</h3>
        <p className="mt-1 text-xs text-slate-400">{ablation.summary.scenario_count} fixed scenarios · {ablation.runs.length} scenario × variant outputs</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-xs">
            <thead className="text-[10px] uppercase text-slate-500"><tr><th className="py-2">Variant</th><th>Policy distribution</th><th>Mean QoS utility</th><th>Mean effective risk</th><th>Risk violations</th></tr></thead>
            <tbody>{Object.entries(ablation.summary.policy_distribution).map(([variant, distribution]) => {
              const values = Object.entries(distribution.counts ?? {}).filter(([, count]) => count > 0).map(([policy, count]) => `${policy}: ${count}`).join(' · ') || '—'
              const violations = ablation.summary.risk_constraint_violation_rate[variant]
              return <tr key={variant} className="border-t border-slate-800"><td className="py-2 pr-4 text-slate-200">{variant}</td><td className="pr-4 text-slate-400">{values}</td><td className="pr-4">{ablation.summary.mean_qos_utility[variant] ?? 'Unavailable'}</td><td className="pr-4">{ablation.summary.mean_effective_security_risk[variant] ?? 'Unavailable'}</td><td>{violations ? `${violations.numerator}/${violations.denominator} (${(violations.rate ?? 0) * 100}%)` : 'Unavailable'}</td></tr>
            })}</tbody>
          </table>
        </div>
      </Panel> : null}

      <div className="grid items-start gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Panel>
          <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Scenario set</p>
          <h3 className="mt-2 text-base font-semibold text-white">Choose conditions</h3>
          <div className="mt-4 space-y-2">
            {scenarios.map((scenario) => (
              <label key={scenario.id} className="flex cursor-pointer gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3 transition hover:border-slate-600">
                <input
                  type="checkbox"
                  checked={selected.includes(scenario.id)}
                  onChange={() => toggleScenario(scenario.id)}
                  className="mt-0.5 accent-cyan-400"
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-100">{scenario.name}</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">{scenario.description}</span>
                </span>
              </label>
            ))}
            {!scenarios.length ? <EmptyState title="No scenarios available" detail="Create scenarios before running a simulation." /> : null}
          </div>
          {savedRuns.length ? (
            <label className="mt-5 block text-xs text-slate-400">
              Previous runs
              <select
                value=""
                onChange={(event) => {
                  if (event.target.value) void loadSavedRun(Number(event.target.value))
                }}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200"
              >
                <option value="">Load saved simulation…</option>
                {savedRuns.map((run) => <option key={run.id} value={run.id}>{run.name} · {formatDate(run.created_at)}</option>)}
              </select>
            </label>
          ) : null}
        </Panel>

        <div className="space-y-6">
          {simulation && activeStep ? (
            <>
              <Panel>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{simulation.name} · saved {formatDate(simulation.created_at)}</p>
                    <h3 className="mt-2 text-xl font-semibold text-white">Adaptive decision timeline</h3>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setPlaying((value) => !value)} disabled={activeIndex >= simulation.results.length - 1 && !playing} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50">
                      {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />} {playing ? 'Pause' : 'Play'}
                    </button>
                    <button type="button" onClick={() => { setPlaying(false); setActiveIndex(0) }} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800">
                      <RotateCcw className="h-3.5 w-3.5" /> Reset
                    </button>
                  </div>
                </div>

                <div className="mt-6 flex items-center">
                  {simulation.results.map((step, index) => (
                    <div key={step['Time Step']} className="flex flex-1 items-center last:flex-none">
                      <button
                        type="button"
                        onClick={() => { setPlaying(false); setActiveIndex(index) }}
                        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border text-xs font-semibold transition ${
                          index === activeIndex
                            ? 'border-violet-400 bg-violet-400 text-slate-950'
                            : index < activeIndex
                              ? 'border-cyan-700 bg-cyan-950/60 text-cyan-200'
                              : 'border-slate-700 bg-slate-900 text-slate-500'
                        }`}
                      >
                        {step['Time Step']}
                      </button>
                      {index < simulation.results.length - 1 ? <div className={`h-px min-w-4 flex-1 ${index < activeIndex ? 'bg-cyan-700' : 'bg-slate-800'}`} /> : null}
                    </div>
                  ))}
                </div>

                <div className="mt-6 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
                  <div className="rounded-2xl border border-cyan-500/15 bg-cyan-500/[0.035] p-4">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{activeStep['Time Step']} · {activeStep['Scenario Name']}</p>
                    <h4 className="mt-2 text-lg font-semibold text-white">{activeStep['QoS Policy']}</h4>
                    <span className={`mt-3 inline-flex rounded-full border px-2.5 py-1 text-[10px] ${policyTone(activeStep['Security Action'])}`}>
                      {activeStep['Security Action']}
                    </span>
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <MiniMetric label="Decision score" value={activeStep['Decision Score'].toFixed(2)} />
                      <MiniMetric label="Priority" value={activeStep.Priority} />
                      <MiniMetric label="Queue" value={activeStep.Queue} />
                      <MiniMetric label="Allocation" value={`${activeStep['Bandwidth Allocation'].toFixed(2)} Mbps`} />
                    </div>
                    <p className="mt-4 text-xs leading-5 text-slate-400">{activeStep.Reason}</p>
                  </div>
                  <div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                      <RawMetric label="Traffic" value={activeStep['Traffic Type']} />
                      <RawMetric label="Threat" value={`${activeStep.Threat} / 10`} />
                      <RawMetric label="Congestion" value={`${activeStep.Congestion} / 10`} />
                      <RawMetric label="Bandwidth" value={`${activeStep['Bandwidth (Mbps)']} Mbps`} />
                      <RawMetric label="Application priority" value={`${activeStep['Application Priority']} / 10`} />
                      <RawMetric label="Device trust" value={`${activeStep['Device Trust']} / 100`} />
                      <RawMetric label="Latency" value={`${activeStep['Latency (ms)']} ms`} />
                    </div>
                    <div className="mt-5 h-44">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(116,123,137,.22)" />
                          <XAxis dataKey="time" stroke="#A7ADBA" fontSize={10} />
                          <YAxis domain={[0, 100]} stroke="#A7ADBA" fontSize={10} />
                          <Tooltip contentStyle={{ background: '#20232D', border: '1px solid #303440', borderRadius: 8, color: '#F3F4F6' }} />
                          <Line type="monotone" dataKey="score" name="Decision score" stroke="#A78BFA" strokeWidth={2} dot={{ r: 3 }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              </Panel>

              <Panel>
                <div className="mb-4 flex items-center gap-2">
                  <Save className="h-4 w-4 text-cyan-300" />
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Observed policy output</p>
                    <h3 className="mt-1 text-base font-semibold text-white">Static baseline vs adaptive result</h3>
                  </div>
                </div>
                <div className="space-y-3">
                  {simulation.comparison.map((item) => (
                    <div key={item.Scenario} className="grid gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3 md:grid-cols-[1fr_1fr_1.25fr] md:items-center">
                      <div>
                        <p className="text-sm font-medium text-slate-100">{item['Scenario Name']}</p>
                        <p className="mt-1 text-xs text-slate-500">Static: {item['Static Priority']} · {item['Static Policy']}</p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-wide text-slate-500">Adaptive</p>
                        <p className="mt-1 text-sm text-cyan-100">{item['Adaptive Priority']} · {item['Adaptive Policy']}</p>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        {item['Security Action'] === 'QUARANTINE' || item['Security Action'] === 'RESTRICT' ? <ShieldAlert className="h-4 w-4 text-amber-300" /> : null}
                        Security: {item['Security Action']} · Baseline policy differs: {item.Adapted}
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs leading-5 text-slate-500">This is a policy-output comparison against a fixed NORMAL baseline; it does not claim measured performance gains.</p>
              </Panel>
            </>
          ) : (
            <Panel>
              <EmptyState title="No simulation selected" detail="Choose scenario inputs and run the Python simulator to create an actual backend-generated timeline." />
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-[9px] uppercase tracking-[0.15em] text-slate-500">{label}</p><p className="mt-1 text-sm font-medium text-slate-100">{value}</p></div>
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-2">
      <p className="text-[9px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xs font-medium text-slate-100">{value}</p>
    </div>
  )
}

function RawMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-[0.13em] text-slate-500">{label}</p>
      <p className="mt-1 break-words text-xs font-medium text-slate-200">{value}</p>
    </div>
  )
}
