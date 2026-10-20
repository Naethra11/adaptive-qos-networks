import { Copy, Pencil, Play, Plus, Save, Trash2, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { ErrorNotice, PageTitle, Panel, formatDate, policyTone } from '../components/ui'
import { api } from '../services/api'
import type { DecisionResult, NetworkInput, Scenario } from '../types'

type ScenarioDraft = NetworkInput & {
  name: string
  description: string
}

const emptyDraft: ScenarioDraft = {
  name: '',
  description: '',
  traffic_type: 'Video Call',
  threat_level: 2,
  congestion: 3,
  bandwidth_available: 20,
  application_priority: 8,
  device_trust: 90,
  latency: 50,
}

const trafficTypes = ['Voice Call', 'Video Call', 'Gaming', 'Web Browsing', 'File Download', 'Background Traffic', 'Suspicious Traffic']

export function ScenariosPage({ onRunScenario }: { onRunScenario: (scenario: Scenario) => void }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [draft, setDraft] = useState<ScenarioDraft>(emptyDraft)
  const [editing, setEditing] = useState<Scenario | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [running, setRunning] = useState<number | null>(null)
  const [lastResult, setLastResult] = useState<{ name: string; result: DecisionResult } | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const response = await api.scenarios()
      setScenarios(response.items)
      setError('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scenarios could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const startEdit = (scenario: Scenario) => {
    setEditing(scenario)
    setEditorOpen(true)
    setDraft({
      name: scenario.name,
      description: scenario.description,
      traffic_type: scenario.traffic_type,
      threat_level: scenario.threat_level,
      congestion: scenario.congestion,
      bandwidth_available: scenario.bandwidth_available,
      application_priority: scenario.application_priority,
      device_trust: scenario.device_trust,
      latency: scenario.latency,
    })
    setError('')
  }

  const startCreate = () => {
    setEditing(null)
    setEditorOpen(true)
    setDraft(emptyDraft)
    setError('')
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (editing) await api.updateScenario(editing.id, draft)
      else await api.createScenario(draft)
      setEditing(null)
      setEditorOpen(false)
      setDraft(emptyDraft)
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scenario could not be saved.')
    } finally {
      setLoading(false)
    }
  }

  const duplicate = async (scenario: Scenario) => {
    setLoading(true)
    setError('')
    try {
      const { id: _id, created_at: _createdAt, is_default: _isDefault, ...copy } = scenario
      await api.createScenario({ ...copy, name: `${scenario.name} copy` })
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scenario could not be duplicated.')
    } finally {
      setLoading(false)
    }
  }

  const remove = async (scenario: Scenario) => {
    if (!window.confirm(`Delete scenario "${scenario.name}"? It will not delete existing decision records.`)) return
    setLoading(true)
    setError('')
    try {
      await api.deleteScenario(scenario.id)
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scenario could not be deleted.')
    } finally {
      setLoading(false)
    }
  }

  const run = async (scenario: Scenario) => {
    setRunning(scenario.id)
    setError('')
    try {
      const result = await api.decide(scenario)
      setLastResult({ name: scenario.name, result })
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scenario analysis failed.')
    } finally {
      setRunning(null)
    }
  }

  return (
    <div>
      <PageTitle
        eyebrow="Reusable network conditions"
        title="Scenarios"
        description="Inspect predefined baseline conditions and manage your own test inputs. Running a scenario sends its values to the same decision API used by the engine page."
        action={<button type="button" onClick={startCreate} className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 hover:border-cyan-500/40 hover:bg-slate-800/60"><Plus className="h-4 w-4" /> New scenario</button>}
      />
      {error ? <div className="mb-5"><ErrorNotice>{error}</ErrorNotice></div> : null}

      {lastResult ? (
        <Panel className="mb-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Latest scenario result · {lastResult.name}</p>
              <p className="mt-2 text-sm text-white">{lastResult.result.qos_policy} · score {lastResult.result.decision_score.toFixed(2)} · {lastResult.result.queue}</p>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs ${policyTone(lastResult.result.security_action)}`}>{lastResult.result.security_action}</span>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-400">{lastResult.result.reason}</p>
        </Panel>
      ) : null}

      {editorOpen ? (
        <Panel className="mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{editing ? 'Update saved input' : 'Create reusable input'}</p>
              <h3 className="mt-1 text-base font-semibold text-white">{editing ? `Edit ${editing.name}` : 'New scenario'}</h3>
            </div>
            <button type="button" aria-label="Close scenario editor" onClick={() => { setEditing(null); setEditorOpen(false); setDraft(emptyDraft) }} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
          </div>
          <form onSubmit={save} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <TextInput label="Scenario name" value={draft.name} onChange={(name) => setDraft((current) => ({ ...current, name }))} required />
            <label className="block text-xs text-slate-400 sm:col-span-2">
              Description
              <input value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500/50" />
            </label>
            <label className="block text-xs text-slate-400">
              Traffic type
              <select value={draft.traffic_type} onChange={(event) => setDraft((current) => ({ ...current, traffic_type: event.target.value }))} className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                {trafficTypes.map((traffic) => <option key={traffic}>{traffic}</option>)}
              </select>
            </label>
            <NumericDraft label="Threat / 10" value={draft.threat_level} max={10} onChange={(threat_level) => setDraft((current) => ({ ...current, threat_level }))} />
            <NumericDraft label="Congestion / 10" value={draft.congestion} max={10} onChange={(congestion) => setDraft((current) => ({ ...current, congestion }))} />
            <NumericDraft label="Bandwidth · Mbps" value={draft.bandwidth_available} max={10000} onChange={(bandwidth_available) => setDraft((current) => ({ ...current, bandwidth_available }))} />
            <NumericDraft label="Application priority / 10" value={draft.application_priority} max={10} onChange={(application_priority) => setDraft((current) => ({ ...current, application_priority }))} />
            <NumericDraft label="Device trust / 100" value={draft.device_trust} max={100} onChange={(device_trust) => setDraft((current) => ({ ...current, device_trust }))} />
            <NumericDraft label="Latency · ms" value={draft.latency} max={100000} onChange={(latency) => setDraft((current) => ({ ...current, latency }))} />
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
              <button type="submit" disabled={loading} className="inline-flex items-center gap-2 rounded-lg bg-cyan-300 px-4 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50"><Save className="h-3.5 w-3.5" /> Save scenario</button>
              <button type="button" onClick={() => { setEditing(null); setEditorOpen(false); setDraft(emptyDraft) }} className="rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300">Cancel</button>
            </div>
          </form>
        </Panel>
      ) : null}

      {loading && !scenarios.length ? <p className="text-sm text-slate-500">Loading saved scenarios…</p> : null}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {scenarios.map((scenario) => (
          <Panel key={scenario.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-semibold text-white">{scenario.name}</h3>
                  {scenario.is_default ? <span className="rounded-full border border-cyan-500/20 bg-cyan-500/[0.05] px-2 py-0.5 text-[9px] uppercase tracking-wide text-cyan-200">Baseline</span> : null}
                </div>
                <p className="mt-2 min-h-10 text-xs leading-5 text-slate-400">{scenario.description}</p>
              </div>
              <span className="text-[9px] text-slate-600">#{scenario.id}</span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <ScenarioMetric label="Traffic" value={scenario.traffic_type} />
              <ScenarioMetric label="Threat" value={`${scenario.threat_level} / 10`} />
              <ScenarioMetric label="Congestion" value={`${scenario.congestion} / 10`} />
              <ScenarioMetric label="Bandwidth" value={`${scenario.bandwidth_available} Mbps`} />
              <ScenarioMetric label="Application priority" value={`${scenario.application_priority} / 10`} />
              <ScenarioMetric label="Device trust" value={`${scenario.device_trust} / 100`} />
              <ScenarioMetric label="Latency" value={`${scenario.latency} ms`} />
              <ScenarioMetric label="Created" value={formatDate(scenario.created_at)} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-800 pt-4">
              <button type="button" disabled={running === scenario.id} onClick={() => void run(scenario)} className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-300 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50"><Play className="h-3.5 w-3.5" /> {running === scenario.id ? 'Running…' : 'Run scenario'}</button>
              <button type="button" onClick={() => onRunScenario(scenario)} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800/70">Open in engine</button>
              <button type="button" aria-label={`Duplicate ${scenario.name}`} onClick={() => void duplicate(scenario)} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-cyan-200"><Copy className="h-3.5 w-3.5" /></button>
              <button type="button" aria-label={`Edit ${scenario.name}`} onClick={() => startEdit(scenario)} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-cyan-200"><Pencil className="h-3.5 w-3.5" /></button>
              {!scenario.is_default ? <button type="button" aria-label={`Delete ${scenario.name}`} onClick={() => void remove(scenario)} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-rose-200"><Trash2 className="h-3.5 w-3.5" /></button> : null}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  )
}

function ScenarioMetric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/40 p-2"><p className="text-[9px] uppercase tracking-wide text-slate-600">{label}</p><p className="mt-1 truncate text-xs text-slate-200" title={value}>{value}</p></div>
}

function TextInput({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
}) {
  return <label className="block text-xs text-slate-400">{label}<input required={required} value={value} onChange={(event) => onChange(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500/50" /></label>
}

function NumericDraft({
  label,
  value,
  max,
  onChange,
}: {
  label: string
  value: number
  max: number
  onChange: (value: number) => void
}) {
  return <label className="block text-xs text-slate-400">{label}<input type="number" min={0} max={max} step="any" required value={value} onChange={(event) => onChange(Number(event.target.value))} className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500/50" /></label>
}
