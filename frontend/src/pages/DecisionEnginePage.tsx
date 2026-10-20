import { motion } from 'framer-motion'
import { ArrowRight, Check, LoaderCircle, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../services/api'
import type { DecisionResult, IntegratedDecisionResult, NetworkInput, Scenario, SystemSettings } from '../types'
import { ErrorNotice, PageTitle, Panel, policyTone } from '../components/ui'

const initialInput: NetworkInput = {
  traffic_type: 'Video Call',
  threat_level: 2,
  congestion: 4,
  bandwidth_available: 24,
  application_priority: 8,
  device_trust: 90,
  latency: 80,
}

const trafficTypes = [
  'Voice Call',
  'Video Call',
  'Gaming',
  'Web Browsing',
  'File Download',
  'Background Traffic',
  'Suspicious Traffic',
]

const analysisSteps = [
  'Validate network inputs',
  'Phase 1 · normalize, weight, and score',
  'Phase 2 · utility and security admissibility',
  'Phase 3 · EWMA trend and effective risk',
  'Phase 4 · hysteresis and stability metrics',
  'Persist integrated decision',
]

const factorLabels: Record<string, string> = {
  application_priority: 'Application Priority',
  threat_security: 'Threat Security',
  congestion: 'Network Congestion',
  bandwidth: 'Available Bandwidth',
  traffic_type: 'Traffic Type',
  device_trust: 'Device Trust',
  latency: 'Latency',
}

type DecisionEnginePageProps = {
  initialScenario: Scenario | null
  onScenarioConsumed: () => void
}

export function DecisionEnginePage({ initialScenario, onScenarioConsumed }: DecisionEnginePageProps) {
  const [input, setInput] = useState<NetworkInput>(initialInput)
  const [result, setResult] = useState<DecisionResult | null>(null)
  const [integrated, setIntegrated] = useState<IntegratedDecisionResult | null>(null)
  const [previousThreat, setPreviousThreat] = useState<number | null>(null)
  const [previousPolicy, setPreviousPolicy] = useState('')
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(-1)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.settings()
      .then((current) => { if (active) setSettings(current) })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Runtime thresholds could not be loaded.')
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (initialScenario) {
      const { name: _name, description: _description, id: _id, is_default: _default, created_at: _created, ...scenarioInput } = initialScenario
      setInput(scenarioInput)
      setResult(null)
      setIntegrated(null)
      setError('')
      onScenarioConsumed()
    }
  }, [initialScenario, onScenarioConsumed])

  const update = <K extends keyof NetworkInput>(key: K, value: NetworkInput[K]) => {
    setInput((current) => ({ ...current, [key]: value }))
  }

  const analyze = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setStage(0)

    const decisionRequest = api.integratedDecision(input, {
      previous_smoothed_threat: previousThreat,
      previous_policy: previousPolicy || null,
    })
    const visualization = async () => {
      for (let index = 1; index < analysisSteps.length; index += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 230))
        setStage(index)
      }
    }

    try {
      const [decision] = await Promise.all([decisionRequest, visualization()])
      setIntegrated(decision)
      setResult(decision.phase1_result)
      setStage(analysisSteps.length)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The decision request could not be completed.')
      setStage(-1)
    } finally {
      setBusy(false)
    }
  }

  const rawValueFor = (factor: string) => {
    switch (factor) {
      case 'application_priority':
        return `${input.application_priority} / 10`
      case 'threat_security':
        return `Threat ${input.threat_level} / 10`
      case 'congestion':
        return `${input.congestion} / 10`
      case 'bandwidth':
        return `${input.bandwidth_available} Mbps`
      case 'traffic_type':
        return input.traffic_type
      case 'device_trust':
        return `${input.device_trust} / 100`
      case 'latency':
        return `${input.latency} ms`
      default:
        return '—'
    }
  }

  const factors = result
    ? Object.keys(result.factor_contributions).map((factor) => ({
        factor,
        normalized: result.normalized_factors[factor] ?? 0,
        weight: result.dynamic_weights[factor] ?? 0,
        contribution: result.factor_contributions[factor] ?? 0,
      }))
    : []
  const securityOverride = result?.security_action === 'RESTRICT' || result?.security_action === 'QUARANTINE'

  const selectHighThreatScenario = () => {
    setInput({
      traffic_type: 'Suspicious Traffic',
      threat_level: 10,
      congestion: 3,
      bandwidth_available: 50,
      application_priority: 9,
      device_trust: 5,
      latency: 45,
    })
    setIntegrated(null)
    setResult(null)
  }

  return (
    <div>
      <PageTitle
        eyebrow="Integrated research controller · Phases 1–4"
        title="Decision Engine"
        description="Run the implemented multi-factor, risk-aware, temporal, and stability pipeline. All displayed outcomes are returned by the Python controller."
      />

      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      <div className="grid items-start gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Panel>
          <form onSubmit={analyze} className="space-y-5">
            <div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Input signals</p>
                <button type="button" onClick={selectHighThreatScenario} className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-[10px] font-medium text-rose-200 hover:bg-rose-500/15">
                  Load High Threat
                </button>
              </div>
              <h3 className="mt-2 text-lg font-semibold text-white">Network conditions</h3>
            </div>

            <label className="block text-sm text-slate-300">
              Traffic type
              <select
                value={input.traffic_type}
                onChange={(event) => update('traffic_type', event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
              >
                {trafficTypes.map((traffic) => <option key={traffic}>{traffic}</option>)}
              </select>
            </label>

            <div className="space-y-4">
              <RangeInput label="Threat level" value={input.threat_level} max={10} suffix="/10" onChange={(value) => update('threat_level', value)} />
              <RangeInput label="Network congestion" value={input.congestion} max={10} suffix="/10" onChange={(value) => update('congestion', value)} />
              <RangeInput label="Application priority" value={input.application_priority} max={10} suffix="/10" onChange={(value) => update('application_priority', value)} />
              <RangeInput label="Device trust" value={input.device_trust} max={100} step={5} suffix="/100" onChange={(value) => update('device_trust', value)} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Bandwidth" value={input.bandwidth_available} unit="Mbps" min={0} onChange={(value) => update('bandwidth_available', value)} />
              <NumberInput label="Latency" value={input.latency} unit="ms" min={0} onChange={(value) => update('latency', value)} />
            </div>

            <div className="grid grid-cols-2 gap-3 border-t border-slate-800 pt-4">
              <label className="block text-xs text-slate-400">
                Previous smoothed threat
                <input type="number" min={0} max={100} step="any" value={previousThreat ?? ''} placeholder="None (first observation)" onChange={(event) => setPreviousThreat(event.target.value === '' ? null : Number(event.target.value))} className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
              </label>
              <label className="block text-xs text-slate-400">
                Previous policy
                <select value={previousPolicy} onChange={(event) => setPreviousPolicy(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                  <option value="">None (first decision)</option>
                  <option>CRITICAL PRIORITY</option><option>HIGH PRIORITY</option><option>NORMAL</option><option>LOW / RATE LIMITED</option><option>QUARANTINED</option>
                </select>
              </label>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-wait disabled:opacity-70"
            >
              {busy ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Running Phases 1–4</> : <>RUN DECISION <ArrowRight className="h-4 w-4" /></>}
            </button>
          </form>
        </Panel>

        <div className="space-y-6">
          {integrated ? (
            <Panel>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-200">Phase 1 → 2 → 3 → 4 · actual backend result</p>
                  <h3 className="mt-1 text-lg font-semibold text-white">Integrated decision pipeline</h3>
                </div>
                <span className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${policyTone(integrated.final_policy === 'QUARANTINED' ? 'QUARANTINE' : integrated.security_action)}`}>
                  FINAL · {integrated.final_policy}
                </span>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Outcome label="Phase 1 score" value={`${integrated.decision_score.toFixed(2)} / 100`} />
                <Outcome label="QoS utility" value={integrated.qos_utility.toFixed(2)} />
                <Outcome label="Raw security risk" value={integrated.raw_security_risk.toFixed(2)} />
                <Outcome label="Effective risk / R_MAX" value={`${integrated.effective_security_risk.toFixed(2)} / ${integrated.r_max.toFixed(2)}`} />
                <Outcome label="Risk budget" value={integrated.risk_budget_satisfied ? 'SATISFIED' : 'VIOLATED'} />
                <Outcome label="Threat trend" value={`${integrated.threat_trend} · EWMA ${integrated.smoothed_threat.toFixed(2)}`} />
                <Outcome label="Temporal adjustment" value={`${integrated.temporal_adjustment >= 0 ? '+' : ''}${integrated.temporal_adjustment.toFixed(2)}`} />
                <Outcome label="Candidate → final" value={`${integrated.candidate_policy} → ${integrated.final_policy}`} />
                <Outcome label="Hysteresis state" value={integrated.candidate_policy !== integrated.final_policy ? `Retained ${integrated.final_policy}` : 'Candidate accepted'} />
                <Outcome label="Switching cost" value={integrated.switching_cost.toFixed(2)} />
                <Outcome label="Stability objective" value={integrated.stability_objective.stability_aware_objective.toFixed(2)} />
                <Outcome label="Recommended allocation" value={`${integrated.bandwidth_allocation.toFixed(2)} Mbps`} />
                <Outcome label="Security action" value={integrated.security_action} />
              </div>
              {settings ? (
                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/35 p-3">
                  <p className="text-[9px] uppercase tracking-[0.16em] text-slate-500">Configured hysteresis thresholds · loaded from backend</p>
                  <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-300">
                    <span>Normal enter/exit: {settings.stability.hysteresis.normal_enter} / {settings.stability.hysteresis.normal_exit}</span>
                    <span>High enter/exit: {settings.stability.hysteresis.high_enter} / {settings.stability.hysteresis.high_exit}</span>
                    <span>Critical enter/exit: {settings.stability.hysteresis.critical_enter} / {settings.stability.hysteresis.critical_exit}</span>
                    <span>R_MAX: {settings.risk_aware.r_max}</span>
                  </div>
                </div>
              ) : null}
              <div className={`mt-4 rounded-xl border p-4 ${integrated.risk_budget_satisfied ? 'border-cyan-500/20 bg-cyan-500/[0.04]' : 'border-rose-500/30 bg-rose-500/[0.08]'}`}>
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Why was this final policy selected?</p>
                <p className="mt-2 text-sm leading-6 text-slate-100">{integrated.explanation}</p>
                <p className="mt-2 text-[11px] text-slate-400">Prior state supplied: threat {integrated.previous_smoothed_threat ?? 'none'} · policy {integrated.previous_policy ?? 'none'}. Stability objective is reported separately; it does not rerank the risk-aware candidate.</p>
              </div>
            </Panel>
          ) : null}

          <Panel>
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-center">
              <div className="flex items-center gap-5">
                <div className="relative grid h-32 w-32 shrink-0 place-items-center">
                  <svg viewBox="0 0 120 120" className="absolute inset-0 h-full w-full -rotate-90">
                    <circle cx="60" cy="60" r="49" fill="none" stroke="#303440" strokeWidth="8" />
                    <motion.circle
                      cx="60"
                      cy="60"
                      r="49"
                      fill="none"
                      stroke="#a78bfa"
                      strokeWidth="8"
                      strokeLinecap="round"
                      strokeDasharray={2 * Math.PI * 49}
                      animate={{ strokeDashoffset: 2 * Math.PI * 49 * (1 - (result?.decision_score ?? 0) / 100) }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                  </svg>
                  <div className="text-center">
                    <motion.div key={result?.decision_score ?? 'empty'} className="text-3xl font-semibold text-white">
                      {result ? result.decision_score.toFixed(2) : '—'}
                    </motion.div>
                    <div className="text-[9px] uppercase tracking-[0.17em] text-slate-500">Score / 100</div>
                  </div>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Decision score</p>
                  <h3 className="mt-2 text-xl font-semibold text-white">
                    {result ? `${result.priority} priority` : 'Awaiting analysis'}
                  </h3>
                  <p className="mt-1 text-sm text-slate-400">
                    {result ? result.qos_policy : 'Run an analysis to reveal the engine result.'}
                  </p>
                </div>
              </div>

              {result ? (
                <div className={`inline-flex items-center gap-2 self-start rounded-full border px-3 py-2 text-xs ${policyTone(result.security_action)}`}>
                  {securityOverride ? <ShieldAlert className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                  {securityOverride ? 'Security override active' : `Security status · ${result.security_action}`}
                </div>
              ) : (
                <div className="inline-flex items-center gap-2 self-start rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-400">
                  <Sparkles className="h-4 w-4" /> Baseline engine ready
                </div>
              )}
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Outcome label="Security action" value={result?.security_action ?? '—'} />
              <Outcome label="Policy queue" value={result?.queue ?? '—'} />
              <Outcome label="QoS policy" value={result?.qos_policy ?? '—'} />
              <Outcome label="Recommended allocation" value={result ? `${result.bandwidth_allocation.toFixed(2)} Mbps` : '—'} />
            </div>
            {result ? (
              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/45 p-4">
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Why this decision?</p>
                <p className="mt-2 text-sm leading-6 text-slate-200">{result.reason}</p>
              </div>
            ) : null}
          </Panel>

          {busy || stage === analysisSteps.length ? (
            <Panel>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Request visualization</p>
                  <h3 className="mt-1 text-base font-semibold text-white">Integrated controller sequence</h3>
                </div>
                <span className="text-xs text-slate-500">{busy ? 'Processing request' : 'Complete'}</span>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {analysisSteps.map((step, index) => (
                  <div key={step} className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
                    stage > index
                      ? 'border-cyan-500/25 bg-cyan-500/[0.06] text-cyan-100'
                      : stage === index
                        ? 'border-sky-400/30 bg-sky-400/[0.08] text-sky-100'
                        : 'border-slate-800 text-slate-500'
                  }`}>
                    {stage > index ? <Check className="h-3.5 w-3.5" /> : <span className="grid h-4 w-4 place-items-center rounded-full border border-current text-[9px]">{index + 1}</span>}
                    {step}
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}

          <Panel>
            <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Explainability</p>
                <h3 className="mt-1 text-base font-semibold text-white">Factor values and score contribution</h3>
              </div>
              <p className="text-xs text-slate-500">Normalized factor values and weights come from the Python engine response.</p>
            </div>
            {result ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-[10px] uppercase tracking-[0.13em] text-slate-500">
                      <th className="py-3 pr-3 font-medium">Factor</th>
                      <th className="py-3 pr-3 font-medium">Raw value</th>
                      <th className="py-3 pr-3 font-medium">Normalized score</th>
                      <th className="py-3 pr-3 font-medium">Weight</th>
                      <th className="py-3 pr-3 font-medium">Contribution</th>
                      <th className="w-40 py-3 font-medium">Contribution points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factors.map(({ factor, normalized, weight, contribution }) => (
                      <tr key={factor} className="border-b border-slate-800/70 text-slate-300 last:border-0">
                        <td className="py-3 pr-3 font-medium text-slate-100">{factorLabels[factor] ?? factor}</td>
                        <td className="py-3 pr-3">{rawValueFor(factor)}</td>
                        <td className="py-3 pr-3">{normalized.toFixed(2)} / 100</td>
                        <td className="py-3 pr-3">{(weight * 100).toFixed(1)}%</td>
                        <td className="py-3 pr-3">{contribution.toFixed(2)} pts</td>
                        <td className="py-3">
                          <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.min(contribution, 100)}%` }}
                              className="h-full rounded-full bg-cyan-400"
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-[11px] text-slate-500">Contribution points are the engine’s normalized factor score multiplied by its dynamic weight.</p>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-slate-700 px-4 py-8 text-center text-sm text-slate-500">
                Analyze a network state to inspect the actual normalized factors, dynamic weights, and contribution values.
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}

function RangeInput({
  label,
  value,
  max,
  step = 0.5,
  suffix,
  onChange,
}: {
  label: string
  value: number
  max: number
  step?: number
  suffix: string
  onChange: (value: number) => void
}) {
  return (
    <label className="block text-xs text-slate-300">
      <span className="mb-2 flex justify-between gap-3">
        <span>{label}</span>
        <span className="font-medium text-cyan-200">{value}{suffix}</span>
      </span>
      <input
        type="range"
        min={0}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-800 accent-cyan-400"
      />
    </label>
  )
}

function NumberInput({
  label,
  value,
  unit,
  min,
  onChange,
}: {
  label: string
  value: number
  unit: string
  min: number
  onChange: (value: number) => void
}) {
  return (
    <label className="block min-w-0 text-xs text-slate-300">
      {label}
      <span className="mt-2 flex items-center rounded-xl border border-slate-700 bg-slate-950 px-2.5">
        <input
          type="number"
          min={min}
          step="any"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full min-w-0 bg-transparent py-2 text-sm text-white outline-none"
        />
        <span className="text-[10px] uppercase text-slate-500">{unit}</span>
      </span>
    </label>
  )
}

function Outcome({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3">
      <p className="text-[9px] uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-2 break-words text-sm font-medium text-slate-100">{value}</p>
    </div>
  )
}
