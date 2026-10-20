export type NetworkInput = {
  traffic_type: string
  threat_level: number
  congestion: number
  bandwidth_available: number
  application_priority: number
  device_trust: number
  latency: number
}

export type DecisionResult = {
  decision_score: number
  priority: string
  qos_policy: string
  bandwidth_allocation: number
  queue: string
  security_action: string
  reason: string
  factor_contributions: Record<string, number>
  normalized_factors: Record<string, number>
  dynamic_weights: Record<string, number>
}

export type DecisionRecord = {
  id: number
  created_at: string
  input: NetworkInput
  result: DecisionResult
  integrated_result: IntegratedDecisionResult | null
  scenario_id: number | null
}

export type IntegratedDecisionResult = {
  input: NetworkInput
  decision_score: number
  priority: string
  qos_policy: string
  bandwidth_allocation: number
  queue: string
  security_action: string
  reason: string
  factor_contributions: Record<string, number>
  normalized_factors: Record<string, number>
  dynamic_weights: Record<string, number>
  candidate_policy: string
  final_policy: string
  raw_security_risk: number
  effective_security_risk: number
  r_max: number
  qos_utility: number
  risk_budget_satisfied: boolean
  smoothed_threat: number
  threat_trend: string
  temporal_adjustment: number
  previous_smoothed_threat: number | null
  previous_policy: string | null
  switching_cost: number
  stability_objective: {
    base_objective: number
    switching_cost: number
    switching_penalty: number
    stability_aware_objective: number
    switch_required: boolean
  }
  explanation: string
  phase1_result: DecisionResult
  risk_aware_result: Record<string, unknown>
}

export type Scenario = NetworkInput & {
  id: number
  name: string
  description: string
  is_default: boolean
  created_at: string
}

export type SimulationStep = {
  'Time Step': string
  'Traffic Type': string
  Threat: number
  Congestion: number
  'Bandwidth (Mbps)': number
  'Application Priority': number
  'Device Trust': number
  'Latency (ms)': number
  'Decision Score': number
  Priority: string
  'QoS Policy': string
  'Bandwidth Allocation': number
  Queue: string
  'Security Action': string
  Reason: string
  'Factor Contributions': Record<string, number>
  'Normalized Factors': Record<string, number>
  'Dynamic Weights': Record<string, number>
  'Scenario Name': string
}

export type SimulationComparison = {
  Scenario: string
  'Traffic Type': string
  'Threat Level': number
  Congestion: number
  'Bandwidth (Mbps)': number
  'Latency (ms)': number
  'Adaptive Score': number
  'Adaptive Priority': string
  'Adaptive Policy': string
  'Security Action': string
  'Static Priority': string
  'Static Policy': string
  Adapted: 'Yes' | 'No'
  'Scenario Name': string
}

export type Simulation = {
  id: number
  name: string
  created_at: string
  scenario_ids: number[]
  results: SimulationStep[]
  comparison: SimulationComparison[]
}

export type AnalyticsSummary = {
  total_decisions: number
  average_score: number | null
  security_overrides: number
  most_common_policy: string | null
  average_bandwidth_allocation: number | null
  average_latency: number | null
  decision_score_over_time: Array<{ time: string; traffic_type: string; value: number }>
  threat_level_over_time: Array<{ time: string; traffic_type: string; value: number }>
  congestion_over_time: Array<{ time: string; traffic_type: string; value: number }>
  policy_distribution: Array<{ name: string; value: number }>
  security_distribution: Array<{ name: string; value: number }>
  traffic_distribution: Array<{ name: string; value: number }>
}

export type SystemStatus = {
  api_connected: boolean
  database_connected: boolean
  database: string
  decision_engine_active: boolean
  temporal_risk_active: boolean
  stability_active: boolean
}

export type EvaluationScenario = {
  scenario_id: string
  description: string
  network_input: NetworkInput
}

export type AblationVariantSummary = {
  counts?: Record<string, number>
  percentages?: Record<string, number>
  numerator?: number
  denominator?: number
  rate?: number
}

export type AblationSummary = {
  scenario_count: number
  variant_count: number
  policy_distribution: Record<string, AblationVariantSummary>
  security_override_rate: Record<string, AblationVariantSummary | null>
  risk_constraint_violation_rate: Record<string, AblationVariantSummary | null>
  mean_effective_security_risk: Record<string, number | null>
  mean_raw_security_risk: Record<string, number | null>
  mean_qos_utility: Record<string, number | null>
  temporal_trend_counts: Record<string, Record<string, number> | null>
  policy_switching_metrics: Record<string, Record<string, {
    decisions: number
    switches: number
    psr: number
    psi: number
  }>>
  hysteresis_effect: {
    scenario_ids: string[]
    candidate_policies: string[]
    final_policies: string[]
    candidate_switch_count: number
    final_switch_count: number
  } | null
  phase_differences: Record<string, Record<string, unknown>>
}

export type AblationResponse = {
  evaluation_type: string
  runs: Array<{
    scenario_id: string
    variant: string
    sequence_id: string | null
    result: Record<string, unknown> & {
      policy?: string
      raw_security_risk?: number | null
      effective_security_risk?: number | null
      qos_utility?: number | null
      threat_trend?: string | null
      risk_budget_satisfied?: boolean | null
    }
  }>
  summary: AblationSummary
}

export type TestbedStatus = {
  connected: boolean
  interface: string
  message: string
  telemetry: Record<string, string | number> | null
}

export type SystemSettings = {
  api_endpoint: string
  database_location: string
  application_version: string
  baseline_status: string
  weights: Record<string, number>
  policy_thresholds: Record<string, number>
  security_thresholds: Record<string, number>
  traffic_type_scores: Record<string, number>
  risk_aware: {
    r_max: number
    risk_penalty_weight: number
  }
  temporal: {
    enabled: boolean
    alpha: number
    trend_threshold: number
    risk_adjustment: Record<string, number>
  }
  stability: {
    enabled: boolean
    switching_penalty: number
    hysteresis: {
      enabled: boolean
      high_enter: number
      high_exit: number
      critical_enter: number
      critical_exit: number
      normal_enter: number
      normal_exit: number
    }
  }
  control_mode: string
}
