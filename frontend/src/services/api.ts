import type {
  AnalyticsSummary,
  AblationResponse,
  DecisionRecord,
  DecisionResult,
  EvaluationScenario,
  IntegratedDecisionResult,
  NetworkInput,
  Scenario,
  Simulation,
  SystemSettings,
  SystemStatus,
  TestbedStatus,
} from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, options)
  } catch {
    throw new Error(
      'Cannot reach the Adaptive QoS API at http://127.0.0.1:8000. Start the FastAPI backend, then refresh this page.',
    )
  }
  if (response.status === 204) return undefined as T

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    const message = response.status >= 502
      ? 'The frontend proxy could not reach FastAPI on port 8000. Start the backend with: uvicorn api:app --host 0.0.0.0 --port 8000.'
      :
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ')
          : `Request failed (${response.status})`
    throw new Error(message)
  }
  return data as T
}

export const api = {
  status: () => request<SystemStatus>('/api/status'),
  settings: () => request<SystemSettings>('/api/settings'),
  decide: (input: NetworkInput) =>
    request<DecisionResult>('/api/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),
  integratedDecision: (
    input: NetworkInput,
    state: { previous_smoothed_threat: number | null; previous_policy: string | null },
  ) =>
    request<IntegratedDecisionResult>('/api/integrated-decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, ...state }),
    }),
  decisions: (params: URLSearchParams) =>
    request<{ items: DecisionRecord[]; total: number; limit: number; offset: number }>(
      `/api/decisions?${params.toString()}`,
    ),
  decision: (id: number) => request<DecisionRecord>(`/api/decisions/${id}`),
  deleteDecision: (id: number) =>
    request<void>(`/api/decisions/${id}`, { method: 'DELETE' }),
  scenarios: () => request<{ items: Scenario[] }>('/api/scenarios'),
  createScenario: (scenario: Omit<Scenario, 'id' | 'created_at' | 'is_default'>) =>
    request<Scenario>('/api/scenarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenario),
    }),
  updateScenario: (id: number, scenario: Omit<Scenario, 'id' | 'created_at' | 'is_default'>) =>
    request<Scenario>(`/api/scenarios/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenario),
    }),
  deleteScenario: (id: number) =>
    request<void>(`/api/scenarios/${id}`, { method: 'DELETE' }),
  simulations: () => request<{ items: Simulation[] }>('/api/simulations'),
  simulation: (id: number) => request<Simulation>(`/api/simulations/${id}`),
  runSimulation: (scenarioIds: number[], name?: string) =>
    request<Simulation>('/api/simulations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_ids: scenarioIds, name }),
    }),
  analytics: () => request<AnalyticsSummary>('/api/analytics/summary'),
  evaluationScenarios: () =>
    request<{ evaluation_type: string; items: EvaluationScenario[] }>(
      '/api/evaluation/scenarios',
    ),
  ablation: () => request<AblationResponse>('/api/evaluation/ablation'),
  testbedStatus: () => request<TestbedStatus>('/api/testbed/status'),
}
