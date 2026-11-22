import type { Asset, Snapshot } from '../data/types'
import { money, number, percent, relativeTime } from './format'

export interface AssistantLink {
  label: string
  href: string
}

export interface AssistantReply {
  text: string
  bullets: string[]
  links: AssistantLink[]
  source: string
}

const HELP: AssistantReply = {
  text: 'I answer from the platform payload the console already loaded — fleet state, alerts, model metrics, datasets and settings. No external model is called, so the same answers work in live and snapshot mode.',
  bullets: [
    'Try “how is the fleet doing?” or “which machine is worst?”',
    'Ask about an asset, e.g. “status of FD001-003” or “why is it flagged?”',
    'Ask “how many critical alerts?”, “what is the maintenance plan?”, “which model is best?”',
    'Ask “how do I connect a machine?” for the twin ingest path.',
  ],
  links: [
    { label: 'Fleet overview', href: '/' },
    { label: 'Digital twin', href: '/twins' },
  ],
  source: 'Assistant capabilities',
}

function assetMention(question: string, data: Snapshot): Asset | null {
  const upper = question.toUpperCase()
  const direct = data.assets.find(
    (asset) => upper.includes(asset.id.toUpperCase()) || upper.includes(asset.label.toUpperCase()),
  )
  if (direct) return direct
  const numeric = upper.match(/FD001[\s-]?0*(\d{1,3})/)
  if (numeric) {
    const index = Number(numeric[1])
    return data.assets.find((asset) => asset.asset_id === index) ?? null
  }
  return null
}

function assetReply(asset: Asset, data: Snapshot): AssistantReply {
  const alerts = data.alerts.filter((alert) => alert.asset_id === asset.id)
  const top = asset.anomaly.top_sensors[0]
  return {
    text: `${asset.label} is ${asset.status} with a health score of ${number(asset.health_score, 0)}/100 at recorded cycle ${asset.cycle} of ${asset.lifetime}.`,
    bullets: [
      `Estimated RUL ${number(asset.rul.estimate, 0)} cycles (80% band ${number(asset.rul.lower, 0)}–${number(asset.rul.upper, 0)}).`,
      `Failure risk: ${percent(asset.rul.horizon_risk['10'] ?? 0)} within 10 cycles, ${percent(asset.rul.horizon_risk['30'] ?? 0)} within 30, ${percent(asset.rul.horizon_risk['50'] ?? 0)} within 50.`,
      `Anomaly ensemble ${number(asset.anomaly.score, 2)} (${asset.anomaly.severity}); degradation ${asset.degradation.direction} at ${number(asset.degradation.health_slope_per_cycle, 2)} points/cycle.`,
      top ? `Largest deviation: ${top.label} at ${top.z_score > 0 ? '+' : ''}${number(top.z_score, 1)}σ.` : 'No dominant sensor attribution.',
      `${alerts.length} alert${alerts.length === 1 ? '' : 's'} recorded for this asset in the current build.`,
      `Health components — RUL ${number(asset.health_components.rul_health ?? 0, 0)}, risk ${number(asset.health_components.risk_health ?? 0, 0)}, anomaly ${number(asset.health_components.anomaly_health ?? 0, 0)}, trend ${number(asset.health_components.trend_health ?? 0, 0)}.`,
    ],
    links: [
      { label: `Open ${asset.label}`, href: `/assets/${encodeURIComponent(asset.id)}` },
      { label: 'Machine intelligence', href: '/assets' },
    ],
    source: `Asset record · build ${data.meta.build_version}`,
  }
}

function fleetReply(data: Snapshot): AssistantReply {
  const summary = data.fleet.summary
  const worst = [...data.assets].sort((a, b) => a.health_score - b.health_score).slice(0, 4)
  return {
    text: `${summary.total} assets are tracked: ${summary.healthy} healthy, ${summary.attention} attention, ${summary.warning} warning and ${summary.critical} critical. Mean health is ${number(summary.avg_health, 1)}/100.`,
    bullets: [
      `Average RUL ${number(summary.avg_rul, 0)} cycles; ${summary.predicted_failures_30} assets carry a 30-cycle failure risk and ${summary.active_anomalies} are in an active anomaly.`,
      `This build produced ${summary.alerts} alerts and plans ${summary.maintenance_actions} maintenance actions against a ${money(summary.budget)} budget.`,
      ...worst.map((asset) => `${asset.label}: health ${number(asset.health_score, 0)}/100, RUL ${number(asset.rul.estimate, 0)} cycles, ${asset.status}.`),
    ],
    links: [
      { label: 'Fleet overview', href: '/' },
      { label: 'Predictive analytics', href: '/predictive' },
    ],
    source: `Fleet summary · build ${data.meta.build_version}`,
  }
}

function alertsReply(question: string, data: Snapshot): AssistantReply {
  const critical = data.alerts.filter((alert) => alert.severity === 'critical' || alert.severity === 'high')
  const ranked = [...critical, ...data.alerts.filter((alert) => !critical.includes(alert))]
  const limit = /all|every/.test(question) ? 8 : 4
  return {
    text: `The current build holds ${data.alerts.length} alerts, ${critical.length} of them high or critical.`,
    bullets: [
      ...ranked.slice(0, limit).map((alert) => `${alert.severity.toUpperCase()} · ${alert.label} · cycle ${alert.cycle}: ${alert.message}`),
      'Lifecycle transitions (acknowledge / resolve) are stored in the operational database, so they survive a rebuild.',
    ],
    links: [{ label: 'Alert inbox', href: '/anomalies' }],
    source: `Alert set · build ${data.meta.build_version}`,
  }
}

function riskReply(data: Snapshot): AssistantReply {
  const top = data.predictive.highest_risk.slice(0, 4)
  return {
    text: `${data.predictive.highest_risk.length} assets appear in the risk ranking; the model is ${data.predictive.model}.`,
    bullets: [
      ...top.map((entry) => `${entry.label}: ${percent(entry.risk_30)} risk within 30 cycles, RUL ${number(entry.rul, 0)} (${number(entry.lower, 0)}–${number(entry.upper, 0)}), ${entry.status}.`),
      `Mean 80% interval width ${number(data.predictive.confidence.mean_interval_width, 1)} cycles.`,
      data.predictive.method,
    ],
    links: [{ label: 'Predictive analytics', href: '/predictive' }],
    source: `Prediction payload · build ${data.meta.build_version}`,
  }
}

function rulReply(data: Snapshot): AssistantReply {
  const validation = data.rul.benchmark.validation
  const lowest = [...data.rul.fleet].sort((a, b) => a.estimate - b.estimate).slice(0, 3)
  return {
    text: `The RUL model targets ${data.settings.rul_clip}-cycle clips. ${data.rul.benchmark.protocol}`,
    bullets: [
      `Held-out RMSE ${number(Number(validation.rmse ?? validation.RMSE ?? 0), 2)} cycles; R² ${number(Number(validation.r2 ?? validation.R2 ?? 0), 3)}.`,
      ...lowest.map((entry) => `${entry.id}: ${number(entry.estimate, 0)} cycles remaining (${number(entry.lower, 0)}–${number(entry.upper, 0)}), ${entry.status}.`),
      ...data.rul.limitations.slice(0, 2),
    ],
    links: [{ label: 'RUL intelligence', href: '/rul' }],
    source: `RUL benchmark · build ${data.meta.build_version}`,
  }
}

function maintenanceReply(data: Snapshot): AssistantReply {
  const plan = data.maintenance
  return {
    text: `The optimiser selected ${plan.selected.length} of ${plan.selected.length + plan.deferred.length} candidates for a ${money(plan.budget)} budget, spending ${money(plan.spent)}.`,
    bullets: [
      `Expected avoided loss ${money(plan.expected_avoided_loss)} with ${number(plan.expected_downtime_hours, 1)} planned downtime hours.`,
      ...plan.selected.slice(0, 4).map((entry) => `${entry.asset_id}: ${entry.action}, RUL ${number(entry.predicted_rul, 0)}, ${entry.window}, ${money(entry.planned_cost)}.`),
      `${plan.deferred.length} assets deferred; ${plan.notes[0] ?? 'costs are documented engineering assumptions.'}`,
    ],
    links: [{ label: 'Maintenance optimiser', href: '/maintenance' }],
    source: `Maintenance plan · build ${data.meta.build_version}`,
  }
}

function anomalyReply(data: Snapshot): AssistantReply {
  const summary = data.anomalies.summary
  const sensors = data.anomalies.affected_sensors.slice(0, 3)
  return {
    text: `${number(summary.scored_rows, 0)} rows were scored by the ensemble (${summary.ensemble}) with a healthy-row mean of ${number(summary.healthy_score_mean, 2)}.`,
    bullets: [
      ...Object.entries(summary.severity_distribution).map(([name, count]) => `${name}: ${number(count, 0)} rows.`),
      sensors.length ? `Most affected channels: ${sensors.map((entry) => `${entry.sensor} (${entry.assets} assets)`).join(', ')}.` : 'No channel dominates the affected set.',
      ...summary.limitations.slice(0, 2),
    ],
    links: [{ label: 'Anomaly centre', href: '/anomalies' }],
    source: `Anomaly artefacts · build ${data.meta.build_version}`,
  }
}

function modelReply(data: Snapshot): AssistantReply {
  return {
    text: `${data.models.length} model versions are registered. Selection is metric-driven, never accuracy alone.`,
    bullets: data.models.slice(0, 5).map((model) => `${model.name} · ${model.algorithm} · ${model.task} · ${model.status} · ${model.dataset} ${model.version}`),
    links: [{ label: 'Model laboratory', href: '/models' }],
    source: `Model registry · build ${data.meta.build_version}`,
  }
}

function datasetReply(data: Snapshot): AssistantReply {
  return {
    text: `${data.datasets.length} datasets are registered and validated at build time.`,
    bullets: data.datasets.map((dataset) => `${dataset.display_name} (${dataset.name} ${dataset.version}): ${number(dataset.rows, 0)} rows, ${dataset.columns} columns, quality ${dataset.quality.score}/100, ${dataset.quality.error_count} errors.`),
    links: [{ label: 'Dataset management', href: '/datasets' }],
    source: `Dataset registry · build ${data.meta.build_version}`,
  }
}

function forecastReply(data: Snapshot): AssistantReply {
  const summary = data.forecast.summary
  const best = data.forecast.best.slice(0, 4)
  return {
    text: `${summary.best_model} wins most sensor/horizon pairs across ${Object.keys(summary.wins).length} model families. Mean best MASE ${number(summary.mean_best_mase, 3)} versus ${number(summary.mean_persistence_mase, 3)} for persistence.`,
    bullets: [
      summary.improvement_vs_persistence_pct != null
        ? `${number(summary.improvement_vs_persistence_pct, 1)}% improvement over persistence.`
        : 'No persistence comparison available.',
      ...best.map((entry) => `${entry.label} · h=${entry.horizon} · ${entry.model} · MASE ${number(entry.mase, 3)}, RMSE ${number(entry.rmse, 3)}.`),
      data.forecast.validation.protocol,
    ],
    links: [{ label: 'Sensor forecasting', href: '/forecast' }],
    source: `Forecast comparison · build ${data.meta.build_version}`,
  }
}

function explainReply(data: Snapshot): AssistantReply {
  const top = data.explainability.global_importance.slice(0, 4)
  return {
    text: `${data.explainability.method} Contributions are model attribution, not physical causation.`,
    bullets: [
      ...top.map((entry) => `${entry.label}: importance ${number(entry.importance, 3)} (±${number(entry.std, 3)}).`),
      `Brier score ${number(data.explainability.calibration.brier_score, 4)} against a ${number(data.explainability.calibration.brier_baseline_rate, 4)} baseline.`,
      ...data.explainability.limitations.slice(0, 2),
    ],
    links: [{ label: 'Explainable AI', href: '/explainability' }],
    source: `Explainability artefacts · build ${data.meta.build_version}`,
  }
}

function settingsReply(data: Snapshot): AssistantReply {
  const costs = data.settings.costs
  const weights = data.settings.health.weights
  return {
    text: `Health is a weighted score: RUL ${percent(weights.rul ?? 0, 0)}, risk ${percent(weights.risk ?? 0, 0)}, anomaly ${percent(weights.anomaly ?? 0, 0)}, trend ${percent(weights.trend ?? 0, 0)}.`,
    bullets: [
      `Cost assumptions: missed failure ${money(costs.false_negative_cost)}, unnecessary inspection ${money(costs.false_positive_cost)}, planned service ${money(costs.planned_maintenance_cost)}, unplanned failure ${money(costs.unplanned_failure_cost)}, downtime ${money(costs.downtime_cost_per_hour)}/h.`,
      `Failure threshold ${number(data.settings.failure_threshold, 2)}; RUL clip ${data.settings.rul_clip} cycles; rolling windows ${data.settings.rolling_windows.join('/')}.`,
      `Build ${data.meta.build_version} generated ${relativeTime(data.meta.generated_at)} on Python ${data.meta.runtime.python}.`,
    ],
    links: [{ label: 'System settings', href: '/settings' }],
    source: `Settings payload · build ${data.meta.build_version}`,
  }
}

function securityReply(): AssistantReply {
  return {
    text: 'Mutating routes accept an X-API-Key; device ingest requires a per-device X-Device-Token that is stored only as a PBKDF2 digest. Traffic is capped and rate-limited before routing.',
    bullets: [
      'Security headers: nosniff, frame denial, no-referrer, permissions policy, HSTS on HTTPS and a frame-locked CSP.',
      'Request bodies are capped at 8 MB, ingest at 25 samples/second per device, and API routes at a configurable per-client limit.',
      'CORS allows the console origins only and the mutating verbs it actually needs.',
      'Set SENTINEL_API_KEY (and SENTINEL_REQUIRE_API_KEY=true) in the App Service to fail closed. The console sends the key from session storage.',
      'Database storage encryption is provided by the managed PostgreSQL service; no secret is stored in the bundle or the repository.',
    ],
    links: [{ label: 'System settings', href: '/settings' }],
    source: 'Runtime security configuration',
  }
}

function twinReply(): AssistantReply {
  return {
    text: 'The twin studio binds a machine to a digital twin. Manual mode scores readings you enter or a gateway pushes; auto mode streams the bound asset\'s recorded trajectory through the same ingest path.',
    bullets: [
      'Register a twin, then send POST /api/v1/devices/{id}/telemetry with X-Device-Token and a sensors object.',
      'Health is baseline-relative: 100 − min(50, 11 × deviation index) − coverage penalty.',
      'Deviation index = 0.65 × peak |z| + 0.35 × median |z|, so one failing channel cannot hide.',
      'Auto mode needs a bound fleet asset and uses the build\'s replay artifact as its source.',
    ],
    links: [{ label: 'Machine twin studio', href: '/twins' }],
    source: 'Digital twin ingest contract',
  }
}

const INTENTS: { id: string; keywords: string[]; run: (question: string, data: Snapshot) => AssistantReply }[] = [
  { id: 'help', keywords: ['help', 'what can you do', 'capabilities', 'how do i use', 'question'], run: () => HELP },
  { id: 'twin', keywords: ['twin', 'connect a machine', 'connect machine', 'plc', 'gateway', 'device', 'sensor feed', 'auto mode'], run: () => twinReply() },
  { id: 'security', keywords: ['security', 'secure', 'encrypt', 'api key', 'token', 'auth', 'rate limit'], run: () => securityReply() },
  { id: 'alert', keywords: ['alert', 'alarm', 'inbox', 'acknowledge', 'resolve'], run: alertsReply },
  { id: 'maintenance', keywords: ['maintenance', 'budget', 'plan', 'optimise', 'optimize', 'service', 'downtime'], run: (_q, data) => maintenanceReply(data) },
  { id: 'rul', keywords: ['rul', 'remaining life', 'remaining useful', 'life left', 'cycles left'], run: (_q, data) => rulReply(data) },
  { id: 'risk', keywords: ['risk', 'failure probability', 'predict', 'forecast failure', 'fail within'], run: (_q, data) => riskReply(data) },
  { id: 'anomaly', keywords: ['anomaly', 'outlier', 'deviation', 'severity'], run: (_q, data) => anomalyReply(data) },
  { id: 'models', keywords: ['model', 'algorithm', 'xgboost', 'accuracy', 'rmse', 'mae', 'metric'], run: (_q, data) => modelReply(data) },
  { id: 'datasets', keywords: ['dataset', 'data quality', 'rows', 'cmapss', 'ai4i', 'drift'], run: (_q, data) => datasetReply(data) },
  { id: 'forecast', keywords: ['forecast', 'horizon', 'sensor prediction', 'mase'], run: (_q, data) => forecastReply(data) },
  { id: 'explain', keywords: ['explain', 'shap', 'why', 'importance', 'attribution', 'contribution'], run: (_q, data) => explainReply(data) },
  { id: 'settings', keywords: ['setting', 'cost', 'threshold', 'weight', 'config', 'version', 'build'], run: (_q, data) => settingsReply(data) },
  { id: 'fleet', keywords: ['fleet', 'how is', 'overall', 'summary', 'worst', 'riskiest', 'health', 'status', 'machine'], run: (_q, data) => fleetReply(data) },
]

/** Deterministic retrieval over the loaded payload; no network, no API key. */
export function askAssistant(question: string, data: Snapshot): AssistantReply {
  const text = question.trim()
  if (!text) return HELP

  const mentioned = assetMention(text, data)
  if (mentioned) return assetReply(mentioned, data)

  const lower = text.toLowerCase()
  let best: { intent: (typeof INTENTS)[number]; hits: number } | null = null
  for (const intent of INTENTS) {
    const hits = intent.keywords.reduce(
      (total, keyword) => total + (lower.includes(keyword) ? 1 : 0),
      0,
    )
    if (hits > 0 && (!best || hits > best.hits)) best = { intent, hits }
  }

  if (!best) {
    const worst = [...data.assets].sort((a, b) => a.health_score - b.health_score)[0]
    return {
      ...HELP,
      text: `I could not match “${text}” to a platform topic. ${worst ? `The lowest-health asset right now is ${worst.label} at ${number(worst.health_score, 0)}/100.` : ''}`,
    }
  }
  return best.intent.run(text, data)
}

export const ASSISTANT_SUGGESTIONS = [
  'How is the fleet doing?',
  'Which machine is worst?',
  'How many critical alerts?',
  'What is the maintenance plan?',
  'How do I connect a machine?',
]
