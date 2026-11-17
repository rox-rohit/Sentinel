export type Severity = 'normal' | 'low' | 'medium' | 'high' | 'critical'
export type HealthCategory = 'healthy' | 'attention' | 'warning' | 'critical'

export interface HorizonRisk {
  [horizon: string]: number
}

export interface AssetSeries {
  cycle: number[]
  predicted_rul: number[]
  health: number[]
  anomaly: number[]
  sensors: Record<string, number[]>
}

export interface Asset {
  id: string
  asset_id: number
  label: string
  dataset: string
  criticality: number
  cycle: number
  lifetime: number
  status: HealthCategory
  health_score: number
  health_components: Record<string, number>
  health_explanation: string
  rul: {
    estimate: number
    lower: number
    upper: number
    clip: number
    horizon_risk: HorizonRisk
  }
  anomaly: {
    score: number
    severity: Severity
    detectors: Record<string, number>
    top_sensors: { sensor: string; label: string; z_score: number; value: number }[]
  }
  degradation: { health_slope_per_cycle: number; direction: string }
  latest_sensors: { sensor: string; label: string; value: number; healthy_mean: number }[]
  series: AssetSeries
  actual_rul_final: number | null
  source: string
}

export interface Alert {
  asset_id: string
  label: string
  kind: string
  severity: Severity
  cycle: number
  score: number
  message: string
  sensors: string[]
}

export type AlertStatus = 'open' | 'acknowledged' | 'resolved'

export interface AlertLifecycle extends Alert {
  id: number
  fingerprint: string
  status: AlertStatus
  acknowledged: boolean
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  resolved_by: string | null
  note: string | null
  created_at: string
  updated_at: string | null
}

export interface AlertInbox {
  alerts: AlertLifecycle[]
  counts: { open: number; acknowledged: number; resolved: number; total: number }
  statuses: AlertStatus[]
}

export interface ScenarioSummary {
  id: number
  name: string
  note: string | null
  created_at: string | null
  budget: number
  spent: number
  expected_avoided_loss: number
  expected_downtime_hours: number
  assets_serviced: number
  asset_count: number
  predictive_cost: number
  reactive_cost: number
  preventive_cost: number
  selected_assets: string[]
  avoided_per_1000_spent: number | null
}

export interface ScenarioMetric {
  key: string
  label: string
  unit: 'currency' | 'hours' | 'count'
  better: 'higher' | 'lower'
  values: Record<string, number | null>
  best_ids: string[]
}

export interface ScenarioComparison {
  scenarios: ScenarioSummary[]
  metrics: ScenarioMetric[]
  deltas_vs_first: Record<string, Record<string, number | null>>
  assets: {
    shared: string[]
    shared_count: number
    union_count: number
    unique: Record<string, string[]>
  }
  note: string
}

export interface OnboardingColumn {
  source: string
  target: string | null
  confidence: number
  dtype: string
  missing_pct: number
  unique: number
  sample: (string | number | null)[]
}

export interface OnboardingInspection {
  schema_version: string
  rows: number
  columns: OnboardingColumn[]
  suggested_mapping: Record<string, string>
  unmapped: string[]
  required_targets: string[]
  targets: string[]
  source_file: string
}

export interface OnboardingIssue {
  severity: 'error' | 'warning' | 'info'
  code: string
  message: string
  column: string | null
  count: number
  pct: number
}

export interface OnboardingReport {
  readiness: 'blocked' | 'warnings' | 'ready'
  quality_score: number
  rows: number
  asset_count: number
  assets: {
    asset_id: string
    rows: number
    min_cycle: number
    max_cycle: number
    span: number
    short_history: boolean
  }[]
  issues: OnboardingIssue[]
  error_count: number
  warning_count: number
  scoring: {
    eligible: boolean
    reasons: string[]
    mapped_sensors: number
    missing_sensors: string[]
    min_cycles_required: number
  }
  mapping: Record<string, string>
  schema_version: string
  source_file: string
  preview: Record<string, string | number | null>[]
  notes: string[]
  drift?: SchemaDrift | null
}

export interface SchemaDrift {
  profile_id: number | null
  profile_name?: string
  status: 'unchanged' | 'drift'
  changed: boolean
  blocking: boolean
  expected_columns: string[]
  current_columns: string[]
  added: string[]
  missing: string[]
  renamed: { from: string; to: string; confidence: number; target: string | null }[]
  suggestions: { source: string; target: string | null; confidence: number }[]
  dropped_targets: string[]
  mapping: Record<string, string>
  requires_acknowledgement: boolean
  reason: string | null
}

export interface MappingProfile {
  id: number
  name: string
  source: string
  mapping: Record<string, string>
  expected_columns: string[]
  notes: string | null
  use_count: number
  created_at: string
  updated_at: string | null
  last_used_at: string | null
}

export interface PlantAsset {
  id: number
  asset_id: string
  name: string
  source_file: string
  status: 'ready' | 'registered'
  score_eligible: boolean
  rows: number
  cycles: number
  min_cycle: number
  max_cycle: number
  sensors: string[]
  mapping: Record<string, string>
  quality: OnboardingReport
  parquet_path: string
  notes: string | null
  created_at: string
  updated_at: string | null
}

export interface Snapshot {
  meta: {
    product: string
    build_version: string
    generated_at: string
    pipeline: string
    duration_seconds: number
    dataset_versions: Record<string, { version: string; rows: number; quality_score: number; source_url: string }>
    feature_specs: number
    runtime: { python: string; platform: string }
  }
  fleet: {
    summary: {
      total: number
      healthy: number
      attention: number
      warning: number
      critical: number
      avg_health: number
      avg_rul: number
      active_anomalies: number
      predicted_failures_30: number
      predicted_failures_10: number
      maintenance_actions: number
      budget: number
      planned_spend: number
      deferred: number
      alerts: number
    }
    health_distribution: { category: HealthCategory; count: number }[]
    risk_distribution: { band: string; count: number }[]
    health_weights: {
      weights: Record<string, number>
      bands: Record<string, number>
      method: string
      limitations: string[]
    }
    data_source: string
  }
  assets: Asset[]
  alerts: Alert[]
  predictive: {
    risk_distribution: { band: string; count: number }[]
    horizon_curve: { horizon: number; high_risk: number; mean_risk: number }[]
    highest_risk: {
      id: string
      label: string
      health: number
      risk_10: number
      risk_30: number
      risk_50: number
      rul: number
      lower: number
      upper: number
      status: HealthCategory
    }[]
    confidence: { mean_interval_width: number; residual_quantiles: Record<string, number | string> }
    model: string
    method: string
  }
  anomalies: {
    summary: {
      fit_rows: number
      scored_rows: number
      healthy_score_mean: number
      ensemble: string
      severity_distribution: Record<string, number>
      thresholds: Record<string, number>
      limitations: string[]
    }
    severity_distribution: Record<string, number>
    score_histogram: { counts: number[]; edges: number[] }
    recent: Alert[]
    affected_sensors: { sensor: string; assets: number }[]
    scored_rows: number
  }
  rul: {
    benchmark: {
      official: Record<string, number>
      validation: Record<string, number>
      comparison: Record<string, number | string>[]
      residuals: Record<string, number | string>
      clip: number
      protocol: string
    }
    points: { asset_id: string; actual: number; predicted: number; lower: number; upper: number }[]
    fleet: { id: string; estimate: number; lower: number; upper: number; status: HealthCategory }[]
    warnings: string[]
    limitations: string[]
  }
  explainability: {
    dataset: string
    global_importance: { feature: string; label: string; importance: number; std: number }[]
    samples: {
      title: string
      row_id: number
      product_type: string
      actual_failure: number
      probability: number
      threshold: number
      decision: string
      contributions: { feature: string; label: string; value: number; contribution: number }[]
      narrative: string
    }[]
    method: string
    calibration: {
      brier_score: number
      brier_baseline_rate: number
      reliability: { bin_lower: number; bin_upper: number; mean_predicted: number; observed_rate: number; count: number }[]
      note: string
    }
    failure_modes: {
      labels: { column: string; label: string; train_support: number; test_support: number; status: string; pr_auc: number | null; recall: number | null; precision: number | null; note: string }[]
      method: string
      limitations: string[]
    }
    limitations: string[]
  }
  forecast: {
    sensors: { key: string; label: string }[]
    horizons: number[]
    all_horizons: number[]
    models: string[]
    validation: {
      protocol: string
      train_fraction: number
      train_rows: number
      test_rows: number
      units: number
      ses_alpha: number
    }
    comparison: {
      sensor: string
      label: string
      horizon: number
      model: string
      mae: number
      rmse: number
      mase: number
    }[]
    best: {
      sensor: string
      label: string
      horizon: number
      model: string
      mae: number
      rmse: number
      mase: number
    }[]
    summary: {
      best_model: string
      wins: Record<string, number>
      mean_best_mase: number | null
      mean_persistence_mase: number | null
      improvement_vs_persistence_pct: number | null
    }
    example: {
      asset_id: string | null
      origin_cycle: number | null
      series: {
        sensor: string
        label: string
        asset_id: string
        origin_cycle: number
        horizons: number[]
        actual: number[]
        forecast: number[]
      }[]
    }
    limitations: string[]
  }
  maintenance: {
    budget: number
    spent: number
    expected_avoided_loss: number
    expected_downtime_hours: number
    selected: {
      asset_id: string
      action: string
      criticality: number
      failure_risk: number
      predicted_rul: number
      planned_cost: number
      expected_failure_cost: number
      expected_benefit: number
      priority_score: number
      downtime_hours: number
      window: string
    }[]
    deferred: { asset_id: string; failure_risk: number; predicted_rul: number; expected_benefit: number }[]
    scenarios: { strategy: string; label: string; cost: number; downtime_hours: number; serviced: number; description: string }[]
    assumptions: Record<string, number>
    notes: string[]
    health_weights?: unknown
  }
  models: {
    id: number
    name: string
    task: string
    dataset: string
    version: string
    algorithm: string
    status: string
    metrics: Record<string, unknown>
    params: Record<string, unknown>
    created_at: string
  }[]
  datasets: {
    id: number
    name: string
    display_name: string
    version: string
    rows: number
    columns: number
    quality: {
      score: number
      ok: boolean
      error_count: number
      warning_count: number
      issues: { severity: string; code: string; message: string; column?: string | null; count: number; pct: number }[]
    }
    schema: { name: string; notes?: string[]; columns?: { name: string; dtype: string; description: string; unit?: string | null }[] }
    source_url: string
    created_at: string
  }[]
  eda: Record<string, EdaPayload>
  drift: {
    ai4i: { comparison: string; features: { feature: string; psi: number; status: string }[] }
    cmapss: { comparison: string; features: { feature: string; psi: number; status: string }[] }
    worst_psi: number
    overall_status: string
    method: string
    thresholds: Record<string, string>
    note: string
  }
  settings: {
    costs: Record<string, number>
    health: {
      weights: Record<string, number>
      bands: Record<string, number>
      method: string
      limitations: string[]
    }
    horizons: number[]
    rul_clip: number
    rolling_windows: number[]
    budget: number
    failure_threshold: number
    cmapss_subset: string
  }
}

export interface EdaPayload {
  dataset: string
  rows: number
  columns: number
  descriptive: {
    column: string
    count: number
    mean: number
    std: number
    min: number
    p25: number
    median: number
    p75: number
    max: number
    skew: number
    missing: number
  }[]
  correlation: { features: string[]; matrix: number[][] }
  top_correlations: { a: string; b: string; abs_correlation: number }[]
  histograms: { column: string; counts: number[]; edges: number[]; mean: number }[]
  missing: { column: string; missing: number; pct: number }[]
  degradation?: { sensor: string; life_fraction: number[]; mean_value: number[] }[]
  machine_comparison?: { unit: string; latest: number; mean: number; lifetime: number }[]
  fleet_size?: number
  failure_balance?: {
    overall: { positives: number; rows: number; rate: number }
    modes: { column: string; label: string; count: number; rate: number }[]
  }
  notes: string[]
}
